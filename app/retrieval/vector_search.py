from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.models import LegalChunk, LegalCase, SourceDocument
from app.retrieval.embedding_service import EmbeddingService


class VectorSearch:
    def __init__(self, db: Session):
        self.db = db
        self.embedder = EmbeddingService()

    def search_similar_chunks(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query_vector = self.embedder.embed_query(query)
        if not query_vector:
            return []

        vec_str = "[" + ",".join(map(str, query_vector)) + "]"

        sql = """
            SELECT 
                c.id AS chunk_id,
                c.legal_case_id,
                c.content,
                c.page_start,
                c.page_end,
                c.metadata AS chunk_metadata,
                lc.case_number,
                lc.resolution_number,
                lc.legal_area,
                lc.court,
                lc.judge_rapporteur,
                sd.source_type,
                sd.filename,
                1 - (c.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM legal_chunks c
            JOIN legal_cases lc ON lc.id = c.legal_case_id
            JOIN source_documents sd ON sd.id = lc.source_document_id
            WHERE c.embedding IS NOT NULL
        """

        params = {"query_vector": vec_str, "limit": limit}

        if filters:
            if filters.get("legal_area"):
                sql += " AND LOWER(lc.legal_area) = LOWER(:legal_area)"
                params["legal_area"] = filters["legal_area"]
            if filters.get("case_number"):
                sql += " AND lc.case_number = :case_number"
                params["case_number"] = filters["case_number"]
            if filters.get("source_type"):
                sql += " AND sd.source_type = :source_type"
                params["source_type"] = filters["source_type"]

        sql += " ORDER BY c.embedding <=> CAST(:query_vector AS vector) ASC LIMIT :limit;"

        result = self.db.execute(text(sql), params)
        rows = result.mappings().all()

        results = []
        for row in rows:
            results.append({
                "chunk_id": str(row["chunk_id"]),
                "case_id": str(row["legal_case_id"]),
                "case_number": row["case_number"],
                "resolution_number": row["resolution_number"],
                "legal_area": row["legal_area"],
                "court": row["court"],
                "judge_rapporteur": row["judge_rapporteur"],
                "source_type": row["source_type"],
                "filename": row["filename"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "similarity_score": float(row["similarity"]),
                "content": row["content"],
                "metadata": row["chunk_metadata"] or {},
            })

        return results
