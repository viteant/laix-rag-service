import hashlib
import tiktoken
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.database.models import LegalCase, LegalSection, LegalChunk


class TextChunker:
    def __init__(self, target_tokens: int = 700, max_tokens: int = 900, overlap_tokens: int = 100):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        # Estimación fallback si tiktoken no estuviera disponible: ~4 caracteres por token en español
        return len(text) // 4

    def chunk_section(self, db: Session, legal_case: LegalCase, section: LegalSection) -> List[LegalChunk]:
        content = section.content
        if not content or not content.strip():
            return []

        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        chunks_created = []

        current_paragraphs = []
        current_token_count = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            if current_token_count + para_tokens <= self.max_tokens:
                current_paragraphs.append(para)
                current_token_count += para_tokens
            else:
                # Si acumulamos suficiente contenido, crear chunk
                if current_paragraphs:
                    chunk_text = "\n\n".join(current_paragraphs)
                    chunk_obj = self._save_chunk(db, legal_case, section, chunk_text)
                    chunks_created.append(chunk_obj)

                # Manejar solapamiento / overlap
                current_paragraphs = [para]
                current_token_count = para_tokens

        # Guardar último remanente
        if current_paragraphs:
            chunk_text = "\n\n".join(current_paragraphs)
            chunk_obj = self._save_chunk(db, legal_case, section, chunk_text)
            chunks_created.append(chunk_obj)

        return chunks_created

    def _save_chunk(self, db: Session, legal_case: LegalCase, section: LegalSection, text: str) -> LegalChunk:
        # Extraer metadatos para inyección temporal
        case_meta = legal_case.case_metadata or {}
        pub_date = case_meta.get("publication_date")
        n_type = case_meta.get("norm_type")
        
        # Crear encabezado temporal si es Registro Oficial
        if pub_date or n_type:
            temporal_header = f"[Contexto Legal -> Publicado el: {pub_date or 'Desconocida'} | Tipo: {n_type or 'Norma'}]\n"
            text = temporal_header + text

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        token_count = self.count_tokens(text)

        metadata = {
            "case_number": legal_case.case_number,
            "resolution_number": legal_case.resolution_number,
            "legal_area": legal_case.legal_area,
            "court": legal_case.court,
            "decision_date": legal_case.decision_date,
            "section_type": section.section_type,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "publication_date": pub_date,
            "norm_type": n_type,
        }

        chunk = LegalChunk(
            legal_case_id=legal_case.id,
            legal_section_id=section.id,
            content=text,
            content_hash=content_hash,
            page_start=section.page_start,
            page_end=section.page_end,
            token_count=token_count,
            chunk_metadata=metadata,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def process_case_chunks(self, db: Session, case_id: str) -> List[LegalChunk]:
        legal_case = db.query(LegalCase).filter_by(id=case_id).first()
        if not legal_case:
            raise ValueError(f"LegalCase with ID {case_id} not found")

        sections = db.query(LegalSection).filter_by(legal_case_id=legal_case.id).order_by(LegalSection.position).all()
        if not sections:
            return []

        # Eliminar chunks previos
        db.query(LegalChunk).filter_by(legal_case_id=legal_case.id).delete()

        all_chunks = []
        for sec in sections:
            created = self.chunk_section(db, legal_case, sec)
            all_chunks.extend(created)

        return all_chunks
