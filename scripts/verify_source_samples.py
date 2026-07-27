"""Smoke-test source PDFs without renaming or modifying their original files."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz

from app.pipeline.transform import TransformService


def samples(root: Path):
    for source_type in ("jurisprudencia", "documentos"):
        files = sorted((root / source_type).glob("*.pdf"))
        if files:
            yield source_type, "default", files[0]
    registro_root = root / "registro_oficial"
    for subtype_dir in sorted(path for path in registro_root.iterdir() if path.is_dir()):
        files = sorted(subtype_dir.glob("*.pdf"))
        if files:
            yield "registro_oficial", subtype_dir.name, files[0]


def verify(root: Path = Path("data/source")) -> int:
    checked = 0
    with TemporaryDirectory(prefix="laix-source-smoke-") as temporary:
        temporary_root = Path(temporary)
        for source_type, subtype, pdf_path in samples(root):
            # Manual/source-provided files retain their exact original name.
            original_filename = pdf_path.name
            source = SimpleNamespace(source_type=source_type, source_subtype=subtype)
            asset = SimpleNamespace(
                downloaded_pdf_path=str(pdf_path), optimized_pdf_path=None, optimized_sha256=None,
                local_txt_path=None, status=None, error_message=None,
                canonical_filename=original_filename, source=source,
            )
            run_asset = SimpleNamespace(
                asset=asset, pipeline_run_id="source-smoke", status=None, detail=None,
            )
            service = TransformService(None, temporary_root / "work", temporary_root / "text")
            optimized = service.optimize(run_asset)
            extracted = service.extract_text(run_asset)
            with fitz.open(optimized) as document:
                pages = len(document)
            text = extracted.read_text(encoding="utf-8")
            if pages < 1 or "[[PAGE:1]]" not in text:
                raise RuntimeError(f"Invalid conversion for {pdf_path}")
            checked += 1
            print(f"OK {source_type}/{subtype}: {pdf_path.name} ({pages} pages, {len(text)} chars)")
    print(f"Verified {checked} real local PDFs")
    return checked


if __name__ == "__main__":
    raise SystemExit(0 if verify() else 1)
