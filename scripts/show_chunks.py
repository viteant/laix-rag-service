import sys
import pathlib
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.database.models import LegalCase, LegalChunk
from app.processing.section_detector import SectionDetector
from app.processing.chunker import TextChunker

Base.metadata.create_all(bind=engine)


def process_chunks_for_cases(target_case_id: str = None):
    db: Session = SessionLocal()

    if target_case_id:
        cases = db.query(LegalCase).filter_by(id=target_case_id).all()
    else:
        cases = db.query(LegalCase).all()

    if not cases:
        print("ℹ️ No hay casos jurídicos en la base de datos.")
        db.close()
        return

    sec_detector = SectionDetector()
    chunker = TextChunker()

    print(f"✂️ Procesando secciones y fragmentos (chunks) para {len(cases)} casos...\n")

    for idx, c in enumerate(cases, 1):
        sections = sec_detector.detect_sections(db, str(c.id))
        chunks = chunker.process_case_chunks(db, str(c.id))

        print(f"--------------------------------------------------")
        print(f"⚖️ Caso #{idx} (ID: {c.id})")
        print(f"   - Juicio / Recurso: {c.case_number or 'N/A'}")
        print(f"   - Materia:          {c.legal_area}")
        print(f"   - Secciones:        {len(sections)}")
        print(f"   - Chunks Generados: {len(chunks)}")

        for c_idx, chk in enumerate(chunks, 1):
            sample = chk.content[:120].replace("\n", " ")
            print(f"     🔹 Chunk #{c_idx} [{chk.token_count} tokens | Págs {chk.page_start}-{chk.page_end} | Sec: {chk.chunk_metadata.get('section_type')}]")
            print(f"        \"{sample}...\"")

    db.close()


if __name__ == "__main__":
    case_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    process_chunks_for_cases(case_id_arg)
