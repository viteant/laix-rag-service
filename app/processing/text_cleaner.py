import re
from sqlalchemy.orm import Session
from app.database.models import SourceDocument, DocumentPage, DocumentStatus


class TextCleaner:
    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""

        # 1. Normalizar caracteres nulos y no imprimibles raros (manteniendo saltos de línea y tabuladores)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # 2. Unir palabras partidas al final de línea con guion (ej: "admi-\nnistración" -> "administración")
        cleaned = re.sub(r'(\b\w+)-\s*\n\s*(\w+\b)', r'\1\2', cleaned)

        # 3. Reemplazar tabulaciones por espacios
        cleaned = cleaned.replace('\t', ' ')

        # 4. Normalizar espacios en blanco horizontales (pero no saltos de línea)
        cleaned = re.sub(r'[^\S\r\n]+', ' ', cleaned)

        # 5. Reducir saltos de línea excesivos (más de 2 consecutivos a máximo 2)
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)

        # 6. Limpiar espacios al inicio/final de cada línea
        lines = [line.strip() for line in cleaned.splitlines()]
        cleaned = '\n'.join(lines)

        return cleaned.strip()

    def process_document_pages(self, db: Session, source_doc_id: str):
        pages = db.query(DocumentPage).filter_by(source_document_id=source_doc_id).order_by(DocumentPage.page_number).all()
        for page in pages:
            if page.raw_text:
                page.clean_text = self.clean_text(page.raw_text)

        source_doc = db.query(SourceDocument).filter_by(id=source_doc_id).first()
        if source_doc:
            source_doc.status = DocumentStatus.COMPLETED.value
        db.commit()
