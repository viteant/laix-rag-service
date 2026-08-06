"""Regression test for the SourceDocument.filepath attribute bug in
ingest_tasks.py: the Celery task read doc.filepath (not a real column) and
would raise AttributeError on every real ingestion job, and it also
discarded process_single_pdf's actual "success"/"skipped"/"failed" result by
coercing it into a boolean that was always truthy.
"""
import pathlib
from types import SimpleNamespace
from unittest.mock import patch

from app.tasks import ingest_tasks


class _FakeQuery:
    def __init__(self, doc):
        self._doc = doc

    def filter_by(self, **_):
        return self

    def first(self):
        return self._doc


class _FakeSession:
    def __init__(self, doc):
        self._doc = doc
        self.committed = False

    def query(self, *_):
        return _FakeQuery(self._doc)

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_task_reads_original_path_and_forwards_the_real_result(tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    doc = SimpleNamespace(original_path=str(pdf_path), status="queued", error_message=None)
    session = _FakeSession(doc)

    with patch.object(ingest_tasks, "SessionLocal", return_value=session), \
         patch.object(ingest_tasks, "process_single_pdf", return_value="success") as mocked:
        result = ingest_tasks.ingest_source_document_task.run("doc-1")

    mocked.assert_called_once()
    called_path = mocked.call_args[0][1]
    assert called_path == pathlib.Path(str(pdf_path))
    assert result == {"status": "success", "document_id": "doc-1"}


def test_task_marks_the_document_failed_when_the_file_is_missing(tmp_path):
    missing_path = tmp_path / "missing.pdf"
    doc = SimpleNamespace(original_path=str(missing_path), status="queued", error_message=None)
    session = _FakeSession(doc)

    with patch.object(ingest_tasks, "SessionLocal", return_value=session):
        result = ingest_tasks.ingest_source_document_task.run("doc-2")

    assert result == {"status": "error", "message": "File not found"}
    assert doc.status == "failed"
    assert session.committed is True
