import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
import enum

from app.core.database import Base


class SourceType(str, enum.Enum):
    DOCUMENT = "document"
    JURISPRUDENCE = "jurisprudence"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionMethod(str, enum.Enum):
    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(50), nullable=False, default=SourceType.DOCUMENT.value)
    filename = Column(String(255), nullable=False)
    original_path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    file_size = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False, default=0)
    has_embedded_text = Column(Boolean, nullable=False, default=True)
    requires_ocr = Column(Boolean, nullable=False, default=False)
    status = Column(String(50), nullable=False, default=DocumentStatus.PENDING.value, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    pages = relationship("DocumentPage", back_populates="source_document", cascade="all, delete-orphan")
    legal_cases = relationship("LegalCase", back_populates="source_document", cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=True)
    clean_text = Column(Text, nullable=True)
    extraction_method = Column(String(50), nullable=False, default=ExtractionMethod.EMBEDDED_TEXT.value)
    ocr_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    source_document = relationship("SourceDocument", back_populates="pages")

    __table_args__ = (
        Index("idx_doc_page_number", "source_document_id", "page_number", unique=True),
    )


class LegalCase(Base):
    __tablename__ = "legal_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    case_number = Column(String(100), nullable=True, index=True)
    resolution_number = Column(String(100), nullable=True, index=True)
    court = Column(String(255), nullable=True)
    chamber = Column(String(255), nullable=True)
    judge_rapporteur = Column(String(255), nullable=True)
    decision_date = Column(String(50), nullable=True)
    city = Column(String(100), nullable=True)
    legal_area = Column(String(100), nullable=True, index=True)
    action_type = Column(String(100), nullable=True)
    procedural_stage = Column(String(100), nullable=True)
    outcome = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    case_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    source_document = relationship("SourceDocument", back_populates="legal_cases")
    sections = relationship("LegalSection", back_populates="legal_case", cascade="all, delete-orphan")
    chunks = relationship("LegalChunk", back_populates="legal_case", cascade="all, delete-orphan")


class LegalSection(Base):
    __tablename__ = "legal_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_case_id = Column(UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    section_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)

    legal_case = relationship("LegalCase", back_populates="sections")
    chunks = relationship("LegalChunk", back_populates="legal_section", cascade="all, delete-orphan")


class LegalChunk(Base):
    __tablename__ = "legal_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_case_id = Column(UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_section_id = Column(UUID(as_uuid=True), ForeignKey("legal_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Vector(768), nullable=True)
    chunk_metadata = Column("metadata", JSONB, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_version = Column(String(50), nullable=True)
    embedded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    legal_case = relationship("LegalCase", back_populates="chunks")
    legal_section = relationship("LegalSection", back_populates="chunks")
