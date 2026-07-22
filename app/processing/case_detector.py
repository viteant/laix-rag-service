import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.database.models import SourceDocument, DocumentPage, LegalCase


class CaseMatch:
    def __init__(self, page_number: int, case_number: str = None, resolution_number: str = None, header_title: str = None):
        self.page_number = page_number
        self.case_number = case_number
        self.resolution_number = resolution_number
        self.header_title = header_title


class CaseDetector:
    # Patrones regex para detectar encabezados de juicios/recursos/resoluciones
    CASE_PATTERNS = [
        re.compile(r'JUICIO\s+(?:No\.|N°|Nº)\s*:?\s*([\d\w-]+)', re.IGNORECASE),
        re.compile(r'RECURSO\s+(?:No\.|N°|Nº)\s*:?\s*([\d\w-]+)', re.IGNORECASE),
        re.compile(r'RESOLUCIÓN\s+(?:No\.|N°|Nº)\s*:?\s*([\d\w-]+)', re.IGNORECASE),
        re.compile(r'CORTE\s+NACIONAL\s+DE\s+JUSTICIA', re.IGNORECASE),
        re.compile(r'SALA\s+ESPECIALIZADA', re.IGNORECASE),
    ]

    def detect_cases_in_document(self, db: Session, source_doc_id: str) -> List[LegalCase]:
        source_doc = db.query(SourceDocument).filter_by(id=source_doc_id).first()
        if not source_doc:
            raise ValueError(f"SourceDocument with ID {source_doc_id} not found")

        pages = db.query(DocumentPage).filter_by(source_document_id=source_doc.id).order_by(DocumentPage.page_number).all()
        if not pages:
            return []

        # 1. Escanear páginas en busca de inicios de caso
        matches: List[CaseMatch] = []
        for page in pages:
            text = page.clean_text or page.raw_text or ""

            case_num = None
            res_num = None

            # Buscar número de juicio o recurso
            m_juicio = re.search(r'(?:JUICIO|RECURSO)\s+(?:No\.|N°|Nº)\s*:?\s*([\d\w-]+)', text, re.IGNORECASE)
            if m_juicio:
                case_num = m_juicio.group(1).strip()

            # Buscar número de resolución
            m_res = re.search(r'RESOLUCIÓN\s+(?:No\.|N°|Nº)\s*:?\s*([\d\w-]+)', text, re.IGNORECASE)
            if m_res:
                res_num = m_res.group(1).strip()

            # Si detectamos un inicio explícito de caso en esta página
            if case_num or res_num or ("CORTE NACIONAL" in text.upper() and page.page_number == 1):
                # Evitar duplicar el mismo match en páginas consecutivas si ya es del mismo caso
                if not matches or matches[-1].case_number != case_num or matches[-1].page_number != page.page_number:
                    matches.append(CaseMatch(
                        page_number=page.page_number,
                        case_number=case_num,
                        resolution_number=res_num,
                        header_title=text[:100]
                    ))

        # 2. Si no se detectaron cortes específicos, tratar todo el PDF como 1 caso
        if not matches:
            matches.append(CaseMatch(page_number=1))

        # 3. Construir rangos de páginas (page_start, page_end)
        total_pages = len(pages)
        created_cases = []

        # Eliminar casos previos existentes para este documento (re-procesamiento idéntico)
        db.query(LegalCase).filter_by(source_document_id=source_doc.id).delete()

        for i, match in enumerate(matches):
            page_start = match.page_number
            if i + 1 < len(matches):
                # El final del caso actual es la página anterior al inicio del siguiente caso
                page_end = max(page_start, matches[i + 1].page_number - 1)
            else:
                page_end = total_pages

            legal_case = LegalCase(
                source_document_id=source_doc.id,
                case_number=match.case_number,
                resolution_number=match.resolution_number,
                page_start=page_start,
                page_end=page_end,
            )
            db.add(legal_case)
            created_cases.append(legal_case)

        db.commit()

        # Refrescar objetos creados
        for case in created_cases:
            db.refresh(case)

        return created_cases
