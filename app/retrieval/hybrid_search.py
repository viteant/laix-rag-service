from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.retrieval.vector_search import VectorSearch
from app.retrieval.full_text_search import FullTextSearch


class HybridSearch:
    def __init__(self, db: Session, alpha: float = 0.7):
        self.db = db
        self.vector_search = VectorSearch(db)
        self.text_search = FullTextSearch(db)
        self.alpha = alpha

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        vec_results = self.vector_search.search_similar_chunks(query, limit=limit * 2, filters=filters)
        txt_results = self.text_search.search_text_chunks(query, limit=limit * 2, filters=filters)

        chunks_map: Dict[str, Dict[str, Any]] = {}

        for rank, res in enumerate(vec_results, 1):
            cid = res["chunk_id"]
            rrf_score = 1.0 / (60 + rank)
            vec_score = res.get("similarity_score", 0.0)

            res["hybrid_score"] = self.alpha * vec_score + (1 - self.alpha) * rrf_score
            res["match_type"] = "vector"
            chunks_map[cid] = res

        for rank, res in enumerate(txt_results, 1):
            cid = res["chunk_id"]
            rrf_score = 1.0 / (60 + rank)
            text_score = min(1.0, res.get("text_score", 0.5))

            if cid in chunks_map:
                existing = chunks_map[cid]
                existing["hybrid_score"] += (1 - self.alpha) * text_score + rrf_score
                existing["match_type"] = "hybrid"
            else:
                res["hybrid_score"] = (1 - self.alpha) * text_score + rrf_score
                res["match_type"] = "text"
                chunks_map[cid] = res

        sorted_results = sorted(chunks_map.values(), key=lambda x: x["hybrid_score"], reverse=True)

        final_results = []
        for item in sorted_results[:limit]:
            final_results.append({
                "chunk_id": item["chunk_id"],
                "case_id": item["case_id"],
                "case_number": item["case_number"],
                "resolution_number": item["resolution_number"],
                "legal_area": item["legal_area"],
                "court": item["court"],
                "judge_rapporteur": item["judge_rapporteur"],
                "source_type": item["source_type"],
                "filename": item["filename"],
                "page_start": item["page_start"],
                "page_end": item["page_end"],
                "section_type": item.get("metadata", {}).get("section_type", "general"),
                "score": round(float(item["hybrid_score"]), 4),
                "match_type": item["match_type"],
                "content": item["content"],
            })

        return final_results
