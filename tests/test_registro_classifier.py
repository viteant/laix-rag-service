from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline.models import PipelineAssetStatus
from app.pipeline.registro_classifier import (
    ClassificationResult,
    RegistroOficialClassifier,
    categories_for_page_range,
    index_excerpt,
    normalize_model_payload,
)


def test_index_excerpt_keeps_initial_pages_and_detects_index():
    excerpt, pages, has_index = index_excerpt(
        "[[PAGE:1]]\nÍNDICE\nLey Orgánica ..... 3\n[[PAGE:2]]\nResolución ..... 8\n[[PAGE:3]]\nTexto",
        max_pages=2,
        max_chars=1000,
    )

    assert pages == [1, 2]
    assert has_index is True
    assert "[[PAGE:3]]" not in excerpt


def test_classification_result_rejects_non_catalog_categories():
    with pytest.raises(ValueError, match="Unsupported"):
        ClassificationResult.model_validate({
            "has_index": True, "primary_category": "LEY", "categories": ["LEY"], "confidence": 0.9,
        })


def test_page_ranges_select_only_the_category_that_applies_to_chunk():
    classification = {
        "categories": ["LEY_ORGANICA", "RESOLUCION"],
        "entries": [
            {"category": "LEY_ORGANICA", "page_start": 3, "page_end": 7},
            {"category": "RESOLUCION", "page_start": 8, "page_end": 10},
        ],
    }

    assert categories_for_page_range(classification, 4, 4) == ["LEY_ORGANICA"]
    assert categories_for_page_range(classification, 8, 9) == ["RESOLUCION"]
    assert categories_for_page_range(classification, 20, 20) == ["LEY_ORGANICA", "RESOLUCION"]


def test_model_aliases_are_normalized_before_closed_taxonomy_validation():
    normalized = normalize_model_payload({
        "primary_category": "instrumento internacional",
        "categories": ["INSTRUMENTO_INTERNACIONAL", "RESOLUCION", "RESOLUCION"],
        "entries": [{"category": "Tratado", "title": "Convenio", "page_start": 3}],
    })

    assert normalized["primary_category"] == "TRATADO_INTERNACIONAL"
    assert normalized["categories"] == ["TRATADO_INTERNACIONAL", "RESOLUCION"]
    assert normalized["entries"][0]["category"] == "TRATADO_INTERNACIONAL"


def test_string_evidence_is_preserved_as_a_single_evidence_item():
    normalized = normalize_model_payload({"categories": ["OTRO"], "evidence": "No hay índice."})

    assert normalized["evidence"] == [{"text": "No hay índice."}]


def test_indice_mensual_is_classified_as_other_without_llm_call():
    asset = SimpleNamespace(
        source=SimpleNamespace(source_type="registro_oficial", source_subtype="indice_mensual"),
        metadata_json={}, local_txt_path=None, status=None,
    )
    run_asset = SimpleNamespace(asset=asset, status=None)

    result = RegistroOficialClassifier(transport=lambda _: (_ for _ in ()).throw(AssertionError("must not call LLM"))).classify(run_asset)

    assert result["categories"] == ["OTRO"]
    assert result["method"] == "rule_indice_mensual"
    assert asset.status == PipelineAssetStatus.CLASSIFIED.value
