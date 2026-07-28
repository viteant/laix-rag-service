from pathlib import Path
from uuid import uuid4

import fitz

from app.pipeline.manual_sources import register_manual_sources
from app.pipeline.models import PipelineAsset, PipelineRun, PipelineRunAsset, PipelineSource


class _Query:
    def __init__(self, items):
        self.items = items
        self.filters = {}

    def filter_by(self, **filters):
        self.filters.update(filters)
        return self

    def first(self):
        return next((item for item in self.items if all(getattr(item, key) == value for key, value in self.filters.items())), None)


class _Db:
    def __init__(self):
        self.items = {PipelineSource: [], PipelineAsset: [], PipelineRunAsset: []}

    def query(self, model):
        return _Query(self.items[model])

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.items[type(item)].append(item)

    def flush(self):
        pass

    def commit(self):
        pass


def _pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Documento judicial")
    document.save(path)
    document.close()


def test_manual_sources_keep_original_filename_and_are_idempotent(tmp_path: Path):
    source_root = tmp_path / "source"
    pdf = source_root / "jurisprudencia" / "10866.pdf"
    pdf.parent.mkdir(parents=True)
    _pdf(pdf)
    db = _Db()
    run = PipelineRun(id=uuid4())

    assert register_manual_sources(db, run, source_root) == 1
    assert register_manual_sources(db, run, source_root) == 0

    asset = db.items[PipelineAsset][0]
    assert asset.canonical_filename == "10866.pdf"
    assert Path(asset.downloaded_pdf_path) == pdf
    assert len(db.items[PipelineRunAsset]) == 1
