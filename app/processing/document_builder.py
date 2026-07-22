import os
import pathlib
from sqlalchemy.orm import Session
from app.database.models import DocumentPage, SourceDocument


class DocumentBuilder:
    def __init__(self, processed_base_dir: str = "data/processed"):
        self.processed_base_dir = processed_base_dir

    def build_full_document(self, db: Session, source_doc_id: str) -> str:
        source_doc = db.query(SourceDocument).filter_by(id=source_doc_id).first()
        if not source_doc:
            raise ValueError(f"SourceDocument with ID {source_doc_id} not found")

        pages = db.query(DocumentPage).filter_by(source_document_id=source_doc.id).order_by(DocumentPage.page_number).all()

        full_text_parts = []
        for page in pages:
            text_content = page.clean_text if page.clean_text else (page.raw_text or "")
            full_text_parts.append(f"[[PAGE:{page.page_number}]]\n{text_content}")

        full_text = "\n\n".join(full_text_parts)

        # Crear directorio de salida
        doc_dir = os.path.join(self.processed_base_dir, str(source_doc.id))
        os.makedirs(doc_dir, exist_ok=True)

        output_path = os.path.join(doc_dir, "full_text.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        print(f"📄 Documento completo guardado en: {output_path}")
        return output_path
