from pathlib import Path
from types import SimpleNamespace

from app.pipeline.executor import PublicPipelineExecutor
from app.pipeline.models import PipelineAssetStatus


def test_cleanup_removes_only_known_pdfs_after_verified_backup_and_txt(tmp_path: Path):
    downloaded = tmp_path / "downloaded.pdf"
    optimized = tmp_path / "optimized.pdf"
    text = tmp_path / "document.txt"
    downloaded.write_bytes(b"%PDF")
    optimized.write_bytes(b"%PDF")
    text.write_text("text", encoding="utf-8")
    asset = SimpleNamespace(
        downloaded_pdf_path=str(downloaded),
        optimized_pdf_path=str(optimized),
        local_txt_path=str(text),
        r2_verified_at=object(),
        status=None,
    )
    run_asset = SimpleNamespace(asset=asset, status=None)

    executor = object.__new__(PublicPipelineExecutor)
    executor.cleanup_local_pdfs(run_asset)

    assert not downloaded.exists()
    assert not optimized.exists()
    assert text.exists()
    assert asset.status == PipelineAssetStatus.CLEANED.value


def test_partial_rag_with_no_verified_assets_keeps_pipeline_paused():
    class FakeSession:
        def refresh(self, _run):
            pass

        def commit(self):
            pass

    run = SimpleNamespace(status="paused", summary=None)
    executor = object.__new__(PublicPipelineExecutor)
    executor.db = FakeSession()
    executor._run_assets = lambda _run: []

    result = executor.ingest_verified_assets_while_paused(run)

    assert result["status"] == "completed"
    assert result["total"] == 0
    assert result["processed"] == 0
    assert run.status == "paused"
    assert run.summary["partial_rag"]["status"] == "completed"
