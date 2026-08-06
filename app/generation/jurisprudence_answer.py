from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.generation.llm_client import LlmClient, LlmGenerationError
from app.retrieval.hybrid_search import HybridSearch

MAX_CONTEXT_CHUNK_CHARS = 1500

SYSTEM_PROMPT = (
    "Eres un asistente jurídico para abogados ecuatorianos. Respondes ÚNICAMENTE "
    "con base en las fuentes provistas a continuación (jurisprudencia, normativa o "
    "Registro Oficial ya recuperados). No inventes citas, números de juicio, fechas "
    "ni artículos que no aparezcan en las fuentes. Si las fuentes no bastan para "
    "responder con certeza, dilo explícitamente. Responde en español, de forma "
    "clara y concisa, y cuando cites una fuente usa su número de referencia entre "
    "corchetes, por ejemplo [1]."
)


class JurisprudenceAnswerGenerator:
    def __init__(self, db: Session, llm_client: Optional[LlmClient] = None):
        self.db = db
        self.searcher = HybridSearch(db)
        self.llm_client = llm_client or LlmClient()

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
                "sources_used": [],
                "generated_by": "no_results"
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
                f"Texto: {c['content'][:MAX_CONTEXT_CHUNK_CHARS]}\n"
            )
            context_blocks.append(block)

        answer_text, generated_by = self._synthesize(query, chunks, context_blocks)

        return {
            "query": query,
            "answer": answer_text,
            "citations": citations,
            "sources_used": sources_used,
            "retrieved_chunks_count": len(chunks),
            "generated_by": generated_by
        }

    def _synthesize(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        context_blocks: List[str]
    ) -> Tuple[str, str]:
        if self.llm_client.enabled:
            try:
                prompt = (
                    f"Pregunta del abogado: {query}\n\n"
                    f"Fuentes recuperadas:\n\n" + "\n".join(context_blocks)
                )
                answer = self.llm_client.generate(SYSTEM_PROMPT, prompt)
                if answer:
                    return answer, "llm"
            except LlmGenerationError:
                pass  # cae al respaldo por plantilla

        return self._template_synthesis(chunks[0], chunks), "template_fallback"

    @staticmethod
    def _template_synthesis(top_chunk: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
        if top_chunk.get("source_type") == "registro_oficial" or top_chunk.get("norm_type"):
            norm_type = top_chunk.get("norm_type") or "Normativa"
            pub_date = top_chunk.get("publication_date") or "Fecha Desconocida"

            evolucion = ""
            if len(chunks) > 1:
                fechas = [c.get("publication_date") for c in chunks if c.get("publication_date")]
                if len(set(fechas)) > 1:
                    evolucion = "\n\n**Evolución Cronológica Detectada**: Se han encontrado referencias a esta normativa en distintas fechas. " \
                                "La respuesta prioriza la norma más reciente para asegurar la vigencia, pero debes corroborar derogatorias."

            return (
                f"Con base en el Registro Oficial del Ecuador:\n\n"
                f"1. **Disposición Legal Vigente**: De acuerdo con el/la **{norm_type}** "
                f"publicado el **{pub_date}**:\n"
                f"> \"{top_chunk['content'][:400].strip()}...\"\n{evolucion}\n"
                f"2. **Fuente**: Extraído de {top_chunk['filename']} (Páginas {top_chunk['page_start']}-{top_chunk['page_end']}).\n"
            )

        top_kind = "Precedente Jurisprudencial Vinculante" if top_chunk.get("source_type") == "jurisprudence" else "Fallo / Sentencia Particular"
        top_case = top_chunk.get("case_number") or "S/N"

        return (
            f"Con base en la normativa y los criterios de la Corte Nacional de Justicia de Ecuador:\n\n"
            f"1. **Criterio Jurídico Aplicable**: De acuerdo con el {top_kind} en el **Juicio No. {top_case}** "
            f"(Materia: {top_chunk.get('legal_area', 'Otros')}), se establece que:\n"
            f"> \"{top_chunk['content'][:350].strip()}...\"\n\n"
            f"2. **Naturaleza de la Fuente**: Se fundamenta principalmente en un **{top_kind}** "
            f"obtenido de {top_chunk['filename']} (Páginas {top_chunk['page_start']}-{top_chunk['page_end']}).\n"
        )
