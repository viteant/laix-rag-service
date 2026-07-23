import os
import sys
import hashlib
import pathlib
import fitz  # PyMuPDF
from sqlalchemy.orm import Session

# Añadir el directorio raíz al path para poder importar app
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.database.models import SourceDocument, SourceType, DocumentStatus

# Asegurar tablas creadas
Base.metadata.create_all(bind=engine)


def calculate_sha256(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def evaluate_pdf_quality(filepath: str) -> tuple[int, bool, bool]:
    """
    Retorna (page_count, has_embedded_text, requires_ocr)
    Regla: Si menos del 60% de las páginas tiene al menos 100 caracteres legibles, requiere OCR.
    """
    doc = fitz.open(filepath)
    page_count = len(doc)
    if page_count == 0:
        doc.close()
        return 0, False, True

    sample_size = min(page_count, 10)
    step = max(1, page_count // sample_size)
    readable_pages = 0

    for i in range(0, page_count, step):
        page = doc[i]
        text = page.get_text("text").strip()
        # Consideramos legible si tiene al menos 100 caracteres de texto estructurado
        if len(text) >= 100:
            readable_pages += 1

    evaluated_pages = max(1, len(range(0, page_count, step)))
    ratio = readable_pages / evaluated_pages

    has_embedded_text = ratio >= 0.6
    requires_ocr = not has_embedded_text

    doc.close()
    return page_count, has_embedded_text, requires_ocr


def inventory_directory(base_dir: str):
    db: Session = SessionLocal()
    found_count = 0
    new_count = 0
    duplicate_count = 0
    ocr_required_count = 0
    embedded_text_count = 0

    print(f"🔍 Escaneando carpeta de origen: {base_dir}")

    source_folders = {
        os.path.join(base_dir, "documentos"): SourceType.DOCUMENT.value,
        os.path.join(base_dir, "jurisprudencia"): SourceType.JURISPRUDENCE.value,
        os.path.join(base_dir, "jurisprudencias"): SourceType.JURISPRUDENCE.value,
    }

    for folder_path, source_type in source_folders.items():
        if not os.path.exists(folder_path):
            print(f"⚠️ La carpeta {folder_path} no existe. Omitiendo...")
            continue

        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    found_count += 1
                    full_path = os.path.abspath(os.path.join(root, file))
                    file_size = os.path.getsize(full_path)
                    sha256 = calculate_sha256(full_path)

                    # Verificar si ya existe en BD por SHA-256
                    existing = db.query(SourceDocument).filter_by(sha256=sha256).first()
                    if existing:
                        duplicate_count += 1
                        print(f"  [Duplicado] {file} (SHA256 ya registrado: {sha256[:8]}...)")
                        continue

                    page_count, has_embedded_text, requires_ocr = evaluate_pdf_quality(full_path)

                    doc_entry = SourceDocument(
                        source_type=source_type,
                        filename=file,
                        original_path=full_path,
                        sha256=sha256,
                        file_size=file_size,
                        page_count=page_count,
                        has_embedded_text=has_embedded_text,
                        requires_ocr=requires_ocr,
                        status=DocumentStatus.PENDING.value,
                    )
                    db.add(doc_entry)
                    db.commit()

                    new_count += 1
                    if requires_ocr:
                        ocr_required_count += 1
                    else:
                        embedded_text_count += 1

                    ocr_status_str = "Requiere OCR" if requires_ocr else "Texto embebido"
                    print(f"  [Nuevo] {file} ({page_count} pgs, {ocr_status_str}, {file_size} bytes)")

    db.close()
    print("\n--- Resumen de Inventario ---")
    print(f"Encontrados: {found_count} PDFs")
    print(f"Nuevos: {new_count}")
    print(f"Duplicados: {duplicate_count}")
    print(f"Requieren OCR: {ocr_required_count}")
    print(f"Texto Embebido: {embedded_text_count}")


if __name__ == "__main__":
    base_data_path = os.getenv("DATA_SOURCE_PATH", "data/source")
    inventory_directory(base_data_path)
