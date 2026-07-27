import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class PipelineSourceType(str, enum.Enum):
    JURISPRUDENCIA = "jurisprudencia"
    DOCUMENTOS = "documentos"
    REGISTRO_OFICIAL = "registro_oficial"
    LEYES = "leyes"


class PipelineOrigin(str, enum.Enum):
    DOWNLOAD = "download"
    MANUAL = "manual"


class PipelineRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


class PipelinePhase(str, enum.Enum):
    DOWNLOAD = "download"
    OPTIMIZE = "optimize"
    UPLOAD = "upload"
    VERIFY_UPLOAD = "verify_upload"
    EXTRACT_TEXT = "extract_text"
    INGEST_RAG = "ingest_rag"
    CLEANUP = "cleanup"


class PipelineAssetStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    OPTIMIZED = "optimized"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    TEXT_READY = "text_ready"
    INGESTED = "ingested"
    CLEANED = "cleaned"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineSource(Base):
    __tablename__ = "pipeline_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(50), nullable=False, index=True)
    source_subtype = Column(String(80), nullable=False, default="default", index=True)
    connector_name = Column(String(100), nullable=False)
    base_url = Column(Text, nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = relationship("PipelineAsset", back_populates="source")

    __table_args__ = (
        UniqueConstraint("source_type", "source_subtype", "connector_name", name="uq_pipeline_source_connector"),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger = Column(String(30), nullable=False, default="manual")
    status = Column(String(30), nullable=False, default=PipelineRunStatus.PENDING.value, index=True)
    current_phase = Column(String(30), nullable=False, default=PipelinePhase.DOWNLOAD.value)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    cancellation_reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    summary = Column(JSONB, nullable=True)

    run_assets = relationship("PipelineRunAsset", back_populates="pipeline_run", cascade="all, delete-orphan")


class PipelineAsset(Base):
    __tablename__ = "pipeline_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_sources.id"), nullable=False, index=True)
    origin = Column(String(20), nullable=False)
    logical_identity = Column(String(512), nullable=False)
    canonical_filename = Column(String(512), nullable=False)
    source_url = Column(Text, nullable=True)
    local_pdf_path = Column(Text, nullable=True)
    local_txt_path = Column(Text, nullable=True)
    original_sha256 = Column(String(64), nullable=True, index=True)
    optimized_sha256 = Column(String(64), nullable=True, index=True)
    r2_key = Column(Text, nullable=True, unique=True)
    r2_etag = Column(String(255), nullable=True)
    r2_size_bytes = Column(Integer, nullable=True)
    r2_verified_at = Column(DateTime, nullable=True)
    status = Column(String(30), nullable=False, default=PipelineAssetStatus.DISCOVERED.value, index=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("PipelineSource", back_populates="assets")
    run_assets = relationship("PipelineRunAsset", back_populates="asset", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source_id", "logical_identity", name="uq_pipeline_asset_identity"),
    )


class PipelineRunAsset(Base):
    """Per-batch view of an asset; keeps retries and skipped files auditable."""

    __tablename__ = "pipeline_run_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(30), nullable=False, default=PipelineAssetStatus.DISCOVERED.value, index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    pipeline_run = relationship("PipelineRun", back_populates="run_assets")
    asset = relationship("PipelineAsset", back_populates="run_assets")

    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "asset_id", name="uq_pipeline_run_asset"),
    )
