from pathlib import Path
import shutil
from types import SimpleNamespace
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


def test_optimize_uses_ghostscript_profile_when_available(tmp_path: Path, monkeypatch):
    downloaded = tmp_path / "entrada.pdf"
    _pdf_with_embedded_text(downloaded)
    source = SimpleNamespace(source_type="documentos", source_subtype="default")
    asset = SimpleNamespace(
        downloaded_pdf_path=str(downloaded), optimized_pdf_path=None, optimized_sha256=None,
        local_txt_path=None, status=None, error_message=None, canonical_filename="documento.pdf", source=source,
    )
    run_asset = SimpleNamespace(asset=asset, pipeline_run_id="smoke-run", status=None, detail=None)
    service = TransformService(None, work_root=tmp_path / "work", text_root=tmp_path / "text")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output = next(part.removeprefix("-sOutputFile=") for part in command if part.startswith("-sOutputFile="))
        shutil.copyfile(downloaded, output)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.pipeline.transform.subprocess.run", fake_run)
    optimized = service.optimize(run_asset)

    assert optimized.is_file()
    assert calls and calls[0][0] == "gs"
    assert any(part == "-dPDFSETTINGS=/ebook" for part in calls[0])


def test_text_extraction_prefers_original_pdf_over_compressed_copy(tmp_path: Path):
    original = tmp_path / "original.pdf"
    compressed = tmp_path / "compressed.pdf"
    _pdf_with_embedded_text(original)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "SOLO COPIA COMPRIMIDA", fontsize=12)
    document.save(compressed)
    document.close()
    source = SimpleNamespace(source_type="jurisprudencia", source_subtype="default")
    asset = SimpleNamespace(
        downloaded_pdf_path=str(original), optimized_pdf_path=str(compressed), optimized_sha256="sha",
        local_txt_path=None, status=None, error_message=None, canonical_filename="10866.pdf", source=source,
    )
    run_asset = SimpleNamespace(asset=asset, pipeline_run_id="smoke-run", status=None, detail=None)

    extracted = TransformService(None, work_root=tmp_path / "work", text_root=tmp_path / "text").extract_text(run_asset)

    content = extracted.read_text(encoding="utf-8")
    assert "Contenido jurídico verificable." in content
    assert "SOLO COPIA COMPRIMIDA" not in content
