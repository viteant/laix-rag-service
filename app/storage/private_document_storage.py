"""Download/delete helper for privately-ingested case documents stored in R2.

Reuses the same R2 account/credentials as the public pipeline
(app.pipeline.r2_storage) but a distinct key prefix
(settings.R2_PRIVATE_PREFIX) so private client documents are namespaced
separately from the publicly-scraped jurisprudence corpus. Both live in the
same bucket today; moving private documents to a dedicated bucket later
(for stricter IAM-level isolation) only requires changing R2_BUCKET_NAME
here without touching callers.
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
        self.bucket = settings.R2_BUCKET_NAME
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION,
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
