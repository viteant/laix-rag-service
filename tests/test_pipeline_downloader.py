from pathlib import Path

from app.pipeline.downloader import sha256_file


def test_sha256_file_is_stable_for_download_deduplication(tmp_path: Path):
    document = tmp_path / "document.pdf"
    document.write_bytes(b"%PDF-1.7\nexample")

    assert sha256_file(document) == "4c05a9d358d6ae170333b35b69ddf857bde90fe521d98136c23d8cda233fcedd"
