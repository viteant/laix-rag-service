from app.generation.jurisprudence_answer import JurisprudenceAnswerGenerator


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


def test_answer_uses_top_jurisprudence_chunk_without_runtime_error():
    generator = JurisprudenceAnswerGenerator(db=None)
    generator.searcher.search = lambda **_: [_chunk()]

    response = generator.generate_answer("motivación de sentencias")

    assert response["retrieved_chunks_count"] == 1
    assert "Juicio No. 319-2011" in response["answer"]
    assert response["citations"][0]["chunk_id"] == "chunk-1"


def test_answer_uses_top_registro_oficial_chunk_without_runtime_error():
    generator = JurisprudenceAnswerGenerator(db=None)
    generator.searcher.search = lambda **_: [
        _chunk(
            source_type="registro_oficial",
            norm_type="LEY_ORGANICA",
            publication_date="2026-05-13",
            filename="13052026_registro_oficial_A02283.pdf",
        )
    ]

    response = generator.generate_answer("ley orgánica")

    assert "Registro Oficial del Ecuador" in response["answer"]
    assert "LEY_ORGANICA" in response["answer"]
