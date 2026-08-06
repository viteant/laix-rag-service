import pathlib
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from scripts.ingest_directory import process_single_pdf
from app.database.models import SourceDocument


@celery_app.task(name="app.tasks.ingest_tasks.ingest_source_document_task")
def ingest_source_document_task(document_id: str):
    db = SessionLocal()
    try:
        doc = db.query(SourceDocument).filter_by(id=document_id).first()
        if not doc:
            print(f"❌ SourceDocument with ID {document_id} not found in worker.")
            return {"status": "error", "message": "Document not found"}

        filepath = pathlib.Path(doc.original_path)
        if not filepath.exists():
            print(f"❌ File not found at path: {doc.original_path}")
            doc.status = "failed"
            doc.error_message = f"File not found: {doc.original_path}"
            db.commit()
            return {"status": "error", "message": "File not found"}

        result = process_single_pdf(db, filepath, force=True)
        return {"status": result, "document_id": document_id}

    finally:
        db.close()
