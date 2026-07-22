import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.database.models import LegalCase, DocumentPage, LegalSection


class SectionDetector:
    SECTION_TYPES = {
        "summary": ["SÍNTESIS", "RESUMEN", "SINTESIS"],
        "background": ["ANTECEDENTES", "VISTOS", "RELACIÓN DE HECHOS", "RELACION DE HECHOS"],
        "first_instance": ["PRIMERA INSTANCIA", "JUZGADO DE ORIGEN"],
        "second_instance": ["SEGUNDA INSTANCIA", "CORTE PROVINCIAL"],
        "cassation": ["RECURSO DE CASACIÓN", "RECURSO DE CASACION", "IMPUGNACIÓN", "IMPUGNACION"],
        "arguments": ["ARGUMENTOS", "ALEGACIONES", "FUNDAMENTOS DEL RECURSO"],
        "legal_analysis": ["CONSIDERANDO", "ANÁLISIS JURÍDICO", "ANALISIS JURIDICO", "PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO"],
        "decision": ["RESUELVE", "DECISIÓN", "DECISION", "ADMINISTRANDO JUSTICIA", "FALLO"],
    }

    def detect_sections(self, db: Session, case_id: str) -> List[LegalSection]:
        legal_case = db.query(LegalCase).filter_by(id=case_id).first()
        if not legal_case:
            raise ValueError(f"LegalCase with ID {case_id} not found")

        pages = db.query(DocumentPage).filter(
            DocumentPage.source_document_id == legal_case.source_document_id,
            DocumentPage.page_number >= legal_case.page_start,
            DocumentPage.page_number <= legal_case.page_end
        ).order_by(DocumentPage.page_number).all()

        if not pages:
            return []

        # Eliminar secciones previas
        db.query(LegalSection).filter_by(legal_case_id=legal_case.id).delete()

        sections_found = []
        position = 1

        for p in pages:
            text = p.clean_text or p.raw_text or ""
            if not text.strip():
                continue

            # Buscar coincidencias de títulos de sección en la página
            lines = text.split("\n")
            current_section_type = "other"
            current_title = "Sección General"
            buffer_lines = []

            for line in lines:
                line_clean = line.strip().upper()
                detected_type = None

                for sec_type, keywords in self.SECTION_TYPES.items():
                    for kw in keywords:
                        if kw in line_clean:
                            detected_type = sec_type
                            current_title = line.strip()
                            break
                    if detected_type:
                        break

                if detected_type and detected_type != current_section_type:
                    # Guardar la sección anterior si acumuló contenido
                    if buffer_lines:
                        content = "\n".join(buffer_lines).strip()
                        if content:
                            sec = LegalSection(
                                legal_case_id=legal_case.id,
                                section_type=current_section_type,
                                title=current_title,
                                page_start=p.page_number,
                                page_end=p.page_number,
                                content=content,
                                position=position
                            )
                            db.add(sec)
                            sections_found.append(sec)
                            position += 1
                        buffer_lines = []

                    current_section_type = detected_type

                buffer_lines.append(line)

            # Guardar remanente de la página
            if buffer_lines:
                content = "\n".join(buffer_lines).strip()
                if content:
                    sec = LegalSection(
                        legal_case_id=legal_case.id,
                        section_type=current_section_type,
                        title=current_title,
                        page_start=p.page_number,
                        page_end=p.page_number,
                        content=content,
                        position=position
                    )
                    db.add(sec)
                    sections_found.append(sec)
                    position += 1

        db.commit()
        for sec in sections_found:
            db.refresh(sec)
        return sections_found
