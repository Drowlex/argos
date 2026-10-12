import subprocess
import shlex
import os
import openpyxl
import json
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.styles import Font, Alignment
from datetime import datetime
from app.core.settings import get_settings
from app.helpers import utils

settings = get_settings()

class MonitoringService(object):
    _instance = None

    def __new__(cls):
        """
        ? Patrón Singleton
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super(MonitoringService, self).__init__()

    def _execute_command(self, command: str, context):
        """
        Ejecuta un comando de terminal en el contenedor y retorna la salida.
        Soporta pipes (|) y operadores de shell mediante bash.
        """
        context.log.info(f"💻 Ejecutando: {command}")
        if "|" in command or ">" in command or "<" in command:
            result = subprocess.run(
                command,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True
            )
        else:
            result = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True
            )
        if result.returncode != 0:
            context.log.error(f"❌ Error al ejecutar '{command}': {result.stderr.strip()}")
            return None
        return result.stdout.strip()

    def _apply_block_borders(self, ws, start_row: int, end_row: int, start_col: int = 1, end_col: int = 7):
        """
        Aplica bordes consistentes con base.xlsx para el bloque diario:
        - Perímetro exterior: grueso (thick)
        - Líneas divisorias interiores: delgadas (thin)
        - Área de Comments (F y G debajo de cabecera): borde exterior limpio sin divisiones intermedias
        """
        from openpyxl.styles import Border, Side
        thin = Side(style="thin", color="000000")
        thick = Side(style="thick", color="000000")

        for r in range(start_row, end_row + 1):
            for c in range(start_col, end_col + 1):
                cell = ws.cell(row=r, column=c)
                
                # Para el cuadro de comentarios (columnas F y G, debajo de la cabecera)
                if r > start_row and c in (6, 7):
                    t_c = thin if r == start_row + 1 else None
                    b_c = thick if r == end_row else None
                    l_c = thin if c == 6 else None
                    r_c = thick if c == 7 else None
                    cell.border = Border(top=t_c, bottom=b_c, left=l_c, right=r_c)
                else:
                    t = thick if r == start_row else thin
                    b = thick if r == end_row else thin
                    l = thick if c == start_col else thin
                    rg = thick if c == end_col else thin
                    cell.border = Border(top=t, bottom=b, left=l, right=rg)
    

    def get_cluster_info(self, project_id: str, context) -> tuple[str, str]:
        """
        Obtiene automáticamente el nombre del cluster y su ubicación (zona o región) para un project_id dado.
        Retorna (cluster_name, location).
        """
        cmd = f"gcloud container clusters list --project {project_id} --format='value(name,location)'"
        output = self._execute_command(cmd, context)
        
        if not output:
            context.log.warning(f"No se pudo autodetectar cluster para '{project_id}'. Usando fallbacks.")
            return f"gke-{project_id}", settings.GCP_REGION

        # Tomar la primera línea devuelta por gcloud
        line = output.splitlines()[0].strip()
        parts = line.split()

        cluster_name = parts[0]
        # Si gcloud devolvió la ubicación la usamos; de lo contrario usamos la región global por defecto
        location = parts[1] if len(parts) > 1 else settings.GCP_REGION

        context.log.info(f"🔎 Cluster detectado: '{cluster_name}' en location: '{location}'")
        return cluster_name, location

    def connect_to_gcp_all(self, context):
        """
        Paso 1: Conecta a los proyectos configurados en GCP autodeteccionando cluster y región/zona.
        """
        servers = context.op_config.get("servers", [])
        context.log.info(f"🔐 Iniciando conexión GCP a {len(servers)} proyecto(s)...")

        connected_info = []

        for project_id in servers:
            if not isinstance(project_id, str):
                continue

            # Obtiene tanto el nombre del cluster como su location (zone o region) automáticamente
            cluster_name, location = self.get_cluster_info(project_id, context)

            if not cluster_name:
                context.log.error(f"❌ No se encontró ningún cluster para el proyecto '{project_id}'")
                continue

            context.log.info(f"🔐 Configurando cluster GKE '{cluster_name}' en proyecto '{project_id}' ({location})")
            
            self._execute_command(f"gcloud config set project {project_id}", context)
            
            # Usamos --location para soporte automático de zonas y regiones
            get_cred_cmd = f"gcloud container clusters get-credentials {cluster_name} --location {location} --project {project_id}"
            self._execute_command(get_cred_cmd, context)

            connected_info.append({
                "project_id"  : project_id,
                "cluster_name": cluster_name,
                "region"      : location
            })

        return connected_info

    def get_kubectl_top_nodes(self, context, connected_info):
        """
        Paso 2: Ejecuta 'kubectl top node' y parsea la salida para cada proyecto conectado.
        """
        metrics_payload = []

        for item in connected_info:
            project_id = item["project_id"]
            cluster_name = item["cluster_name"]

            context.log.info(f"📡 Obteniendo métricas de nodos con 'kubectl top node' para {project_id}...")
            output = self._execute_command("kubectl top node", context)
            if not output:
                metrics_payload.append({"project_id": project_id, "cluster_name": cluster_name, "nodes": []})
                continue

            lines = output.split("\n")
            nodes = []
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    nodes.append({
                        "name"          : parts[0],
                        "cpu_cores"     : parts[1],
                        "cpu_percent"   : parts[2],
                        "memory_bytes"  : parts[3],
                        "memory_percent": parts[4]
                    })
            
            metrics_payload.append({
                "project_id"  : project_id,
                "cluster_name": cluster_name,
                "nodes"       : nodes
            })

        return metrics_payload

    def get_kubectl_top_pods(self, context, connected_info, threshold=75.0):
        """
        Obtiene las métricas de pods para cada proyecto conectado y retorna la lista mapeada.
        """
        all_pods_data = []
        ignored_namespaces = {"kube-system", "gmp-system", "gke-managed-cim", "gke-system", "kube-public", "kube-node-lease"}

        for item in connected_info:
            project_id = item["project_id"]
            
            # 1. Obtener uso actual de pods de forma nativa sin shlex/bash pipes
            top_output = self._execute_command("kubectl top pods -A --no-headers", context)
            if not top_output:
                continue

            # 2. Obtener solicitudes/límites del cluster
            json_output = self._execute_command("kubectl get pods -A -o json", context)
            if not json_output:
                continue

            pods_spec = json.loads(json_output).get("items", [])
            specs_map = {}
            for pod in pods_spec:
                ns = pod["metadata"]["namespace"]
                if ns in ignored_namespaces:
                    continue  # Ignorar namespaces del sistema

                name = pod["metadata"]["name"]
                containers = pod["spec"].get("containers", [])
                
                total_cpu_req = 0.0
                total_mem_req = 0.0
                
                for c in containers:
                    reqs = c.get("resources", {}).get("requests", {})
                    total_cpu_req += utils.parse_cpu_to_m(reqs.get("cpu", "0m"))
                    total_mem_req += utils.parse_mem_to_mi(reqs.get("memory", "0Mi"))

                specs_map[(ns, name)] = (total_cpu_req, total_mem_req)
            
            # 3. Mapear métricas filtrando namespaces no deseados
            for line in top_output.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue

                ns, name = parts[0], parts[1]
                if ns in ignored_namespaces:
                    continue  # Ignorar namespaces del sistema

                used_cpu = utils.parse_cpu_to_m(parts[2])
                used_mem = utils.parse_mem_to_mi(parts[3])

                req_cpu, req_mem = specs_map.get((ns, name), (0.0, 0.0))

                cpu_pct = (used_cpu / req_cpu * 100) if req_cpu > 0 else 0.0
                mem_pct = (used_mem / req_mem * 100) if req_mem > 0 else 0.0
                
                # context.log.info(f"{'✅' if cpu_pct >= threshold or mem_pct >= threshold else '❌'} {name} - {cpu_pct} >= {threshold} or {mem_pct} >= {threshold}")

                # 4. Filtrar solo los que estén por encima del umbral
                if cpu_pct >= threshold or mem_pct >= threshold:
                    all_pods_data.append({
                        "project_id": project_id,
                        "namespace": ns,
                        "name": name,
                        "cpu_used": parts[2],       # ej: "2m"
                        "cpu_val": used_cpu,        # Valor numérico
                        "cpu_pct": round(cpu_pct, 2),
                        "mem_used": parts[3],       # ej: "88Mi"
                        "mem_val": used_mem,        # Valor numérico
                        "mem_pct": round(mem_pct, 2)
                    })
                    # context.log.info(f"🚀 POD CAPTURADO -> Namespace: {ns} | Pod: {name} | CPU: {parts[2]} ({cpu_pct}) | Memoria: {parts[3]}")

        return all_pods_data
    
    def process_and_report(self, context, nodes_data, pods_data):
        """
        Paso 4: Abre el archivo existente del proyecto (o base.xlsx) y anexa/actualiza
        las métricas del día sin duplicar la fecha.
        """
        assets_dir = settings.ASSETS_DIR
        os.makedirs(assets_dir, exist_ok=True)
        base_template_path = os.path.join(assets_dir, "base.xlsx")

        bold_font    = Font(name="Arial", size=10, bold=True)
        regular_font = Font(name="Arial", size=10, bold=False)
        center_align = Alignment(horizontal="center", vertical="center")
        green_fill   = PatternFill(start_color="A9DFBF", end_color="A9DFBF", fill_type="solid")

        generated_files = []

        # Mapa de pods por proyecto
        pods_by_project = {}
        if isinstance(pods_data, list):
            for p in pods_data:
                pid = p.get("project_id")
                if pid not in pods_by_project:
                    pods_by_project[pid] = []
                pods_by_project[pid].append(p)

        today_str = datetime.now().strftime("%d/%m/%Y")
        #* Fake Date
        # today_str = "12/10/2026"

        for item in nodes_data:
            project_id   = item["project_id"]
            cluster_name = item["cluster_name"]
            nodes        = item["nodes"]

            output_filename = f"{project_id}.xlsx"
            output_path = os.path.join(assets_dir, output_filename)

            context.log.info(f"📊 Procesando métricas para {project_id}...")

            existing_row = None

            # 1. Determinar si abrimos existente o creamos desde base.xlsx
            if os.path.exists(output_path):
                wb = openpyxl.load_workbook(output_path)
                ws = wb.active
                
                # Buscar si la fecha de hoy ya existe en la columna A
                for row in range(13, ws.max_row + 1):
                    val = ws.cell(row=row, column=1).value
                    if val and str(val).strip() == today_str:
                        existing_row = row
                        break

                if existing_row:
                    context.log.info(f"🔄 La fecha {today_str} ya existe en la fila {existing_row}. Se actualizarán los datos.")
                    start_row = existing_row
                else:
                    start_row = max(ws.max_row + 1, 13)
            
            elif os.path.exists(base_template_path):
                wb = openpyxl.load_workbook(base_template_path)
                ws = wb.active
                start_row = 13

                # Limpiar cualquier rango combinado y datos de muestra en la plantilla a partir de la fila 13
                for rng in list(ws.merged_cells.ranges):
                    if rng.min_row >= 13:
                        try:
                            ws.unmerge_cells(str(rng))
                        except Exception:
                            pass
                for r in range(13, ws.max_row + 1):
                    for c in range(1, 8):
                        ws.cell(row=r, column=c).value = None

                # Encabezado general solo en creación (Filas 1 y 2)
                utils.set_cell(ws, 1, 1, value="Proyecto", font=bold_font, alignment=center_align)
                utils.set_cell(ws, 1, 2, value="Entorno", font=bold_font, alignment=center_align)
                utils.set_cell(ws, 1, 4, value="Cluster", font=bold_font, alignment=center_align)

                utils.set_cell(ws, 2, 1, value=project_id, font=bold_font)
                utils.set_cell(ws, 2, 2, value=project_id.split('-')[3].upper() if '-' in project_id else "DEV", font=bold_font, alignment=center_align)
                utils.set_cell(ws, 2, 4, value=cluster_name, font=bold_font, alignment=center_align)
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "DEV"
                start_row = 13

            current_row = start_row

            # 2. Descombinar celdas previas en ese bloque de forma segura (solo si se actualiza fecha existente)
            if existing_row:
                block_end_row = ws.max_row
                for r in range(existing_row + 1, ws.max_row + 1):
                    val = ws.cell(row=r, column=1).value
                    if val and any(rng.min_row == r and rng.min_col == 1 and rng.max_col == 5 for rng in ws.merged_cells.ranges):
                        block_end_row = r - 1
                        break
                for rng in list(ws.merged_cells.ranges):
                    if rng.min_row >= existing_row and rng.max_row <= block_end_row:
                        try:
                            ws.unmerge_cells(str(rng))
                        except ValueError:
                            pass

            # 3. Fila de Fecha y Comments (F{row}:G{row} combinado para la cabecera Comments)
            utils.set_cell(ws, current_row, 1, value=today_str, font=bold_font, alignment=center_align)
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)

            utils.set_cell(ws, current_row, 6, value="Comments", font=regular_font, alignment=center_align)
            ws.cell(row=current_row, column=7).value = None
            ws.merge_cells(start_row=current_row, start_column=6, end_row=current_row, end_column=7)

            date_header_row = current_row
            current_row += 1

            # 4. Llenar los bloques de Nodos
            for node in nodes:
                node_header_row = current_row
                node_val_row = current_row + 1

                utils.set_cell(ws, node_header_row, 1, value=node["name"], font=bold_font, alignment=center_align)
                ws.merge_cells(start_row=node_header_row, start_column=1, end_row=node_val_row, end_column=1)

                utils.set_cell(ws, node_header_row, 2, value="CPU", font=bold_font)
                utils.set_cell(ws, node_header_row, 3, value="CPU (%)", font=bold_font)
                utils.set_cell(ws, node_header_row, 4, value="Memoria", font=bold_font)
                utils.set_cell(ws, node_header_row, 5, value="Memoria(%)", font=bold_font)

                utils.set_cell(ws, node_val_row, 2, value=node["cpu_cores"], font=regular_font)

                try:
                    cpu_pct_num = float(node["cpu_percent"].replace("%", "")) / 100.0
                except ValueError:
                    cpu_pct_num = 0.0
                utils.set_cell(ws, node_val_row, 3, value=cpu_pct_num, font=regular_font, number_format="0%")
                ws.cell(row=node_val_row, column=3).fill = green_fill  # <--- Relleno verde para CPU%
                utils.set_cell(ws, node_val_row, 4, value=node["memory_bytes"], font=regular_font)

                try:
                    mem_pct_num = float(node["memory_percent"].replace("%", "")) / 100.0
                except ValueError:
                    mem_pct_num = 0.0
                utils.set_cell(ws, node_val_row, 5, value=mem_pct_num, font=regular_font, number_format="0%")
                ws.cell(row=node_val_row, column=5).fill = green_fill  # <--- Relleno verde para Memoria%

                current_row += 2

            # 5. Pods que superan el umbral (Top CPU y Top Memoria)
            project_pods = pods_by_project.get(project_id, [])

            # Filtrar pods por tipo de consumo > 75%
            cpu_pods = [p for p in project_pods if p.get("cpu_pct", 0) >= 75.0]
            mem_pods = [p for p in project_pods if p.get("mem_pct", 0) >= 75.0]

            # --- Bloque Top CPU ---
            utils.set_cell(ws, current_row, 1, value="Top CPU", font=bold_font, alignment=center_align)
            utils.set_cell(ws, current_row, 2, value="CPU", font=bold_font, alignment=center_align)
            ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)
            
            utils.set_cell(ws, current_row, 4, value="Memoria", font=bold_font, alignment=center_align)
            ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)

            current_row += 1

            if cpu_pods:
                # Iterar sobre TODOS los pods con CPU > 75%
                for pod in cpu_pods:
                    utils.set_cell(ws, current_row, 1, value=pod["name"], font=regular_font, alignment=center_align)
                    utils.set_cell(ws, current_row, 2, value=pod["cpu_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)
                    
                    utils.set_cell(ws, current_row, 4, value=pod["mem_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)
                    current_row += 1
            else:
                # Si ninguno supera el 75%, colocar el pod de mayor uso general como referencia
                top_cpu_pod = max(project_pods, key=lambda x: x.get("cpu_val", 0), default=None)
                if top_cpu_pod:
                    utils.set_cell(ws, current_row, 1, value=top_cpu_pod["name"], font=regular_font, alignment=center_align)
                    utils.set_cell(ws, current_row, 2, value=top_cpu_pod["cpu_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)
                    
                    utils.set_cell(ws, current_row, 4, value=top_cpu_pod["mem_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)
                    current_row += 1

            # --- Bloque Top Memoria ---
            utils.set_cell(ws, current_row, 1, value="Top Memoria", font=bold_font, alignment=center_align)
            utils.set_cell(ws, current_row, 2, value="CPU", font=bold_font, alignment=center_align)
            ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)

            utils.set_cell(ws, current_row, 4, value="Memoria", font=bold_font, alignment=center_align)
            ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)

            current_row += 1

            if mem_pods:
                # Iterar sobre TODOS los pods con Memoria > 75%
                for pod in mem_pods:
                    utils.set_cell(ws, current_row, 1, value=pod["name"], font=regular_font, alignment=center_align)
                    utils.set_cell(ws, current_row, 2, value=pod["cpu_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)

                    utils.set_cell(ws, current_row, 4, value=pod["mem_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)
                    current_row += 1
            else:
                top_mem_pod = max(project_pods, key=lambda x: x.get("mem_val", 0), default=None)
                if top_mem_pod:
                    utils.set_cell(ws, current_row, 1, value=top_mem_pod["name"], font=regular_font, alignment=center_align)
                    utils.set_cell(ws, current_row, 2, value=top_mem_pod["cpu_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=3)

                    utils.set_cell(ws, current_row, 4, value=top_mem_pod["mem_used"], font=regular_font, alignment=center_align)
                    ws.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=5)
                    current_row += 1

            # 6. Unificar Comments dinámicamente en F{date_header_row + 1}:G{nodes_end_row}
            nodes_end_row = current_row - 1
            if nodes_end_row > date_header_row:
                try:
                    for r in range(date_header_row + 1, nodes_end_row + 1):
                        if ws.cell(row=r, column=6).value == "Comments":
                            ws.cell(row=r, column=6).value = None
                        ws.cell(row=r, column=7).value = None
                    ws.merge_cells(start_row=date_header_row + 1, start_column=6, end_row=nodes_end_row, end_column=7)
                    ws.cell(row=date_header_row + 1, column=6).alignment = Alignment(horizontal="left", vertical="top")
                except Exception:
                    pass

            # Ajustar dimensiones
            ws.column_dimensions['A'].width = 51.25
            ws.column_dimensions['B'].width = 12
            ws.column_dimensions['C'].width = 13
            ws.column_dimensions['D'].width = 13
            ws.column_dimensions['E'].width = 11
            ws.column_dimensions['F'].width = 13
            ws.column_dimensions['G'].width = 13

            # 7. Aplicar bordes exteriores e interiores al bloque del día (estilo base.xlsx)
            if nodes_end_row >= date_header_row:
                self._apply_block_borders(ws, start_row=date_header_row, end_row=nodes_end_row)

            wb.save(output_path)
            context.log.info(f"📁 Reporte procesado exitosamente en: {output_path}")
            generated_files.append(output_path)

        return generated_files

monitoring_service = MonitoringService()