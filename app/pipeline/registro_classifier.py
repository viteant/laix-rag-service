"""LLM-assisted, page-aware classification for Registro Oficial assets."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.pipeline.models import PipelineAssetStatus, PipelineRunAsset


LEGAL_CATEGORIES = frozenset({
    "CONSTITUCION", "LEY_ORGANICA", "LEY_ORDINARIA", "LEY_REFORMATORIA", "CODIGO",
    "DECRETO_EJECUTIVO", "REGLAMENTO", "ACUERDO_MINISTERIAL", "ACUERDO", "RESOLUCION",
    "ORDENANZA", "CIRCULAR", "INSTRUCTIVO", "NORMA_TECNICA", "TRATADO_INTERNACIONAL",
    "FE_DE_ERRATAS", "AVISO", "OTRO",
})
CATEGORY_ALIASES = {
    "INSTRUMENTO_INTERNACIONAL": "TRATADO_INTERNACIONAL",
    "TRATADO": "TRATADO_INTERNACIONAL",
    "FE_DE_ERRORES": "FE_DE_ERRATAS",
    "DECRETO": "DECRETO_EJECUTIVO",
}
INDEX_MARKERS = ("ÍNDICE", "INDICE", "SUMARIO", "CONTENIDO")


class ClassificationEntry(BaseModel):
    category: str
    title: str = Field(max_length=500)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @field_validator("category")
    @classmethod
    def category_is_allowed(cls, value: str) -> str:
        if value not in LEGAL_CATEGORIES:
            raise ValueError("Unsupported Registro Oficial category")
        return value

    @model_validator(mode="after")
    def page_range_is_valid(self):
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_end requires page_start")
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end cannot be before page_start")
        return self


class ClassificationResult(BaseModel):
    has_index: bool
    primary_category: str
    categories: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    entries: list[ClassificationEntry] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("primary_category")
    @classmethod
    def primary_category_is_allowed(cls, value: str) -> str:
        if value not in LEGAL_CATEGORIES:
            raise ValueError("Unsupported primary Registro Oficial category")
        return value

    @field_validator("categories")
    @classmethod
    def categories_are_unique_and_allowed(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(value not in LEGAL_CATEGORIES for value in values):
            raise ValueError("Categories must be unique allowed values")
        return values

    @model_validator(mode="after")
    def result_is_consistent(self):
        if self.primary_category not in self.categories:
            raise ValueError("primary_category must be included in categories")
        if not self.has_index and self.categories != ["OTRO"]:
            raise ValueError("Documents without an index must be classified as OTRO")
        return self


def pages_from_txt(content: str) -> list[tuple[int, str]]:
    parts = re.split(r"\[\[PAGE:(\d+)\]\]\s*", content)
    if len(parts) == 1:
        return [(1, content.strip())] if content.strip() else []
    return [(int(parts[index]), parts[index + 1].strip()) for index in range(1, len(parts) - 1, 2)]


def index_excerpt(content: str, max_pages: int, max_chars: int) -> tuple[str, list[int], bool]:
    selected = pages_from_txt(content)[:max_pages]
    excerpt = "\n\n".join(f"[[PAGE:{page}]]\n{text}" for page, text in selected)[:max_chars]
    has_index = any(marker in excerpt.upper() for marker in INDEX_MARKERS)
    return excerpt, [page for page, _ in selected], has_index


def categories_for_page_range(classification: dict[str, Any], page_start: int, page_end: int) -> list[str]:
    matches = {
        entry["category"]
        for entry in classification.get("entries", [])
        if entry.get("page_start") is not None
        and entry["page_start"] <= page_end
        and (entry.get("page_end") or entry["page_start"]) >= page_start
    }
    return sorted(matches) or list(classification.get("categories") or ["OTRO"])


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map unambiguous provider/model aliases to the product's closed taxonomy."""
    def normalized_category(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        key = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
        return CATEGORY_ALIASES.get(key, key)

    normalized = dict(payload)
    normalized["primary_category"] = normalized_category(normalized.get("primary_category"))
    normalized["categories"] = list(dict.fromkeys(
        normalized_category(category) for category in normalized.get("categories", [])
    ))
    evidence = normalized.get("evidence", [])
    if isinstance(evidence, str):
        normalized["evidence"] = [{"text": evidence[:500]}]
    elif evidence is None:
        normalized["evidence"] = []
    normalized_entries = []
    for entry in normalized.get("entries", []):
        entry = dict(entry)
        entry["category"] = normalized_category(entry.get("category"))
        normalized_entries.append(entry)
    normalized["entries"] = normalized_entries
    return normalized


class RegistroOficialClassifier:
    """Stores a safe fallback on LLM failure, so batch processing never stops."""

    def __init__(self, transport=None):
        self.transport = transport

    def _fallback(self, method: str, detail: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "classified", "method": method, "primary_category": "OTRO",
            "categories": ["OTRO"], "confidence": 1.0 if method == "rule_indice_mensual" else 0.0,
            "entries": [], "evidence": [], "prompt_version": settings.LLM_CLASSIFIER_PROMPT_VERSION,
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }
        if detail:
            result["error"] = detail[:500]
        return result

    @staticmethod
    def _prompt(excerpt: str, has_index: bool) -> str:
        catalog = ", ".join(sorted(LEGAL_CATEGORIES))
        return (
            "Clasifica exclusivamente el índice inicial de un Registro Oficial ecuatoriano. "
            f"Categorías permitidas: {catalog}. Devuelve JSON sin markdown con has_index, "
            "primary_category, categories, confidence, entries y evidence. entries debe contener "
            "category, title, page_start y page_end cuando el índice muestre páginas. Un ejemplar puede "
            "tener varias categorías. No inventes títulos, páginas ni categorías. Si no hay índice o no hay "
            "evidencia suficiente, responde has_index=false y categories=[\"OTRO\"]. "
            f"Detector local de índice: {has_index}.\n\n{excerpt}"
        )

    def _request(self, prompt: str) -> str:
        if self.transport:
            return self.transport(prompt)
        provider = settings.LLM_CLASSIFIER_PROVIDER
        timeout = settings.LLM_CLASSIFIER_TIMEOUT_SECONDS
        if provider in {"openai", "openai_compatible"}:
            response = httpx.post(
                f"{settings.LLM_CLASSIFIER_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_CLASSIFIER_API_KEY}"},
                json={"model": settings.LLM_CLASSIFIER_MODEL, "temperature": settings.LLM_CLASSIFIER_TEMPERATURE,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": "You return valid JSON only."}, {"role": "user", "content": prompt}]},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        if provider == "anthropic":
            response = httpx.post(
                f"{settings.LLM_CLASSIFIER_BASE_URL.rstrip('/')}/v1/messages",
                headers={"x-api-key": settings.LLM_CLASSIFIER_API_KEY, "anthropic-version": "2023-06-01"},
                json={"model": settings.LLM_CLASSIFIER_MODEL, "max_tokens": 1200,
                      "temperature": settings.LLM_CLASSIFIER_TEMPERATURE,
                      "messages": [{"role": "user", "content": prompt}]}, timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]
        if provider == "ollama":
            response = httpx.post(
                f"{settings.LLM_CLASSIFIER_BASE_URL.rstrip('/')}/api/chat",
                json={"model": settings.LLM_CLASSIFIER_MODEL, "stream": False, "format": "json",
                      "options": {"temperature": settings.LLM_CLASSIFIER_TEMPERATURE},
                      "messages": [{"role": "user", "content": prompt}]}, timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        raise ValueError(f"Unsupported LLM classifier provider: {provider}")

    def classify(self, run_asset: PipelineRunAsset) -> dict[str, Any]:
        asset = run_asset.asset
        source = asset.source
        if source.source_type != "registro_oficial":
            classification = {"status": "not_applicable", "method": "not_applicable", "categories": []}
        elif source.source_subtype == "indice_mensual":
            classification = self._fallback("rule_indice_mensual")
        elif not settings.LLM_CLASSIFIER_ENABLED:
            classification = self._fallback("disabled")
        else:
            try:
                if not asset.local_txt_path:
                    raise ValueError("TXT is required for classification")
                content = Path(asset.local_txt_path).read_text(encoding="utf-8")
                excerpt, input_pages, has_index = index_excerpt(content, settings.LLM_CLASSIFIER_MAX_INDEX_PAGES, settings.LLM_CLASSIFIER_MAX_INPUT_CHARS)
                raw = self._request(self._prompt(excerpt, has_index))
                parsed = ClassificationResult.model_validate(normalize_model_payload(json.loads(raw)))
                classification = {"status": "classified", "method": "llm", **parsed.model_dump(),
                                  "provider": settings.LLM_CLASSIFIER_PROVIDER, "model": settings.LLM_CLASSIFIER_MODEL,
                                  "prompt_version": settings.LLM_CLASSIFIER_PROMPT_VERSION, "input_pages": input_pages,
                                  "classified_at": datetime.now(timezone.utc).isoformat()}
            except Exception as error:
                classification = self._fallback("fallback", str(error))
        asset.metadata_json = {**(asset.metadata_json or {}), "classification": classification}
        asset.status = PipelineAssetStatus.CLASSIFIED.value
        run_asset.status = PipelineAssetStatus.CLASSIFIED.value
        return classification
