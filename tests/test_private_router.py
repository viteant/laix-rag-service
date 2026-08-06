from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.private_router import _validate_identifier, tag_documents_with_scope


class _FakeCase:
    def __init__(self, id, case_metadata=None):
        self.id = id
        self.case_metadata = case_metadata


class _FakeChunk:
    def __init__(self, legal_case_id, chunk_metadata=None):
        self.legal_case_id = legal_case_id
        self.chunk_metadata = chunk_metadata


class _FakeFilterResult:
    def __init__(self, items):
        self._items = items

    def filter_by(self, **_):
        return self

    def filter(self, *_):
        return self

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self, cases, chunks):
        self._cases = cases
        self._chunks = chunks
        self.committed = False

    def query(self, model):
        # LegalCase vs LegalChunk are distinguished by which fake list applies.
        if model.__name__ == "LegalCase":
            return _FakeFilterResult(self._cases)
        return _FakeFilterResult(self._chunks)

    def commit(self):
        self.committed = True


def test_validate_identifier_accepts_safe_values():
    _validate_identifier("tenant-1_ABC", "tenant_id")  # should not raise


def test_validate_identifier_rejects_unsafe_values():
    with pytest.raises(HTTPException) as exc_info:
        _validate_identifier("../etc/passwd", "tenant_id")

    assert exc_info.value.status_code == 422


def test_tag_documents_with_scope_stamps_cases_and_chunks_and_commits():
    case = _FakeCase(id="case-1", case_metadata={"existing": True})
    chunk = _FakeChunk(legal_case_id="case-1")
    session = _FakeSession(cases=[case], chunks=[chunk])

    tagged = tag_documents_with_scope(session, "doc-1", "tenant-a", "matter-1", r2_key="private/tenant-a/matter-1/x.pdf")

    assert tagged == 1
    assert case.case_metadata == {
        "existing": True,
        "tenant_id": "tenant-a",
        "matter_id": "matter-1",
        "r2_key": "private/tenant-a/matter-1/x.pdf",
    }
    assert chunk.chunk_metadata == {"tenant_id": "tenant-a", "matter_id": "matter-1"}
    assert session.committed is True


def test_tag_documents_with_scope_handles_a_document_with_no_cases():
    session = _FakeSession(cases=[], chunks=[])

    tagged = tag_documents_with_scope(session, "doc-empty", "tenant-a", "matter-1")

    assert tagged == 0
    assert session.committed is True
