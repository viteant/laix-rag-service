import hashlib
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.pipeline.models import PipelineAssetStatus, PipelineRunAsset


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DownloadService:
    """Downloads a discovered PDF atomically, without advancing the batch phase."""

    def __init__(self, db: Session, work_root: Path = Path("data/work")):
        self.db = db
        self.work_root = work_root

    def destination_for(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        source = asset.source
        return (
            self.work_root
            / str(run_asset.pipeline_run_id)
            / source.source_type
            / source.source_subtype
            / "download"
            / asset.canonical_filename
        )

    def download(self, run_asset: PipelineRunAsset) -> Path:
        asset = run_asset.asset
        if not asset.source_url:
            raise DownloadError("A downloaded asset requires a source URL")

        destination = self.destination_for(run_asset)
        if destination.exists() and asset.original_sha256 == sha256_file(destination):
            run_asset.status = PipelineAssetStatus.DOWNLOADED.value
            asset.downloaded_pdf_path = str(destination)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        temporary.unlink(missing_ok=True)

        try:
            with httpx.stream("GET", asset.source_url, follow_redirects=True, timeout=120.0) as response:
                response.raise_for_status()
                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes():
                        file.write(chunk)

            if temporary.stat().st_size == 0:
                raise DownloadError("The downloaded file is empty")
            with temporary.open("rb") as file:
                if file.read(4) != b"%PDF":
                    raise DownloadError("The downloaded resource is not a PDF")

            temporary.replace(destination)
            asset.original_sha256 = sha256_file(destination)
            asset.downloaded_pdf_path = str(destination)
            asset.status = PipelineAssetStatus.DOWNLOADED.value
            run_asset.status = PipelineAssetStatus.DOWNLOADED.value
            run_asset.detail = None
            return destination
        except Exception as error:
            temporary.unlink(missing_ok=True)
            asset.status = PipelineAssetStatus.FAILED.value
            asset.error_message = str(error)
            run_asset.status = PipelineAssetStatus.FAILED.value
            run_asset.detail = str(error)
            raise
