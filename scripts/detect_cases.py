import sys
import pathlib
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.database.models import SourceDocument, LegalCase
from app.processing.case_detector import CaseDetector
from app.processing.metadata_extractor import MetadataExtractor

Base.metadata.create_all(bind=engine)


def process_all_documents(target_doc_id: str = None):
    db: Session = SessionLocal()

    if target_doc_id:
        docs = db.query(SourceDocument).filter_by(id=target_doc_id).all()
    else:
        docs = db.query(SourceDocument).filter_by(status="completed").all()

    if not docs:
        print("ℹ️ No hay documentos procesados disponibles.")
        db.close()
        return

    detector = CaseDetector()
    extractor = MetadataExtractor()

    print(f"⚖️ Procesando detección de casos y metadatos para {len(docs)} documentos...\n")

    for doc in docs:
        print(f"--------------------------------------------------")
        print(f"📄 Documento: {doc.filename} (Tipo: {doc.source_type}, Páginas: {doc.page_count})")

        cases = detector.detect_cases_in_document(db, str(doc.id))
        print(f"   -> Casos detectados: {len(cases)}")

        for idx, c in enumerate(cases, 1):
            extractor.process_case_metadata(db, str(c.id))
            print(f"   🔹 Caso #{idx}:")
            print(f"      - Número de Juicio/Recurso: {c.case_number or 'N/A'}")
            print(f"      - Número de Resolución:     {c.resolution_number or 'N/A'}")
            print(f"      - Rango de Páginas:         {c.page_start} - {c.page_end}")
            print(f"      - Materia Jurídica:         {c.legal_area}")
            print(f"      - Corte / Sala:             {c.court or 'N/A'} | {c.chamber or 'N/A'}")
            print(f"      - Juez Ponente:             {c.judge_rapporteur or 'N/A'}")

    db.close()


if __name__ == "__main__":
    doc_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    process_all_documents(doc_id_arg)
