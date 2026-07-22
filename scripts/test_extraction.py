import sys
import pathlib
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.database.models import SourceDocument, DocumentPage
from app.extraction.pdf_extractor import PDFExtractor
from app.processing.text_cleaner import TextCleaner
from app.processing.document_builder import DocumentBuilder

Base.metadata.create_all(bind=engine)


def test_extraction():
    db: Session = SessionLocal()
    pending_docs = db.query(SourceDocument).filter_by(status="pending").all()

    if not pending_docs:
        print("ℹ️ No hay documentos en estado 'pending'. Ejecuta primero 'python scripts/inventory_documents.py'")
        db.close()
        return

    print(f"⚙️ Procesando extracción para {len(pending_docs)} documentos...")
    extractor = PDFExtractor(db)
    cleaner = TextCleaner()
    builder = DocumentBuilder()

    for doc in pending_docs:
        print(f"\n--- Procesando: {doc.filename} (ID: {doc.id}) ---")
        try:
            extractor.extract_document(str(doc.id))
            print(f"  ✅ Extracción de páginas completada.")

            cleaner.process_document_pages(db, str(doc.id))
            print(f"  ✅ Limpieza de texto completada.")

            full_text_path = builder.build_full_document(db, str(doc.id))
            print(f"  ✅ Ensamblado de full_text.txt completado.")

            # Mostrar resumen de las páginas
            pages = db.query(DocumentPage).filter_by(source_document_id=doc.id).order_by(DocumentPage.page_number).all()
            for p in pages:
                method = p.extraction_method
                sample = (p.clean_text or "")[:80].replace("\n", " ")
                print(f"   - Pág {p.page_number} [{method}]: \"{sample}...\"")

        except Exception as e:
            print(f"  ❌ Error procesando {doc.filename}: {e}")

    db.close()


if __name__ == "__main__":
    test_extraction()
