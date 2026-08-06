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

        params = {
            "query": clean_query,
            "clean_query": clean_query,
            "ilike_query": f"%{clean_query}%",
            "limit": limit
        }

        # Applied identically to both branches below (both alias
        # legal_chunks/legal_cases/source_documents as c/lc/sd).
        extra_filters_sql = ""

        if filters:
            if filters.get("legal_area"):
                extra_filters_sql += " AND LOWER(lc.legal_area) = LOWER(:legal_area)"
                params["legal_area"] = filters["legal_area"]
            if filters.get("case_number"):
                extra_filters_sql += " AND lc.case_number = :case_number"
                params["case_number"] = filters["case_number"]
            if filters.get("source_type"):
                extra_filters_sql += " AND sd.source_type = :source_type"
                params["source_type"] = filters["source_type"]
            if filters.get("registro_oficial_category"):
                extra_filters_sql += " AND COALESCE(c.metadata->'registro_oficial_categories', '[]'::jsonb) ? :registro_oficial_category"
                params["registro_oficial_category"] = filters["registro_oficial_category"]

        # See the matching guard in VectorSearch.search_similar_chunks: never
        # leak privately-ingested case documents into general search.
        if filters and filters.get("tenant_id"):
            extra_filters_sql += " AND c.metadata->>'tenant_id' = :tenant_id"
            params["tenant_id"] = filters["tenant_id"]
            if filters.get("matter_id"):
                extra_filters_sql += " AND c.metadata->>'matter_id' = :matter_id"
                params["matter_id"] = filters["matter_id"]
        else:
            extra_filters_sql += " AND c.metadata->>'tenant_id' IS NULL"

        # Two independently-optimizable branches, combined instead of a
        # single `WHERE tsvector_match OR content ILIKE ... OR number ILIKE
        # ...`. A mixed OR like that forces Postgres to abandon the GIN
        # index on to_tsvector('spanish', content) and fall back to a
        # sequential scan recomputing to_tsvector(content) for every one of
        # the ~1.5M rows in legal_chunks on every query — that's what made
        # /jurisprudence/answer hang for minutes/timeout in production.
        #
        #   1. text_matches: full-text match on content, backed by the GIN
        #      index (ix_legal_chunks_content_tsv).
        #   2. number_matches: exact case/resolution number match, resolved
        #      against the much smaller legal_cases table (~100k rows, with
        #      its own btree indexes) before ever touching legal_chunks.
        sql = f"""
            WITH text_matches AS (
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
                    ts_rank_cd(to_tsvector('spanish', c.content), websearch_to_tsquery('spanish', :query)) AS base_rank
                FROM legal_chunks c
                JOIN legal_cases lc ON lc.id = c.legal_case_id
                JOIN source_documents sd ON sd.id = lc.source_document_id
                WHERE to_tsvector('spanish', c.content) @@ websearch_to_tsquery('spanish', :query)
                {extra_filters_sql}
                ORDER BY base_rank DESC
                LIMIT :limit
            ),
            number_matches AS (
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
                    0::float AS base_rank
                FROM legal_cases lc
                JOIN legal_chunks c ON c.legal_case_id = lc.id
                JOIN source_documents sd ON sd.id = lc.source_document_id
                WHERE (
                    (lc.case_number IS NOT NULL AND lc.case_number ILIKE :ilike_query)
                    OR (lc.resolution_number IS NOT NULL AND lc.resolution_number ILIKE :ilike_query)
                )
                {extra_filters_sql}
                LIMIT :limit
            ),
            combined AS (
                SELECT DISTINCT ON (chunk_id) * FROM (
                    SELECT * FROM text_matches
                    UNION ALL
                    SELECT * FROM number_matches
                ) merged
                ORDER BY chunk_id, base_rank DESC
            )
            SELECT
                chunk_id,
                legal_case_id,
                content,
                page_start,
                page_end,
                chunk_metadata,
                case_number,
                resolution_number,
                legal_area,
                court,
                judge_rapporteur,
                source_type,
                filename,
                (
                    base_rank
                    + CASE WHEN case_number IS NOT NULL AND :clean_query ILIKE '%' || case_number || '%' THEN 2.0 ELSE 0.0 END
                    + CASE WHEN resolution_number IS NOT NULL AND :clean_query ILIKE '%' || resolution_number || '%' THEN 2.0 ELSE 0.0 END
                ) AS rank_score
            FROM combined
            ORDER BY rank_score DESC
            LIMIT :limit;
        """

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
