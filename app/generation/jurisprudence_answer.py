from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.retrieval.hybrid_search import HybridSearch


class JurisprudenceAnswerGenerator:
    def __init__(self, db: Session):
        self.db = db
        self.searcher = HybridSearch(db)

    def generate_answer(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        # 1. Recuperación híbrida de los mejores fragmentos
        chunks = self.searcher.search(query=query, limit=top_k, filters=filters)

        if not chunks:
            return {
                "query": query,
                "answer": "No se encontraron precedentes ni sentencias aplicables a la consulta formulada.",
                "citations": [],
                "sources_used": []
            }

        # 2. Formatear fuentes y citas estructuradas
        citations = []
        context_blocks = []
        sources_used = []

        for idx, c in enumerate(chunks, 1):
            source_kind = "PRECEDENTE JURISPRUDENCIAL VINCULANTE" if c["source_type"] == "jurisprudence" else "FALLO / SENTENCIA PARTICULAR"
            case_num = c["case_number"] or "Sin Número"
            res_num = c["resolution_number"] or "Sin Res."
            court = c["court"] or "Corte Nacional de Justicia"
            pages = f"Págs. {c['page_start']}-{c['page_end']}"

            citation_text = f"[{source_kind}] Juicio No. {case_num} (Res. {res_num}), {court}, {pages}"
            citations.append({
                "source_index": idx,
                "citation_text": citation_text,
                "source_type": c["source_type"],
                "case_number": c["case_number"],
                "resolution_number": c["resolution_number"],
                "legal_area": c["legal_area"],
                "court": c["court"],
                "pages": pages,
                "chunk_id": c["chunk_id"]
            })

            sources_used.append({
                "filename": c["filename"],
                "source_type": c["source_type"],
                "legal_area": c["legal_area"],
                "match_type": c["match_type"],
                "score": c["score"]
            })

            block = (
                f"--- FUENTE #{idx} [{source_kind}] ---\n"
                f"Juicio / Recurso: {case_num} | Res: {res_num} | Materia: {c['legal_area']}\n"
                f"Ubicación: {pages} | Archivo: {c['filename']}\n"
                f"Texto: {c['content']}\n"
            )
            context_blocks.append(block)

        # 3. Ensamblar Respuesta RAG fundamentada
        # Construir síntesis juridica verificable
        top_chunk = chunks[0]
        top_kind = "Precedente Jurisprudencial Vinculante" if top_chunk["source_type"] == "jurisprudence" else "Fallo / Sentencia Particular"
        top_case = top_chunk["case_number"] or "S/N"

        synthesized_text = (
            f"Con base en la normativa y los criterios de la Corte Nacional de Justicia de Ecuador:\n\n"
            f"1. **Criterio Jurídico Aplicable**: De acuerdo con el {top_kind} en el **Juicio No. {top_case}** "
            f"(Materia: {top_chunk['legal_area']}), se establece que:\n"
            f"> \"{top_chunk['content'][:350].strip()}...\"\n\n"
            f"2. **Naturaleza de la Fuente**: Se fundamenta principalmente en un **{top_kind}** "
            f"obtenido de {top_chunk['filename']} (Páginas {top_chunk['page_start']}-{top_chunk['page_end']}).\n"
        )

        return {
            "query": query,
            "answer": synthesized_text,
            "citations": citations,
            "sources_used": sources_used,
            "retrieved_chunks_count": len(chunks)
        }
