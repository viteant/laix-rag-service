from sqlalchemy.orm import Session

from app.pipeline.connectors.base import DiscoveredAsset
from app.pipeline.models import PipelineAsset, PipelineAssetStatus, PipelineRun, PipelineRunAsset, PipelineSource


class DiscoveryService:
    """Persists discovery results without downloading a file or changing its content."""

    def __init__(self, db: Session):
        self.db = db

    def record(self, run: PipelineRun, source: PipelineSource, discovered: DiscoveredAsset) -> tuple[PipelineAsset, bool]:
        asset = self.db.query(PipelineAsset).filter_by(
            source_id=source.id,
            logical_identity=discovered.logical_identity,
        ).first()
        created = asset is None
        if created:
            asset = PipelineAsset(
                source_id=source.id,
                origin="download",
                logical_identity=discovered.logical_identity,
                canonical_filename=discovered.canonical_filename,
                source_url=discovered.source_url,
                metadata_json=discovered.metadata,
            )
            self.db.add(asset)
            self.db.flush()
        else:
            asset.source_url = discovered.source_url or asset.source_url
            asset.metadata_json = {**(asset.metadata_json or {}), **discovered.metadata}

        run_asset = self.db.query(PipelineRunAsset).filter_by(
            pipeline_run_id=run.id,
            asset_id=asset.id,
        ).first()
        if not run_asset:
            already_available = asset.status in {
                PipelineAssetStatus.VERIFIED.value,
                PipelineAssetStatus.TEXT_READY.value,
                PipelineAssetStatus.INGESTED.value,
                PipelineAssetStatus.CLEANED.value,
            }
            run_asset = PipelineRunAsset(
                pipeline_run_id=run.id,
                asset_id=asset.id,
                status=PipelineAssetStatus.DISCOVERED.value if created or not already_available else PipelineAssetStatus.SKIPPED.value,
                detail=None if created or not already_available else "Known asset already has verified storage or text",
            )
            self.db.add(run_asset)

        return asset, created
