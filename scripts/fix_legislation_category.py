import os
import sys
import pathlib
from sqlalchemy.orm import Session

# Añadir el directorio raíz al path para poder importar la configuración de la BD
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.database.models import SourceDocument, SourceType

def fix_legislation_category():
    db: Session = SessionLocal()
    
    # Carpetas que generan documentos del Registro Oficial
    legislation_folders = [
        "registro_oficial",
        "suplementos",
        "edicion_especial",
        "edicion_constitucional",
        "edicion_juridica",
        "indice_mensual"
    ]
    
    print("🔍 Buscando documentos que deberían ser 'legislation' y están como 'document'...")
    
    updated_count = 0
    
    for folder in legislation_folders:
        # Buscamos en el original_path que contenga la carpeta (usando slashes para mayor seguridad)
        search_pattern = f"%/{folder}/%"
        
        # Filtramos los que están mal clasificados
        docs_to_fix = db.query(SourceDocument).filter(
            SourceDocument.source_type == "document",
            SourceDocument.original_path.ilike(search_pattern)
        ).all()
        
        for doc in docs_to_fix:
            print(f"  [Corrigiendo] {doc.filename} ({folder}) -> LEGISLATION")
            doc.source_type = SourceType.LEGISLATION.value
            updated_count += 1
            
    # Guardamos los cambios
    if updated_count > 0:
        db.commit()
        print(f"\n✅ Proceso completado. Se actualizaron exitosamente {updated_count} documentos en la base de datos.")
    else:
        print("\n✅ Proceso completado. No se encontraron documentos mal clasificados.")
        
    db.close()

if __name__ == "__main__":
    fix_legislation_category()
