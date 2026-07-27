"""Manually create and enqueue one complete public-source pipeline batch."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.pipeline.downloader import sha256_file
from app.pipeline.models import PipelineAsset, PipelineAssetStatus, PipelineOrigin, PipelineRun, PipelineRunAsset, PipelineRunStatus, PipelineSource
from app.tasks.pipeline_tasks import discover_and_execute_public_pipeline_task


def register_manual_sources(db, run: PipelineRun, root: Path = Path("data/source")) -> int:
    registered = 0
    for source_type in ("jurisprudencia", "documentos"):
        source = db.query(PipelineSource).filter_by(source_type=source_type, source_subtype="default", connector_name="manual_upload").first()
        if not source:
            source = PipelineSource(source_type=source_type, source_subtype="default", connector_name="manual_upload")
            db.add(source)
            db.flush()
        for pdf in root.joinpath(source_type).rglob("*.pdf") if root.joinpath(source_type).exists() else ():
            digest = sha256_file(pdf)
            asset = db.query(PipelineAsset).filter_by(source_id=source.id, logical_identity=f"manual:{digest}").first()
            if not asset:
                asset = PipelineAsset(source_id=source.id, origin=PipelineOrigin.MANUAL.value, logical_identity=f"manual:{digest}", canonical_filename=pdf.name, downloaded_pdf_path=str(pdf), original_sha256=digest, status=PipelineAssetStatus.DOWNLOADED.value, metadata_json={"original_filename": pdf.name})
                db.add(asset)
                db.flush()
            if not db.query(PipelineRunAsset).filter_by(pipeline_run_id=run.id, asset_id=asset.id).first():
                db.add(PipelineRunAsset(pipeline_run_id=run.id, asset_id=asset.id, status=PipelineAssetStatus.DOWNLOADED.value))
                registered += 1
    db.commit()
    return registered


def main() -> int:
    db = SessionLocal()
    try:
        active = db.query(PipelineRun).filter(PipelineRun.status.in_(["pending", "running", "paused"])).first()
        if active:
            raise RuntimeError(f"An active pipeline already exists: {active.id}")
        run = PipelineRun(trigger="manual")
        db.add(run); db.commit(); db.refresh(run)
        manual_assets = register_manual_sources(db, run)
        task = discover_and_execute_public_pipeline_task.delay(str(run.id))
        print(f"RUN_ID={run.id}")
        print(f"TASK_ID={task.id}")
        print(f"MANUAL_ASSETS={manual_assets}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
