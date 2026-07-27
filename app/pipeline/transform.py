import subprocess
import tempfile
from pathlib import Path

import fitz
from sqlalchemy.orm import Session

from app.pipeline.downloader import sha256_file
from app.pipeline.models import PipelineAssetStatus, PipelineRunAsset
from app.processing.text_cleaner import TextCleaner


class TransformError(RuntimeError):
    pass


class TransformService:
    """Creates a compressed PDF and its canonical TXT before remote upload."""

    def __init__(self, db: Session, work_root: Path = Path("data/work"), text_root: Path = Path("data/text")):
        self.db = db
        self.work_root = work_root
        self.text_root = text_root

    def optimized_path_for(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        source = asset.source
        return self.work_root / str(run_asset.pipeline_run_id) / source.source_type / source.source_subtype / "optimized" / asset.canonical_filename

    def text_path_for(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        source = asset.source
        return self.text_root / source.source_type / source.source_subtype / Path(asset.canonical_filename).with_suffix(".txt").name

    def optimize(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        if not asset.downloaded_pdf_path:
            raise TransformError("A downloaded PDF is required before optimization")
        input_path = Path(asset.downloaded_pdf_path)
        if not input_path.is_file():
            raise TransformError(f"Downloaded PDF is missing: {input_path}")

        output_path = self.optimized_path_for(run_asset)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".part.pdf")
        temporary.unlink(missing_ok=True)
        try:
            with fitz.open(input_path) as original:
                original_pages = len(original)
                original.save(temporary, garbage=4, deflate=True, clean=True)
            with fitz.open(temporary) as optimized:
                if len(optimized) != original_pages:
                    raise TransformError("PDF optimization changed the page count")
            temporary.replace(output_path)
            asset.optimized_pdf_path = str(output_path)
            asset.optimized_sha256 = sha256_file(output_path)
            asset.status = PipelineAssetStatus.OPTIMIZED.value
            run_asset.status = PipelineAssetStatus.OPTIMIZED.value
            return output_path
        except Exception as error:
            temporary.unlink(missing_ok=True)
            asset.status = PipelineAssetStatus.FAILED.value
            asset.error_message = str(error)
            run_asset.status = PipelineAssetStatus.FAILED.value
            run_asset.detail = str(error)
            raise

    @staticmethod
    def _ocr_page(page: fitz.Page) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            image_file.write(page.get_pixmap(dpi=300).tobytes("png"))
            image_file.flush()
            result = subprocess.run(
                ["tesseract", image_file.name, "stdout", "-l", "spa", "--oem", "1"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()

    def extract_text(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        if not asset.optimized_pdf_path:
            raise TransformError("An optimized PDF is required before text extraction")
        pdf_path = Path(asset.optimized_pdf_path)
        if not pdf_path.is_file():
            raise TransformError(f"Optimized PDF is missing: {pdf_path}")

        output_path = self.text_path_for(run_asset)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".part.txt")
        temporary.unlink(missing_ok=True)
        try:
            pages = []
            with fitz.open(pdf_path) as document:
                for index, page in enumerate(document, start=1):
                    embedded_text = page.get_text("text").strip()
                    raw_text = embedded_text if len(embedded_text) >= 100 else self._ocr_page(page) or embedded_text
                    pages.append(f"[[PAGE:{index}]]\n{TextCleaner.clean_text(raw_text)}")
            temporary.write_text("\n\n".join(pages), encoding="utf-8")
            if temporary.stat().st_size == 0:
                raise TransformError("Extracted TXT is empty")
            temporary.replace(output_path)
            asset.local_txt_path = str(output_path)
            asset.status = PipelineAssetStatus.TEXT_READY.value
            run_asset.status = PipelineAssetStatus.TEXT_READY.value
            return output_path
        except Exception as error:
            temporary.unlink(missing_ok=True)
            asset.status = PipelineAssetStatus.FAILED.value
            asset.error_message = str(error)
            run_asset.status = PipelineAssetStatus.FAILED.value
            run_asset.detail = str(error)
            raise
