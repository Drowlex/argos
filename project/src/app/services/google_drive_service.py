import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError


def resolve_credentials_path() -> str:
    """Retorna la ruta de credenciales fija de Docker o el fallback local."""
    path = os.getenv("GDRIVE_CREDENTIALS_PATH", "/opt/dagster/app/credentials.json")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    # Fallback si se ejecuta localmente en Mac fuera de Docker
    local_fallback = os.path.abspath(".docker/credentials.json")
    if os.path.exists(local_fallback):
        return local_fallback
    return path


class GoogleDriveService:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self, service_account_json_path: str = None):
        self.credentials_path = service_account_json_path or resolve_credentials_path()
        self._service = None
        self.client_email = None

    @property
    def service(self):
        """Inicialización perezosa (lazy) del cliente de Google Drive."""
        if self._service is None:
            if not os.path.exists(self.credentials_path) or os.path.getsize(self.credentials_path) == 0:
                resolved = resolve_credentials_path()
                if os.path.exists(resolved) and os.path.getsize(resolved) > 0:
                    self.credentials_path = resolved
                else:
                    raise FileNotFoundError(
                        f"No se encontró un archivo credentials.json válido en: {self.credentials_path}"
                    )

            try:
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.client_email = data.get("client_email")
            except Exception:
                pass

            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
            self._service = build("drive", "v3", credentials=creds)

        return self._service

    def download_all_from_folder(self, folder_id: str, local_dir: str, context):
        """
        Descarga todos los archivos .xlsx y hojas de cálculo de Google Sheets contenidos
        en la carpeta de Drive hacia local_dir.
        """
        os.makedirs(local_dir, exist_ok=True)
        query = f"'{folder_id}' in parents and trashed = false"
        
        results = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            )
            .execute()
        )
        files = results.get("files", [])

        context.log.info(
            f"📥 Se encontraron {len(files)} elemento(s) en la carpeta de Google Drive ({folder_id})."
        )

        downloaded_paths = []

        for f in files:
            file_id = f["id"]
            file_name = f["name"]
            mime_type = f.get("mimeType", "")

            # 1. Caso: Hoja de cálculo nativa de Google Sheets
            if mime_type == "application/vnd.google-apps.spreadsheet":
                out_name = file_name if file_name.endswith(".xlsx") else f"{file_name}.xlsx"
                destination_path = os.path.join(local_dir, out_name)
                context.log.info(
                    f"⬇️ Exportando Google Sheet '{file_name}' a '{destination_path}'..."
                )
                request = self.service.files().export_media(
                    fileId=file_id,
                    mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                with open(destination_path, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                downloaded_paths.append(destination_path)

            # 2. Caso: Archivo binario Excel (.xlsx)
            elif file_name.endswith(".xlsx") or mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                destination_path = os.path.join(local_dir, file_name)
                context.log.info(
                    f"⬇️ Descargando archivo Excel '{file_name}' a '{destination_path}'..."
                )
                request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
                with open(destination_path, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                downloaded_paths.append(destination_path)
            else:
                context.log.info(
                    f"ℹ️ Omitiendo '{file_name}' ({mime_type}) por no ser reporte de tipo Excel / Spreadsheet."
                )

        context.log.info(f"✅ Se descargaron {len(downloaded_paths)} archivo(s) a {local_dir}.")
        return downloaded_paths

    def upload_or_update_files(self, folder_id: str, local_file_paths: list, context):
        """
        Sube o actualiza archivos en Google Drive asegurando compatibilidad con cuotas de Service Account.
        Si el archivo ya existe en Drive, lo actualiza (update), evitando el error de cuota.
        """
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query, 
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        # Mapa de archivos existentes para búsqueda flexible (con y sin extensión)
        existing_files = {}
        for f in results.get("files", []):
            fname = f["name"]
            existing_files[fname] = f
            if fname.endswith(".xlsx"):
                existing_files[fname[:-5]] = f
            existing_files[fname.lower()] = f
            if fname.lower().endswith(".xlsx"):
                existing_files[fname.lower()[:-5]] = f

        for local_path in local_file_paths:
            if not os.path.exists(local_path):
                context.log.warning(f"⚠️ El archivo local '{local_path}' no existe. Omitiendo subida.")
                continue
            
            file_name = os.path.basename(local_path)
            name_no_ext = os.path.splitext(file_name)[0]
            
            media = MediaFileUpload(
                local_path, 
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                resumable=True
            )

            # Buscar si ya existe en Drive
            matched = existing_files.get(file_name) or existing_files.get(name_no_ext) or \
                      existing_files.get(file_name.lower()) or existing_files.get(name_no_ext.lower())

            if matched:
                file_id = matched["id"]
                remote_name = matched["name"]
                context.log.info(f"🔄 Actualizando/Sustituyendo '{remote_name}' en Google Drive (ID: {file_id})...")
                
                try:
                    self.service.files().update(
                        fileId=file_id,
                        media_body=media,
                        supportsAllDrives=True
                    ).execute()
                    context.log.info(f"✅ '{remote_name}' actualizado exitosamente en Drive.")
                except Exception as e:
                    context.log.error(f"❌ Error al actualizar '{remote_name}' (ID: {file_id}): {e}")
            else:
                context.log.info(f"📤 Subiendo nuevo archivo '{file_name}' a Google Drive...")
                file_metadata = {
                    'name': file_name,
                    'parents': [folder_id]
                }
                
                try:
                    created = self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, name',
                        supportsAllDrives=True
                    ).execute()
                    context.log.info(f"✅ Archivo '{created.get('name')}' creado exitosamente (ID: {created.get('id')}).")
                except HttpError as e:
                    err_content = str(e)
                    if "storageQuotaExceeded" in err_content or "storage quota" in err_content:
                        context.log.error(
                            f"❌ Error de cuota al crear '{file_name}': Las cuentas de servicio (Service Accounts) tienen 0 MB de cuota personal y Google no permite crear archivos nuevos en carpetas estándar compartidas.\n"
                            f"💡 Soluciones:\n"
                            f"   1) Usa una 'Unidad Compartida' (Shared Drive) de Google Workspace y comparte esa unidad con {self.client_email} como 'Administrador de contenido' o 'Colaborador'.\n"
                            f"   2) O bien, sube o crea previamente un archivo Excel vacío llamado '{file_name}' en la carpeta de Drive desde tu usuario para que el bot solo tenga que actualizarlo (update) sin consumir cuota."
                        )
                    else:
                        context.log.error(f"❌ Error HTTP al crear '{file_name}' en Drive: {e}")
                except Exception as e:
                    context.log.error(f"❌ Error inesperado al subir '{file_name}': {e}")


# Instancia reusable con detección automática de credenciales
DRIVE_CREDENTIALS_PATH = resolve_credentials_path()
drive_service = GoogleDriveService(DRIVE_CREDENTIALS_PATH)