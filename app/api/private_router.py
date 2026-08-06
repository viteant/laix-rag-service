import hashlib
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_system
from app.database.models import DocumentPage, LegalCase, LegalChunk, SourceDocument
from app.generation.llm_client import LlmClient, LlmGenerationError
from app.storage.private_document_storage import PrivateDocumentNotFoundError, PrivateDocumentStorage

router = APIRouter(prefix="/v1/private", tags=["Documentos privados de casos"])

IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")

SUMMARY_SYSTEM_PROMPT = (
    "Eres un asistente jurídico. Resume, en español y en un máximo de 5 párrafos, "
    "el contenido de los documentos de un caso legal para que un abogado entienda "
    "rápidamente de qué trata. Basa el resumen ÚNICAMENTE en el texto provisto. No "
    "inventes hechos, fechas ni nombres que no aparezcan en el texto."
)


class RegisterPrivateDocumentRequest(BaseModel):
    tenant_id: str = Field(..., description="Identificador del despacho/tenant")
    matter_id: str = Field(..., description="Identificador del asunto en el CRM")
    r2_key: str = Field(..., description="Clave del objeto en el bucket R2 privado")


class MatterSummaryRequest(BaseModel):
    tenant_id: str = Field(..., description="Identificador del despacho/tenant")


def _validate_identifier(value: str, field: str) -> None:
    if not IDENTIFIER_PATTERN.match(value):
        raise HTTPException(status_code=422, detail=f"{field} inválido")


def tag_documents_with_scope(
    db: Session,
    source_document_id,
    tenant_id: str,
    matter_id: str,
    r2_key: Optional[str] = None
) -> int:
    """Stamps tenant_id/matter_id (and the R2 key, for later deletion) on
    every LegalCase/LegalChunk produced for a just-ingested SourceDocument,
    so later retrieval can be scoped to a single case's own private
    documents. Returns the number of chunks tagged.
    """
    cases = db.query(LegalCase).filter_by(source_document_id=source_document_id).all()
    for case in cases:
        case.case_metadata = {
            **(case.case_metadata or {}),
            "tenant_id": tenant_id,
            "matter_id": matter_id,
            **({"r2_key": r2_key} if r2_key else {}),
        }

    case_ids = [case.id for case in cases]
    chunks = (
        db.query(LegalChunk).filter(LegalChunk.legal_case_id.in_(case_ids)).all()
        if case_ids else []
    )
    for chunk in chunks:
        chunk.chunk_metadata = {**(chunk.chunk_metadata or {}), "tenant_id": tenant_id, "matter_id": matter_id}

    db.commit()
    return len(chunks)


@router.post("/documents", dependencies=[Depends(get_current_system)])
def register_private_document(req: RegisterPrivateDocumentRequest, db: Session = Depends(get_db)):
    # Imported lazily: pulls in the heavy extraction/embedding stack, which we
    # don't want to load just to answer a validation error.
    from scripts.ingest_directory import process_single_pdf

    _validate_identifier(req.tenant_id, "tenant_id")
    _validate_identifier(req.matter_id, "matter_id")

    storage = PrivateDocumentStorage()
    try:
        local_path = storage.download_to_temp(req.r2_key)
    except PrivateDocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))

    try:
        hasher = hashlib.sha256()
        with open(local_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        sha256_hash = hasher.hexdigest()

        result = process_single_pdf(db, local_path, force=True)
        source_document = db.query(SourceDocument).filter_by(sha256=sha256_hash).first()

        tagged_chunks = 0
        if source_document and result in {"success", "skipped"}:
            tagged_chunks = tag_documents_with_scope(
                db, source_document.id, req.tenant_id, req.matter_id, r2_key=req.r2_key
            )

        return {
            "message": "Documento privado registrado y procesado.",
            "document_id": str(source_document.id) if source_document else None,
            "status": result,
            "chunks_tagged": tagged_chunks,
        }
    finally:
        local_path.unlink(missing_ok=True)


@router.delete("/documents/{document_id}", dependencies=[Depends(get_current_system)])
def delete_private_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(SourceDocument).filter_by(id=document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Documento con ID {document_id} no encontrado")

    r2_key: Optional[str] = None
    for case in document.legal_cases:
        r2_key = r2_key or (case.case_metadata or {}).get("r2_key")

    db.query(DocumentPage).filter_by(source_document_id=document.id).delete()
    db.delete(document)  # cascades to LegalCase -> LegalSection/LegalChunk
    db.commit()

    if r2_key:
        PrivateDocumentStorage().delete(r2_key)

    return {"message": "Documento privado eliminado.", "document_id": document_id}


@router.post("/matters/{matter_id}/summary", dependencies=[Depends(get_current_system)])
def summarize_matter_documents(matter_id: str, req: MatterSummaryRequest, db: Session = Depends(get_db)):
    _validate_identifier(req.tenant_id, "tenant_id")
    _validate_identifier(matter_id, "matter_id")

    chunks = (
        db.query(LegalChunk)
        .filter(
            LegalChunk.chunk_metadata["tenant_id"].astext == req.tenant_id,
            LegalChunk.chunk_metadata["matter_id"].astext == matter_id,
        )
        .order_by(LegalChunk.legal_case_id, LegalChunk.page_start)
        .all()
    )

    if not chunks:
        return {
            "matter_id": matter_id,
            "summary": "Este asunto todavía no tiene documentos procesados para resumir.",
            "documents_used": 0,
        }

    llm_client = LlmClient()
    if not llm_client.enabled:
        return {
            "matter_id": matter_id,
            "summary": "El resumen automático no está disponible en este momento.",
            "documents_used": len({chunk.legal_case_id for chunk in chunks}),
        }

    content = "\n\n".join(chunk.content for chunk in chunks)[:settings.LLM_ANSWER_MAX_CONTEXT_CHARS]

    try:
        summary = llm_client.generate(
            SUMMARY_SYSTEM_PROMPT,
            f"Documentos del asunto:\n\n{content}"
        )
    except LlmGenerationError as error:
        raise HTTPException(status_code=502, detail=f"No se pudo generar el resumen: {error}")

    return {
        "matter_id": matter_id,
        "summary": summary,
        "documents_used": len({chunk.legal_case_id for chunk in chunks}),
    }
