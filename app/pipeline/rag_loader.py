import hashlib
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import DocumentPage, LegalChunk, SourceDocument
from app.pipeline.models import PipelineAssetStatus, PipelineRunAsset
from app.pipeline.registro_classifier import categories_for_page_range
from app.processing.case_detector import CaseDetector
from app.processing.chunker import TextChunker
from app.processing.document_builder import DocumentBuilder
from app.processing.metadata_extractor import MetadataExtractor
from app.processing.section_detector import SectionDetector
from app.retrieval.embedding_service import EmbeddingService


class RagLoadError(RuntimeError):
    pass


def _source_document_type(source_type: str) -> str:
    return {
        "jurisprudencia": "jurisprudence",
        "documentos": "document",
        "registro_oficial": "registro_oficial",
        "leyes": "laws",
    }[source_type]


class RagTxtLoader:
    """Loads a verified TXT into the existing case/chunk/vector RAG pipeline."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _apply_registro_classification(legal_case, asset) -> None:
        """Attach classification to the case before sections/chunks are created."""
        if asset.source.source_type != "registro_oficial":
            return
        classification = (asset.metadata_json or {}).get("classification")
        if not classification:
            return
        metadata = dict(legal_case.case_metadata or {})
        metadata["registro_oficial_classification"] = classification
        metadata["registro_oficial_subtype"] = asset.source.source_subtype
        metadata["registro_oficial_categories"] = categories_for_page_range(
            classification, legal_case.page_start, legal_case.page_end,
        )
        metadata["norm_type"] = classification.get("primary_category", "OTRO")
        legal_case.case_metadata = metadata

    def load(self, run_asset: PipelineRunAsset) -> SourceDocument:
        asset = run_asset.asset
        if not asset.local_txt_path:
            raise RagLoadError("A canonical TXT is required before RAG ingestion")
        txt_path = Path(asset.local_txt_path)
        if not txt_path.is_file():
            raise RagLoadError(f"TXT is missing: {txt_path}")

        content = txt_path.read_text(encoding="utf-8")
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self.db.query(SourceDocument).filter_by(sha256=sha256).first()
        if existing and existing.status == "completed":
            asset.status = PipelineAssetStatus.INGESTED.value
            run_asset.status = PipelineAssetStatus.INGESTED.value
            return existing

        source_type = _source_document_type(asset.source.source_type)
        source_doc = existing or SourceDocument(
            filename=txt_path.name,
            source_type=source_type,
            original_path=str(txt_path),
            sha256=sha256,
            file_size=txt_path.stat().st_size,
            page_count=0,
            status="processing",
        )
        if not existing:
            self.db.add(source_doc)
            self.db.flush()
        else:
            source_doc.status = "processing"
            source_doc.original_path = str(txt_path)
            source_doc.filename = txt_path.name
            source_doc.file_size = txt_path.stat().st_size
            self.db.query(DocumentPage).filter_by(source_document_id=source_doc.id).delete()
            self.db.commit()

        try:
            raw_pages = [segment for segment in content.split("[[PAGE:") if segment.strip()]
            for position, segment in enumerate(raw_pages, start=1):
                page_text = segment.split("]]\n", 1)[-1] if "]]\n" in segment else segment
                self.db.add(DocumentPage(
                    source_document_id=source_doc.id,
                    page_number=position,
                    raw_text=page_text,
                    clean_text=page_text,
                    extraction_method="embedded_text",
                    ocr_confidence=1.0,
                ))
            source_doc.page_count = len(raw_pages)
            self.db.commit()

            builder = DocumentBuilder()
            builder.build_full_document(self.db, str(source_doc.id))
            cases = CaseDetector().detect_cases_in_document(self.db, str(source_doc.id))
            metadata_extractor = MetadataExtractor()
            section_detector = SectionDetector()
            chunker = TextChunker()
            chunks = []
            for legal_case in cases:
                metadata_extractor.process_case_metadata(self.db, str(legal_case.id))
                self._apply_registro_classification(legal_case, asset)
                self.db.commit()
                section_detector.detect_sections(self.db, str(legal_case.id))
                chunks.extend(chunker.process_case_chunks(self.db, str(legal_case.id)))

            if chunks:
                vectors = EmbeddingService().embed_documents([chunk.content for chunk in chunks])
                for chunk, vector in zip(chunks, vectors):
                    chunk.embedding = vector
                    chunk.embedding_model = settings.EMBEDDING_MODEL
                    chunk.embedding_version = "1.0"
                    chunk.embedded_at = datetime.utcnow()

            source_doc.status = "completed"
            source_doc.processed_at = datetime.utcnow()
            asset.status = PipelineAssetStatus.INGESTED.value
            run_asset.status = PipelineAssetStatus.INGESTED.value
            self.db.commit()
            return source_doc
        except Exception:
            self.db.rollback()
            source_doc.status = "failed"
            asset.status = PipelineAssetStatus.FAILED.value
            run_asset.status = PipelineAssetStatus.FAILED.value
            self.db.commit()
            raise
