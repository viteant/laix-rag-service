import os
from pathlib import Path
import re

MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
}

def parse_and_format_name(old_name):
    old_name_lower = old_name.lower()
    
    # Extraer número
    m_num = re.search(r'(?:nº|nro|no|num)\D*(\d+)', old_name_lower)
    num = m_num.group(1) if m_num else "sn"
    
    # Extraer fecha
    m_date = re.search(r'(\d{1,2})\D+([a-z]+)\D+(\d{4})', old_name_lower)
    if m_date:
        dia = m_date.group(1).zfill(2)
        mes_str = m_date.group(2)
        anio = m_date.group(3)
        mes = MESES.get(mes_str, "00")
        fecha_fmt = f"{anio}{mes}{dia}"
    else:
        fecha_fmt = "00000000"
        
    return f"{fecha_fmt}_ro_{num}"

TARGET_DIRS = [
    "registro_oficial", "suplementos", "edicion_especial",
    "edicion_constitucional", "edicion_juridica", "indice_mensual"
]

base_dir = Path("data/source")
for section_dir in base_dir.iterdir():
    if section_dir.is_dir() and section_dir.name in TARGET_DIRS:
        for file_path in section_dir.glob("*.pdf"):
            old_name = file_path.stem
            new_stem = parse_and_format_name(old_name)
            new_path = file_path.with_name(f"{new_stem}.pdf")
            
            if file_path != new_path:
                print(f"Renombrando: {file_path.name} -> {new_path.name}")
                file_path.rename(new_path)
