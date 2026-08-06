from app.generation.jurisprudence_answer import JurisprudenceAnswerGenerator
from app.generation.llm_client import LlmClient, LlmGenerationError


def _chunk(**overrides):
    chunk = {
        "source_type": "jurisprudence",
        "norm_type": None,
        "publication_date": None,
        "case_number": "319-2011",
        "resolution_number": "123-2011",
        "court": "Corte Nacional de Justicia",
        "page_start": 3,
        "page_end": 4,
        "legal_area": "Laboral y Social",
        "chunk_id": "chunk-1",
        "filename": "sentencia.pdf",
        "match_type": "hybrid",
        "score": 0.95,
        "content": "La sentencia debe expresar una motivación suficiente.",
    }
    chunk.update(overrides)
    return chunk


def _generator_with_llm_disabled(**overrides):
    generator = JurisprudenceAnswerGenerator(db=None, llm_client=LlmClient(enabled=False))
    generator.searcher.search = lambda **_: [_chunk(**overrides)]
    return generator


def test_template_fallback_uses_top_jurisprudence_chunk_when_llm_is_disabled():
    generator = _generator_with_llm_disabled()

    response = generator.generate_answer("motivación de sentencias")

    assert response["generated_by"] == "template_fallback"
    assert response["retrieved_chunks_count"] == 1
    assert "Juicio No. 319-2011" in response["answer"]
    assert response["citations"][0]["chunk_id"] == "chunk-1"


def test_template_fallback_uses_top_registro_oficial_chunk_when_llm_is_disabled():
    generator = _generator_with_llm_disabled(
        source_type="registro_oficial",
        norm_type="LEY_ORGANICA",
        publication_date="2026-05-13",
        filename="13052026_registro_oficial_A02283.pdf",
    )

    response = generator.generate_answer("ley orgánica")

    assert response["generated_by"] == "template_fallback"
    assert "Registro Oficial del Ecuador" in response["answer"]
    assert "LEY_ORGANICA" in response["answer"]


def test_answer_returns_no_results_message_without_calling_the_llm():
    calls = []
    llm_client = LlmClient(enabled=True, transport=lambda system, prompt: calls.append(1) or "no debería llamarse")
    generator = JurisprudenceAnswerGenerator(db=None, llm_client=llm_client)
    generator.searcher.search = lambda **_: []

    response = generator.generate_answer("consulta sin resultados")

    assert response["generated_by"] == "no_results"
    assert response["citations"] == []
    assert calls == []


def test_answer_uses_llm_generated_text_when_enabled():
    llm_client = LlmClient(
        enabled=True,
        transport=lambda system, prompt: "Respuesta redactada por el modelo con base en [1]."
    )
    generator = JurisprudenceAnswerGenerator(db=None, llm_client=llm_client)
    generator.searcher.search = lambda **_: [_chunk()]

    response = generator.generate_answer("motivación de sentencias")

    assert response["generated_by"] == "llm"
    assert response["answer"] == "Respuesta redactada por el modelo con base en [1]."
    # Las citas siguen viniendo del RAG, no del LLM.
    assert response["citations"][0]["chunk_id"] == "chunk-1"


def test_falls_back_to_template_when_llm_call_fails():
    def _failing_transport(system, prompt):
        raise LlmGenerationError("timeout")

    llm_client = LlmClient(enabled=True, transport=_failing_transport)
    generator = JurisprudenceAnswerGenerator(db=None, llm_client=llm_client)
    generator.searcher.search = lambda **_: [_chunk()]

    response = generator.generate_answer("motivación de sentencias")

    assert response["generated_by"] == "template_fallback"
    assert "Juicio No. 319-2011" in response["answer"]


def test_falls_back_to_template_when_llm_returns_empty_string():
    llm_client = LlmClient(enabled=True, transport=lambda system, prompt: "")
    generator = JurisprudenceAnswerGenerator(db=None, llm_client=llm_client)
    generator.searcher.search = lambda **_: [_chunk()]

    response = generator.generate_answer("motivación de sentencias")

    assert response["generated_by"] == "template_fallback"
