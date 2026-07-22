from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text


class FullTextSearch:
    def __init__(self, db: Session):
        self.db = db

    def search_text_chunks(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []

        clean_query = query.strip()

        # Dar un bono de relevancia de +2.0 cuando el texto o metadato coincide exactamente con el expediente o resolución
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
                (
                    ts_rank_cd(to_tsvector('spanish', c.content), websearch_to_tsquery('spanish', :query))
                    + CASE WHEN lc.case_number IS NOT NULL AND :clean_query ILIKE '%' || lc.case_number || '%' THEN 2.0 ELSE 0.0 END
                    + CASE WHEN lc.resolution_number IS NOT NULL AND :clean_query ILIKE '%' || lc.resolution_number || '%' THEN 2.0 ELSE 0.0 END
                ) AS rank_score
            FROM legal_chunks c
            JOIN legal_cases lc ON lc.id = c.legal_case_id
            JOIN source_documents sd ON sd.id = lc.source_document_id
            WHERE (
                to_tsvector('spanish', c.content) @@ websearch_to_tsquery('spanish', :query)
                OR c.content ILIKE :ilike_query
                OR lc.case_number ILIKE :ilike_query
                OR lc.resolution_number ILIKE :ilike_query
            )
        """

        params = {
            "query": clean_query,
            "clean_query": clean_query,
            "ilike_query": f"%{clean_query}%",
            "limit": limit
        }

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

        sql += " ORDER BY rank_score DESC LIMIT :limit;"

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
                "text_score": float(row["rank_score"] or 0.5),
                "content": row["content"],
                "metadata": row["chunk_metadata"] or {},
            })

        return results
