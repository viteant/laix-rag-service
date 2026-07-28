"""Idempotent registration of locally supplied jurisprudence and documents."""
from pathlib import Path

from sqlalchemy.orm import Session

from app.pipeline.downloader import sha256_file
from app.pipeline.models import PipelineAsset, PipelineAssetStatus, PipelineOrigin, PipelineRun, PipelineRunAsset, PipelineSource


MANUAL_SOURCE_TYPES = ("jurisprudencia", "documentos")


def _fingerprint(root: Path, pdf: Path) -> dict:
    stat = pdf.stat()
    return {"relative_path": str(pdf.relative_to(root)), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _fingerprint_key(fingerprint: dict) -> tuple:
    return fingerprint["relative_path"], fingerprint["size"], fingerprint["mtime_ns"]


def register_manual_sources(db: Session, run: PipelineRun, root: Path = Path("data/source")) -> int:
    """Attach local PDFs to a batch without renaming or re-uploading known content."""
    summary = dict(run.summary or {})
    if summary.get("manual_sources_registration_completed"):
        return 0

    files_by_type = {
        source_type: list((root / source_type).rglob("*.pdf")) if (root / source_type).exists() else []
        for source_type in MANUAL_SOURCE_TYPES
    }
    total = sum(len(files) for files in files_by_type.values())
    processed = 0
    registered = 0
    for source_type in MANUAL_SOURCE_TYPES:
        source = db.query(PipelineSource).filter_by(
            source_type=source_type, source_subtype="default", connector_name="manual_upload",
        ).first()
        if not source:
            source = PipelineSource(source_type=source_type, source_subtype="default", connector_name="manual_upload")
            db.add(source)
            db.flush()

        known_by_fingerprint = {}
        for known in db.query(PipelineAsset).filter_by(source_id=source.id).all():
            fingerprint = (known.metadata_json or {}).get("manual_file_fingerprint")
            if fingerprint:
                known_by_fingerprint[_fingerprint_key(fingerprint)] = known

        for pdf in files_by_type[source_type]:
            processed += 1
            if processed % 100 == 0:
                summary["manual_sources_registration"] = {"processed": processed, "total": total, "registered": registered}
                run.summary = summary
                db.commit()
                print(f"Registrando fuentes manuales: {processed} / {total} · nuevos en lote: {registered}")
            fingerprint = _fingerprint(root, pdf)
            asset = known_by_fingerprint.get(_fingerprint_key(fingerprint))
            digest = asset.original_sha256 if asset else sha256_file(pdf)
            asset = asset or db.query(PipelineAsset).filter_by(source_id=source.id, logical_identity=f"manual:{digest}").first()
            if not asset:
                asset = PipelineAsset(
                    source_id=source.id,
                    origin=PipelineOrigin.MANUAL.value,
                    logical_identity=f"manual:{digest}",
                    canonical_filename=pdf.name,
                    downloaded_pdf_path=str(pdf),
                    original_sha256=digest,
                    status=PipelineAssetStatus.DOWNLOADED.value,
                    metadata_json={"original_filename": pdf.name, "manual_file_fingerprint": fingerprint},
                )
                db.add(asset)
                db.flush()
            else:
                asset.metadata_json = {**(asset.metadata_json or {}), "original_filename": pdf.name, "manual_file_fingerprint": fingerprint}

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

    summary["manual_sources_registration"] = {"processed": processed, "total": total, "registered": registered}
    summary["manual_sources_registration_completed"] = True
    run.summary = summary
    db.commit()
    print(f"Registro manual completado: {processed} / {total} · nuevos en lote: {registered}")
    return registered
