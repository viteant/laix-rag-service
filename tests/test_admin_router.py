"""Regression test for the SourceDocument(...) kwargs bug in admin_router.py:
the constructor previously passed filepath=/file_size_bytes=, which don't
exist as columns (the model defines original_path/file_size), so registering
a brand-new document via POST /v1/admin/documents raised a TypeError before
ever reaching the database.
"""
from app.database.models import SourceDocument


def test_source_document_accepts_the_columns_used_by_admin_router():
    document = SourceDocument(
        filename="demo.pdf",
        source_type="document",
        original_path="/tmp/demo.pdf",
        file_size=1024,
        sha256="a" * 64,
        page_count=3,
        status="queued",
    )

    assert document.original_path == "/tmp/demo.pdf"
    assert document.file_size == 1024


def test_source_document_rejects_the_old_incorrect_kwargs():
    try:
        SourceDocument(filepath="/tmp/demo.pdf", file_size_bytes=1024)
    except TypeError:
        pass
    else:
        raise AssertionError(
            "SourceDocument accepted filepath/file_size_bytes; if the model "
            "changed to support these, update admin_router.py accordingly."
        )
