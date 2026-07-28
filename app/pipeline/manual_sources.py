"""Idempotent registration of locally supplied jurisprudence and documents."""
from pathlib import Path

from sqlalchemy.orm import Session

from app.pipeline.downloader import sha256_file
from app.pipeline.models import PipelineAsset, PipelineAssetStatus, PipelineOrigin, PipelineRun, PipelineRunAsset, PipelineSource


MANUAL_SOURCE_TYPES = ("jurisprudencia", "documentos")


def register_manual_sources(db: Session, run: PipelineRun, root: Path = Path("data/source")) -> int:
    """Attach local PDFs to a batch without renaming or re-uploading known content."""
    registered = 0
    for source_type in MANUAL_SOURCE_TYPES:
        source = db.query(PipelineSource).filter_by(
            source_type=source_type, source_subtype="default", connector_name="manual_upload",
        ).first()
        if not source:
            source = PipelineSource(source_type=source_type, source_subtype="default", connector_name="manual_upload")
            db.add(source)
            db.flush()

        directory = root / source_type
        for pdf in directory.rglob("*.pdf") if directory.exists() else ():
            digest = sha256_file(pdf)
            asset = db.query(PipelineAsset).filter_by(source_id=source.id, logical_identity=f"manual:{digest}").first()
            if not asset:
                asset = PipelineAsset(
                    source_id=source.id,
                    origin=PipelineOrigin.MANUAL.value,
                    logical_identity=f"manual:{digest}",
                    canonical_filename=pdf.name,
                    downloaded_pdf_path=str(pdf),
                    original_sha256=digest,
                    status=PipelineAssetStatus.DOWNLOADED.value,
                    metadata_json={"original_filename": pdf.name},
                )
                db.add(asset)
                db.flush()

            run_asset = db.query(PipelineRunAsset).filter_by(pipeline_run_id=run.id, asset_id=asset.id).first()
            if run_asset:
                continue

            # A repeated manual upload is discarded only after its TXT and R2
            # backup were both verified, keeping the VPS as the priority.
            txt_exists = bool(asset.local_txt_path and Path(asset.local_txt_path).is_file())
            if asset.r2_verified_at and txt_exists:
                pdf.unlink(missing_ok=True)
                db.add(PipelineRunAsset(
                    pipeline_run_id=run.id, asset_id=asset.id,
                    status=PipelineAssetStatus.SKIPPED.value,
                    detail="Known manual PDF already has verified R2 storage and TXT",
                ))
                continue

            asset.downloaded_pdf_path = str(pdf)
            asset.original_sha256 = digest
            asset.status = PipelineAssetStatus.DOWNLOADED.value
            db.add(PipelineRunAsset(
                pipeline_run_id=run.id, asset_id=asset.id, status=PipelineAssetStatus.DOWNLOADED.value,
            ))
            registered += 1

    db.commit()
    return registered
