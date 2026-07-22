import re
from typing import Optional, List
from sqlalchemy.orm import Session

from app.database.models import LegalCase, DocumentPage, SourceDocument
from app.models.metadata_schemas import LegalCaseMetadata
from app.models.legal_taxonomy import LEGAL_AREAS


class MetadataExtractor:
    @staticmethod
    def extract_metadata_from_text(text: str) -> LegalCaseMetadata:
        if not text:
            return LegalCaseMetadata()

        # 1. Juez Ponente
        judge = None
        m_judge = re.search(r'Juez\s+Ponente\s*:?\s*([^\n,;]+)', text, re.IGNORECASE)
        if m_judge:
            judge = m_judge.group(1).strip()

        # 2. Tribunal / Corte
        court = None
        if "CORTE NACIONAL DE JUSTICIA" in text.upper():
            court = "Corte Nacional de Justicia"
        elif "CORTE SUPREMA DE JUSTICIA" in text.upper():
            court = "Corte Suprema de Justicia"
        elif "TRIBUNAL DISTRITAL" in text.upper():
            court = "Tribunal Distrital"

        # 3. Sala
        chamber = None
        m_chamber = re.search(r'(SALA\s+ESPECIALIZADA\s+DE\s+[^\n\.,;]+|SALA\s+DE\s+LO\s+[^\n\.,;]+)', text, re.IGNORECASE)
        if m_chamber:
            chamber = m_chamber.group(1).strip()

        # 4. Ciudad y Fecha
        city = None
        date_str = None
        m_city_date = re.search(r'(Quito|Guayaquil|Cuenca)\s*,?\s*(\d{1,2}\s+de\s+[a-zA-Z]+\s+de\s+\d{4}|\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
        if m_city_date:
            city = m_city_date.group(1).capitalize()
            date_str = m_city_date.group(2).strip()

        # 5. Asunto o Acción Específica
        asunto = None
        m_asunto = re.search(r'(?:ASUNTO|MATERIA|JUICIO\s+POR)\s*:?\s*([^\n\.,;]+)', text, re.IGNORECASE)
        if m_asunto:
            asunto = m_asunto.group(1).strip()

        # 6. Materia / Área Judicial Principal
        text_lower = text.lower()
        legal_area = "Otros"
        if "tributari" in text_lower or "sri" in text_lower or "rentas internas" in text_lower:
            legal_area = "Contencioso Tributario"
        elif "laboral" in text_lower or "trabajador" in text_lower or "despido" in text_lower:
            legal_area = "Laboral y Social"
        elif "familia" in text_lower or "paternidad" in text_lower or "adn" in text_lower or "niñez" in text_lower:
            legal_area = "Familia, Niñez, Adolescencia y Adolescentes Infractores"
        elif "penal" in text_lower or "delito" in text_lower or "tránsito" in text_lower:
            legal_area = "Penal, Militar, Policial y Tránsito"
        elif "administrativ" in text_lower:
            legal_area = "Contencioso Administrativo"
        elif "constitucional" in text_lower:
            legal_area = "Constitucional"
        elif "civil" in text_lower or "mercantil" in text_lower or "contrato" in text_lower:
            legal_area = "Civil y Mercantil"

        # 7. Tipo de Acción / Recurso
        action_type = None
        if "recurso de casación" in text_lower or "casacion" in text_lower:
            action_type = "recurso de casación"
        elif "recurso de revisión" in text_lower:
            action_type = "recurso de revisión"
        elif "contrato" in text_lower:
            action_type = "contrato"

        # 8. Resumen inicial
        summary = text[:300].strip().replace("\n", " ") + "..." if len(text) > 300 else text.strip()

        # 9. Extraer Temas / Topics
        topics = []
        possible_topics = ["paternidad", "adn", "pago indebido", "recurso de revisión", "inadmisión", "despido intempestivo", "cosa juzgada", "contrato", "silencio administrativo", "nulidad de contrato"]
        for t in possible_topics:
            if t in text_lower:
                topics.append(t)

        return LegalCaseMetadata(
            court=court,
            chamber=chamber,
            judge_rapporteur=judge,
            decision_date=date_str,
            city=city,
            legal_area=legal_area,
            asunto=asunto,
            action_type=action_type,
            procedural_stage="casación" if "casaci" in text_lower else None,
            summary=summary,
            topics=topics
        )

    def process_case_metadata(self, db: Session, case_id: str) -> LegalCase:
        legal_case = db.query(LegalCase).filter_by(id=case_id).first()
        if not legal_case:
            raise ValueError(f"LegalCase with ID {case_id} not found")

        pages = db.query(DocumentPage).filter(
            DocumentPage.source_document_id == legal_case.source_document_id,
            DocumentPage.page_number >= legal_case.page_start,
            DocumentPage.page_number <= legal_case.page_end
        ).order_by(DocumentPage.page_number).all()

        case_text = "\n".join([p.clean_text or p.raw_text or "" for p in pages])

        extracted = self.extract_metadata_from_text(case_text)

        if extracted.court:
            legal_case.court = extracted.court
        if extracted.chamber:
            legal_case.chamber = extracted.chamber
        if extracted.judge_rapporteur:
            legal_case.judge_rapporteur = extracted.judge_rapporteur
        if extracted.decision_date:
            legal_case.decision_date = extracted.decision_date
        if extracted.city:
            legal_case.city = extracted.city

        legal_case.legal_area = extracted.legal_area
        legal_case.action_type = extracted.action_type
        legal_case.procedural_stage = extracted.procedural_stage
        legal_case.summary = extracted.summary
        legal_case.case_metadata = extracted.model_dump()

        db.commit()
        db.refresh(legal_case)
        return legal_case
