"""Download/delete helper for privately-ingested case documents stored in R2.

Uses its own bucket/credentials (settings.R2_PRIVATE_*), separate from the
public pipeline's R2_* settings (app.pipeline.r2_storage) — the private R2
API token may be scoped to only this bucket, and even where it wouldn't be,
pointing both pipelines at the same bucket/credentials risks one
accidentally redirecting the other. Any R2_PRIVATE_* setting left unset
falls back to the matching public R2_* one, so a single-bucket setup with
only the public credentials configured keeps working unchanged.
"""
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class PrivateDocumentNotFoundError(Exception):
    pass


class PrivateDocumentStorage:
    def __init__(self, client=None):
        self.bucket = settings.R2_PRIVATE_BUCKET_NAME or settings.R2_BUCKET_NAME
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.R2_PRIVATE_ENDPOINT_URL or settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_PRIVATE_ACCESS_KEY_ID or settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_PRIVATE_SECRET_ACCESS_KEY or settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_PRIVATE_REGION or settings.R2_REGION,
        )

    def download_to_temp(self, r2_key: str) -> Path:
        suffix = Path(r2_key).suffix or ".pdf"
        destination = Path(tempfile.mkstemp(suffix=suffix)[1])
        try:
            self.client.download_file(self.bucket, r2_key, str(destination))
        except ClientError as error:
            destination.unlink(missing_ok=True)
            code = error.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise PrivateDocumentNotFoundError(f"R2 object not found: {r2_key}") from error
            raise
        return destination

    def delete(self, r2_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=r2_key)
