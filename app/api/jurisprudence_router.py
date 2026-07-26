from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.retrieval.hybrid_search import HybridSearch
from app.generation.jurisprudence_answer import JurisprudenceAnswerGenerator
from app.database.models import LegalCase, SourceDocument, LegalChunk, DocumentPage

from app.core.security import get_current_system

router = APIRouter(prefix="/v1/jurisprudence", tags=["Jurisprudencia"])


class SearchFilters(BaseModel):
    legal_area: Optional[str] = Field(default=None, description="Filtro por materia/área jurídica (ej: Contencioso Tributario, Laboral y Social)")
    case_number: Optional[str] = Field(default=None, description="Filtro por número de juicio o recurso (ej: 319-2011)")
    source_type: Optional[str] = Field(default=None, description="Filtro por tipo de fuente: 'jurisprudence' (Criterios/Precedentes vinculantes) o 'document' (Fallos/Sentencias particulares)")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Pregunta o consulta en lenguaje natural")
    filters: Optional[SearchFilters] = Field(default=None, description="Filtros opcionales por materia, tipo de fuente o expediente")
    limit: int = Field(default=10, ge=1, le=50, description="Número de resultados a devolver")


class AnswerRequest(BaseModel):
    query: str = Field(..., description="Pregunta jurídica en lenguaje natural")
    filters: Optional[SearchFilters] = Field(default=None, description="Filtros opcionales por materia o tipo de fuente")
    top_k: int = Field(default=5, ge=1, le=20, description="Número de fuentes a considerar en la respuesta")


@router.post("/search", dependencies=[Depends(get_current_system)])
def search_jurisprudence(req: SearchRequest, db: Session = Depends(get_db)):
    filters_dict = req.filters.model_dump(exclude_none=True) if req.filters else None
    searcher = HybridSearch(db)
    results = searcher.search(query=req.query, limit=req.limit, filters=filters_dict)
    return {
        "query": req.query,
        "count": len(results),
        "results": results
    }


@router.post("/answer", dependencies=[Depends(get_current_system)])
def generate_jurisprudence_answer(req: AnswerRequest, db: Session = Depends(get_db)):
    filters_dict = req.filters.model_dump(exclude_none=True) if req.filters else None
    generator = JurisprudenceAnswerGenerator(db)
    response = generator.generate_answer(query=req.query, filters=filters_dict, top_k=req.top_k)
    return response


@router.get("/cases/{case_id}", dependencies=[Depends(get_current_system)])
def get_case_details(case_id: str, db: Session = Depends(get_db)):
    legal_case = db.query(LegalCase).filter_by(id=case_id).first()
    if not legal_case:
        raise HTTPException(status_code=404, detail=f"LegalCase con ID {case_id} no encontrado")

    source_doc = db.query(SourceDocument).filter_by(id=legal_case.source_document_id).first()
    chunks = db.query(LegalChunk).filter_by(legal_case_id=legal_case.id).order_by(LegalChunk.page_start).all()

    return {
        "case_id": str(legal_case.id),
        "source_document_id": str(legal_case.source_document_id),
        "source_type": source_doc.source_type if source_doc else "unknown",
        "filename": source_doc.filename if source_doc else None,
        "case_number": legal_case.case_number,
        "resolution_number": legal_case.resolution_number,
        "legal_area": legal_case.legal_area,
        "court": legal_case.court,
        "chamber": legal_case.chamber,
        "judge_rapporteur": legal_case.judge_rapporteur,
        "decision_date": legal_case.decision_date,
        "city": legal_case.city,
        "summary": legal_case.summary,
        "page_start": legal_case.page_start,
        "page_end": legal_case.page_end,
        "chunks_count": len(chunks),
        "case_metadata": legal_case.case_metadata,
    }


@router.get("/documents/{document_id}", dependencies=[Depends(get_current_system)])
def get_document_details(document_id: str, db: Session = Depends(get_db)):
    source_doc = db.query(SourceDocument).filter_by(id=document_id).first()
    if not source_doc:
        raise HTTPException(status_code=404, detail=f"SourceDocument con ID {document_id} no encontrado")

    cases = db.query(LegalCase).filter_by(source_document_id=source_doc.id).all()

    return {
        "document_id": str(source_doc.id),
        "filename": source_doc.filename,
        "source_type": source_doc.source_type,
        "sha256": source_doc.sha256,
        "page_count": source_doc.page_count,
        "requires_ocr": source_doc.requires_ocr,
        "status": source_doc.status,
        "created_at": source_doc.created_at,
        "cases_detected": len(cases),
        "cases": [
            {
                "case_id": str(c.id),
                "case_number": c.case_number,
                "legal_area": c.legal_area,
                "page_start": c.page_start,
                "page_end": c.page_end
            } for c in cases
        ]
    }
