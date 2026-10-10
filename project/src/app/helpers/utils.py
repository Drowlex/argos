
#* Dado que kubectl top pods no da un porcentaje nativo como los nodos, tomé el consumo actual del pod y lo comparé contra la CPU/Memoria que tiene asignada en su manifiesto (requests/limits). Convertí todo a millicores/MB para calcular el porcentaje real de uso de cada pod, y solo filtro aquellos cuya CPU o Memoria esté superando el 75% de la cuota que tienen asignada.
def parse_cpu_to_m(cpu_str: str) -> float:
    """Convierte unidades de CPU a millicores (m)"""
    cpu_str = cpu_str.strip()
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1])
    elif cpu_str.endswith("n"):
        return float(cpu_str[:-1]) / 1_000_000
    try:
        return float(cpu_str) * 1000  # Ejemplo: '1' -> 1000m
    except ValueError:
        return 0.0

def parse_mem_to_mi(mem_str: str) -> float:
    """Convierte unidades de Memoria a Megabytes (Mi)"""
    mem_str = mem_str.strip()
    if mem_str.endswith("Ki"):
        return float(mem_str[:-2]) / 1024
    elif mem_str.endswith("Mi"):
        return float(mem_str[:-2])
    elif mem_str.endswith("Gi"):
        return float(mem_str[:-2]) * 1024
    elif mem_str.endswith("bytes") or mem_str.isdigit():
        return float(mem_str) / (1024 * 1024)
    try:
        return float(mem_str[:-2])
    except ValueError:
        return 0.0

from openpyxl.cell.cell import MergedCell
def set_cell(ws, row, col, value=None, font=None, alignment=None, number_format=None):
    """
    Asigna valor y estilo a una celda de openpyxl de forma segura
    evitando 'AttributeError: MergedCell object attribute value is read-only'.
    """
    cell = ws.cell(row=row, column=col)
    if not isinstance(cell, MergedCell):
        if value is not None:
            cell.value = value
        if font is not None:
            cell.font = font
        if alignment is not None:
            cell.alignment = alignment
        if number_format is not None:
            cell.number_format = number_format
    return cell