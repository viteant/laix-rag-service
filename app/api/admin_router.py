import hashlib
import pathlib
import fitz
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.database.models import SourceDocument, LegalCase, DocumentPage
from app.tasks.ingest_tasks import ingest_source_document_task

security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/v1/admin", tags=["Administración e Ingesta"])


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
    if settings.SERVICE_API_TOKEN:
        if not credentials or credentials.credentials != settings.SERVICE_API_TOKEN:
            raise HTTPException(status_code=401, detail="Token de autorización inválido o ausente.")
    return True


class RegisterDocumentRequest(BaseModel):
    filepath: str = Field(..., description="Ruta absoluta al archivo PDF en disco")
    source_type: Optional[str] = Field(default="document", description="Tipo de fuente: 'jurisprudence' o 'document'")


@router.post("/documents", dependencies=[Depends(verify_token)])
def register_and_ingest_document(req: RegisterDocumentRequest, db: Session = Depends(get_db)):
    path = pathlib.Path(req.filepath)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=400, detail=f"El archivo no existe en la ruta: {req.filepath}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256_hash = hasher.hexdigest()

    existing = db.query(SourceDocument).filter_by(sha256=sha256_hash).first()
    if existing and existing.status == "completed":
        return {
            "message": "El documento ya fue ingerido previamente.",
            "document_id": str(existing.id),
            "status": existing.status
        }

    if not existing:
        doc = fitz.open(path)
        page_count = len(doc)
        doc.close()

        existing = SourceDocument(
            filename=path.name,
            source_type=req.source_type,
            filepath=str(path),
            file_size_bytes=path.stat().st_size,
            sha256=sha256_hash,
            page_count=page_count,
            status="queued"
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

    # Enviar tarea a Celery Worker en Redis
    try:
        task_res = ingest_source_document_task.delay(str(existing.id))
        task_id = task_res.id
    except Exception:
        # Fallback a procesamiento síncrono si Celery no estuviera corriendo
        task_id = "sync_fallback"

    return {
        "message": "Documento registrado y encolado para procesamiento.",
        "document_id": str(existing.id),
        "filename": existing.filename,
        "status": existing.status,
        "task_id": task_id
    }


@router.get("/documents/{document_id}/status", dependencies=[Depends(verify_token)])
def get_ingestion_status(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(SourceDocument).filter_by(id=document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento con ID {document_id} no encontrado")

    cases_count = db.query(LegalCase).filter_by(source_document_id=doc.id).count()
    pages_count = db.query(DocumentPage).filter_by(source_document_id=doc.id).count()

    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status,
        "source_type": doc.source_type,
        "pages_extracted": pages_count,
        "cases_detected": cases_count,
        "processed_at": doc.processed_at,
        "error_message": doc.error_message
    }
