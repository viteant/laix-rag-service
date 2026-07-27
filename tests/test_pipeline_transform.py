from pathlib import Path
from types import SimpleNamespace

import fitz

from app.pipeline.models import PipelineAssetStatus
from app.pipeline.transform import TransformService


def _pdf_with_embedded_text(path: Path) -> None:
    document = fitz.open()
    for page_number in range(1, 3):
        page = document.new_page()
        page.insert_textbox(
            fitz.Rect(72, 72, 520, 300),
            f"Página {page_number}. " + "Contenido jurídico verificable. " * 4,
            fontsize=10,
        )
    document.save(path)
    document.close()


def test_optimize_and_extract_text_preserves_pages_and_canonical_content(tmp_path: Path):
    downloaded = tmp_path / "entrada.pdf"
    _pdf_with_embedded_text(downloaded)
    source = SimpleNamespace(source_type="registro_oficial", source_subtype="registro_oficial")
    asset = SimpleNamespace(
        downloaded_pdf_path=str(downloaded),
        optimized_pdf_path=None,
        optimized_sha256=None,
        local_txt_path=None,
        status=None,
        error_message=None,
        canonical_filename="30012026_registro_oficial_A01203.pdf",
        source=source,
    )
    run_asset = SimpleNamespace(
        asset=asset,
        pipeline_run_id="smoke-run",
        status=None,
        detail=None,
    )
    service = TransformService(None, work_root=tmp_path / "work", text_root=tmp_path / "text")

    optimized = service.optimize(run_asset)
    extracted = service.extract_text(run_asset)

    assert optimized.is_file()
    assert asset.optimized_sha256
    with fitz.open(optimized) as document:
        assert len(document) == 2
    text = extracted.read_text(encoding="utf-8")
    assert text.count("Contenido jurídico verificable.") == 8
    assert "[[PAGE:1]]" in text
    assert "[[PAGE:2]]" in text
    assert asset.status == PipelineAssetStatus.TEXT_READY.value
    assert run_asset.status == PipelineAssetStatus.TEXT_READY.value
