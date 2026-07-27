import os
import sys
import pathlib
import shutil
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.database.models import SourceDocument

def migrate_pdfs_to_txt():
    db: Session = SessionLocal()
    
    print("🔍 Buscando documentos procesados para migrar a TXT...")
    
    # Buscar todos los documentos procesados que aún apuntan a un PDF
    docs = db.query(SourceDocument).filter(
        SourceDocument.status == "completed",
        SourceDocument.filename.ilike("%.pdf")
    ).all()
    
    if not docs:
        print("✅ No se encontraron documentos PDF completados pendientes de migración.")
        db.close()
        return

    print(f"📊 Se encontraron {len(docs)} documentos PDF completados.")
    
    success_count = 0
    failed_count = 0
    
    processed_dir_base = pathlib.Path("data/processed")
    
    for doc in docs:
        original_pdf_path = pathlib.Path(doc.original_path)
        full_text_path = processed_dir_base / str(doc.id) / "full_text.txt"
        txt_dest_path = original_pdf_path.with_suffix(".txt")
        
        if not full_text_path.exists():
            print(f"⚠️ [Error] No se encontró el texto extraído para {doc.filename}. Saltando.")
            failed_count += 1
            continue
            
        try:
            # 1. Copiar el texto limpio a la carpeta origen
            shutil.copy2(full_text_path, txt_dest_path)
            
            # 2. Borrar el PDF original pesado si existe
            original_pdf_path.unlink(missing_ok=True)
            
            # 3. Actualizar la base de datos
            doc.original_path = str(txt_dest_path)
            doc.filename = txt_dest_path.name
            
            # Recalcular tamaño y sha256 para el nuevo archivo de texto
            import hashlib
            hasher = hashlib.sha256()
            with open(txt_dest_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            doc.sha256 = hasher.hexdigest()
            doc.file_size = txt_dest_path.stat().st_size
            
            db.commit()
            
            print(f"✅ Migrado y borrado: {doc.filename}")
            success_count += 1
            
        except Exception as e:
            db.rollback()
            print(f"❌ Error al migrar {doc.filename}: {e}")
            failed_count += 1
            
    db.close()
    
    print("\n==================================================")
    print("🎉 MIGRACIÓN RETROACTIVA FINALIZADA")
    print(f"  - PDFs convertidos a TXT y borrados: {success_count}")
    print(f"  - Errores: {failed_count}")
    print("==================================================")

if __name__ == "__main__":
    migrate_pdfs_to_txt()
