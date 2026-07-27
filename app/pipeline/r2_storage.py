from pathlib import Path
from datetime import datetime
import re

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.pipeline.models import PipelineAssetStatus, PipelineRunAsset


class R2VerificationError(RuntimeError):
    pass


def r2_key_for(run_asset: PipelineRunAsset, prefix: str) -> str:
    asset = run_asset.asset
    source = asset.source
    base = (prefix.strip("/"), source.source_type)
    if source.source_type in {"jurisprudencia", "documentos"}:
        return "/".join((*base, asset.canonical_filename))
    publication_date = (asset.metadata_json or {}).get("publication_date", "")
    year = publication_date[:4] if re.match(r"\d{4}-\d{2}-\d{2}", publication_date) else None
    if not year:
        match = re.match(r"\d{8}.*", asset.canonical_filename)
        year = asset.canonical_filename[4:8] if match else None
    if not year:
        match = re.match(r"(\d{4})", asset.canonical_filename)
        year = match.group(1) if match else None
    if not year:
        raise ValueError("Registro Oficial requires a publication year for its R2 key")
    return "/".join((*base, source.source_subtype, year, asset.canonical_filename))


class R2StorageService:
    """Stores only optimized PDFs and verifies remote metadata before cleanup is allowed."""

    def __init__(self, db: Session, client=None):
        self.db = db
        self.bucket = settings.R2_BUCKET_NAME
        self.prefix = settings.R2_PREFIX
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION,
        )

    def _head(self, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def upload_and_verify(self, run_asset: PipelineRunAsset) -> str:
        asset = run_asset.asset
        if not asset.optimized_pdf_path or not asset.optimized_sha256:
            raise R2VerificationError("Optimized PDF and SHA-256 are required before R2 upload")
        local_path = Path(asset.optimized_pdf_path)
        if not local_path.is_file():
            raise R2VerificationError(f"Optimized PDF is missing: {local_path}")

        key = r2_key_for(run_asset, self.prefix)
        expected_size = local_path.stat().st_size
        remote = self._head(key)
        remote_metadata = (remote or {}).get("Metadata", {})
        if not remote or remote.get("ContentLength") != expected_size or remote_metadata.get("sha256") != asset.optimized_sha256:
            self.client.upload_file(
                str(local_path),
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": "application/pdf",
                    "Metadata": {"sha256": asset.optimized_sha256},
                },
            )
            remote = self._head(key)

        if not remote or remote.get("ContentLength") != expected_size:
            raise R2VerificationError("R2 size verification failed")
        remote_metadata = remote.get("Metadata", {})
        if remote_metadata.get("sha256") != asset.optimized_sha256:
            raise R2VerificationError("R2 SHA-256 metadata verification failed")

        asset.r2_key = key
        asset.r2_etag = remote.get("ETag", "").strip('"') or None
        asset.r2_size_bytes = remote["ContentLength"]
        asset.r2_verified_at = datetime.utcnow()
        asset.status = PipelineAssetStatus.VERIFIED.value
        run_asset.status = PipelineAssetStatus.VERIFIED.value
        run_asset.detail = None
        return key
