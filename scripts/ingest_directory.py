import sys
import argparse
import hashlib
import pathlib
from datetime import datetime
from typing import Optional
import fitz
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.core.config import settings
from app.database.models import SourceDocument, DocumentPage, LegalCase, LegalChunk
from app.extraction.pdf_extractor import PDFExtractor
from app.processing.text_cleaner import TextCleaner
from app.processing.document_builder import DocumentBuilder
from app.processing.case_detector import CaseDetector
from app.processing.metadata_extractor import MetadataExtractor
from app.processing.section_detector import SectionDetector
from app.processing.chunker import TextChunker
from app.retrieval.embedding_service import EmbeddingService
from app.core.email import send_alert_email


def calculate_sha256(filepath: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def process_single_pdf(db: Session, filepath: pathlib.Path, force: bool = False) -> bool:
    print(f"\n==================================================")
    print(f"📄 Procesando PDF: {filepath.name}")

    sha256_hash = calculate_sha256(filepath)
    filename = filepath.name

    source_type = "jurisprudence" if "jurisprudencia" in str(filepath).lower() else "document"

    existing_doc = db.query(SourceDocument).filter_by(sha256=sha256_hash).first()
    if existing_doc and existing_doc.status == "completed" and not force:
        print(f"ℹ️ Documento ya procesado anteriormente (SHA256: {sha256_hash[:10]}...). Omitiendo.")
        return False

    if not existing_doc:
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()

        existing_doc = SourceDocument(
            filename=filename,
            source_type=source_type,
            original_path=str(filepath),
            file_size=filepath.stat().st_size,
            sha256=sha256_hash,
            page_count=page_count,
            status="processing"
        )
        db.add(existing_doc)
        db.commit()
        db.refresh(existing_doc)
    else:
        existing_doc.status = "processing"
        existing_doc.original_path = str(filepath)
        db.commit()

    try:
        doc_id = str(existing_doc.id)

        # 1. Extracción y OCR (Limpiar páginas previas si force=True)
        print("   1/6 Extrayendo páginas y realizando OCR si es necesario...")
        db.query(DocumentPage).filter_by(source_document_id=existing_doc.id).delete()
        db.commit()

        extractor = PDFExtractor(db)
        extractor.extract_document(doc_id)

        # Limpiar texto en cada página
        pages = db.query(DocumentPage).filter_by(source_document_id=existing_doc.id).all()
        for p in pages:
            if p.raw_text:
                p.clean_text = TextCleaner.clean_text(p.raw_text)
        db.commit()

        # 2. Construcción de texto completo
        print("   2/6 Concatenando texto completo...")
        builder = DocumentBuilder()
        builder.build_full_document(db, doc_id)

        # 3. Detección de Casos
        print("   3/6 Detectando casos jurídicos y linderos de página...")
        case_detector = CaseDetector()
        cases = case_detector.detect_cases_in_document(db, doc_id)
        print(f"      -> Casos identificados: {len(cases)}")

        # 4. Extracción de Metadatos y Taxonomía
        print("   4/6 Extrayendo metadatos y materias...")
        metadata_extractor = MetadataExtractor()
        for c in cases:
            metadata_extractor.process_case_metadata(db, str(c.id))

        # 5. Secciones y Chunks
        print("   5/6 Segmentando secciones y generando chunks...")
        sec_detector = SectionDetector()
        chunker = TextChunker()

        total_chunks = []
        for c in cases:
            sec_detector.detect_sections(db, str(c.id))
            created_chunks = chunker.process_case_chunks(db, str(c.id))
            total_chunks.extend(created_chunks)

        print(f"      -> Chunks generados: {len(total_chunks)}")

        # 6. Embeddings Vectoriales
        print("   6/6 Calculando vectores de embeddings pgvector...")
        embedder = EmbeddingService()
        if total_chunks:
            texts = [chk.content for chk in total_chunks]
            vectors = embedder.embed_documents(texts)
            for chk, vec in zip(total_chunks, vectors):
                chk.embedding = vec
                chk.embedding_model = settings.EMBEDDING_MODEL
                chk.embedding_version = "1.0"
                chk.embedded_at = datetime.utcnow()
            db.commit()

        existing_doc.status = "completed"
        existing_doc.processed_at = datetime.utcnow()
        db.commit()

        print(f"✅ Ingesta completa de {filename} realizada con éxito.")
        return True

    except Exception as e:
        db.rollback()
        existing_doc.status = "failed"
        existing_doc.error_message = str(e)
        db.commit()
        print(f"❌ Error al ingerir {filename}: {e}")
        return False


def ingest_directory(source_dir: str, limit: Optional[int] = None, force: bool = False, retry_failed: bool = False):
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    dir_path = pathlib.Path(source_dir)

    if not dir_path.exists():
        print(f"❌ El directorio {source_dir} no existe.")
        db.close()
        return

    all_pdf_paths = list(dir_path.rglob("*.pdf")) + list(dir_path.rglob("*.PDF"))
    pdf_files = [f for f in all_pdf_paths if f.is_file()]
    print(f"🚀 Iniciando Pipeline de Ingesta sobre {len(pdf_files)} PDFs en {source_dir}...")

    if limit:
        pdf_files = pdf_files[:limit]
        print(f"ℹ️ Limite aplicado: se procesarán {len(pdf_files)} PDFs.")

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for pdf in pdf_files:
        res = process_single_pdf(db, pdf, force=force)
        if res:
            success_count += 1
        else:
            skipped_count += 1
        
        total_processed = success_count + skipped_count + failed_count
        if total_processed > 0 and total_processed % 1000 == 0:
            subject = f"Progreso de Ingesta: {total_processed} documentos procesados"
            body = (
                f"<h2>Reporte Parcial de Ingesta</h2>"
                f"<p>El daemon de inyección ha procesado <b>{total_processed}</b> documentos hasta ahora.</p>"
                f"<ul>"
                f"<li><b>Exitosos:</b> {success_count}</li>"
                f"<li><b>Omitidos/Ya procesados:</b> {skipped_count}</li>"
                f"<li><b>Fallidos:</b> {failed_count}</li>"
                f"</ul>"
                f"<p>Total pendientes en este lote: {len(pdf_files) - total_processed}</p>"
            )
            send_alert_email(subject, body)

    db.close()

    print("\n==================================================")
    print("📊 RESUMEN FINAL DE LA INGESTA EN LOTE:")
    print(f"  - Exitosos:   {success_count}")
    print(f"  - Omitidos:   {skipped_count}")
    print(f"  - Fallidos:   {failed_count}")
    print("==================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de Ingesta End-to-End para el RAG Jurídico")
    parser.add_argument("source_dir", type=str, help="Directorio raíz de PDFs a ingerir")
    parser.add_argument("--limit", type=int, default=None, help="Límite máximo de PDFs a procesar")
    parser.add_argument("--force", action="store_true", help="Forzar re-procesamiento de PDFs completados")
    parser.add_argument("--retry-failed", action="store_true", help="Re-procesar únicamente PDFs que hayan fallado")

    args = parser.parse_args()
    ingest_directory(args.source_dir, limit=args.limit, force=args.force, retry_failed=args.retry_failed)
