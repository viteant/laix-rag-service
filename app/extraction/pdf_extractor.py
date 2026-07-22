import os
import tempfile
import subprocess
from typing import List, Dict, Any
import fitz  # PyMuPDF
from PIL import Image
import io
from sqlalchemy.orm import Session

from app.database.models import SourceDocument, DocumentPage, ExtractionMethod, DocumentStatus


def run_tesseract_on_image(image_bytes: bytes, lang: str = "spa") -> str:
    """
    Ejecuta tesseract por CLI sobre la imagen de una página.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
        tmp_img.write(image_bytes)
        tmp_img_path = tmp_img.name

    try:
        cmd = ["tesseract", tmp_img_path, "stdout", "-l", lang, "--oem", "1"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"Error ejecutando tesseract en imagen: {e}")
        return ""
    finally:
        if os.path.exists(tmp_img_path):
            os.remove(tmp_img_path)


class PDFExtractor:
    def __init__(self, db_session: Session):
        self.db = db_session

    def extract_document(self, doc_id: str) -> SourceDocument:
        source_doc = self.db.query(SourceDocument).filter_by(id=doc_id).first()
        if not source_doc:
            raise ValueError(f"SourceDocument with ID {doc_id} not found")

        source_doc.status = DocumentStatus.EXTRACTING.value
        self.db.commit()

        try:
            pdf_path = source_doc.original_path
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")

            fitz_doc = fitz.open(pdf_path)

            for page_num in range(len(fitz_doc)):
                page = fitz_doc[page_num]
                page_1_indexed = page_num + 1

                # Intentar texto embebido
                embedded_text = page.get_text("text").strip()

                if len(embedded_text) >= 100 and not source_doc.requires_ocr:
                    # Texto embebido de buena calidad
                    raw_text = embedded_text
                    method = ExtractionMethod.EMBEDDED_TEXT.value
                    confidence = 1.0
                else:
                    # Aplicar OCR a la página
                    pix = page.get_pixmap(dpi=300)
                    img_bytes = pix.tobytes("png")
                    ocr_text = run_tesseract_on_image(img_bytes, lang="spa")

                    if len(ocr_text) > len(embedded_text):
                        raw_text = ocr_text
                        method = ExtractionMethod.OCR.value
                        confidence = 0.85
                    else:
                        raw_text = embedded_text
                        method = ExtractionMethod.EMBEDDED_TEXT.value
                        confidence = 0.70

                # Guardar página en BD
                doc_page = DocumentPage(
                    source_document_id=source_doc.id,
                    page_number=page_1_indexed,
                    raw_text=raw_text,
                    clean_text=None,  # Se llenará en la etapa de limpieza
                    extraction_method=method,
                    ocr_confidence=confidence,
                )
                self.db.add(doc_page)

            fitz_doc.close()

            source_doc.status = DocumentStatus.PROCESSING.value
            self.db.commit()
            return source_doc

        except Exception as e:
            source_doc.status = DocumentStatus.FAILED.value
            source_doc.error_message = str(e)
            self.db.commit()
            raise e
