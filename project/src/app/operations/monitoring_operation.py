from dagster import op, Nothing, In, Out
from app.services import monitoring_service, google_drive_service
from app.core.settings import get_settings

settings = get_settings()

@op(out=Out(Nothing))
def download_reports_from_drive(context):
    """Paso 0: Descargar reportes existentes desde Google Drive"""
    context.log.info("📂 Iniciando descarga de reportes previos desde Google Drive...")
    google_drive_service.drive_service.download_all_from_folder(
        folder_id=settings.FOLDER_ID, local_dir=settings.ASSETS_DIR, context=context
    )

@op(ins={"start_after": In(Nothing)})
def connect_to_gcp(context):
    """Paso 1: Conectar y autenticar los proyectos en GCP/GKE"""
    return monitoring_service.connect_to_gcp_all(context)

@op
def fetch_node_metrics(context, connected_info):
    """Paso 2: Obtener métricas de nodos con kubectl top node"""
    return monitoring_service.get_kubectl_top_nodes(context, connected_info)

@op
def fetch_pods_metrics(context, connected_info):
    """Paso 2: Obtener métricas de pods con kubectl top pods -A"""
    return monitoring_service.get_kubectl_top_pods(context, connected_info)

@op
def process_and_report(context, nodes_data, pods_data):
    """Paso 3: Llenar el reporte Excel basado en base.xlsx"""
    return monitoring_service.process_and_report(context, nodes_data, pods_data)

@op
def upload_reports_to_drive(context, generated_files: list):
    """Paso 4: Subir/Sustituir los Excel actualizados de regreso a Google Drive"""
    context.log.info("📤 Subiendo reportes actualizados a Google Drive...")
    google_drive_service.drive_service.upload_or_update_files(
        folder_id=settings.FOLDER_ID, local_file_paths=generated_files, context=context
    )