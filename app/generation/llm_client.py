"""Minimal OpenAI-compatible chat completion client used for answer generation.

Separate from `app.pipeline.registro_classifier.RegistroOficialClassifier`, which
is a JSON-mode classifier for a different pipeline stage. This client returns
free-form text and is meant for synthesizing a natural-language answer from a
set of already-retrieved, trusted context blocks (the RAG is the source of
truth for facts/citations; the LLM only phrases the final answer).
"""
import httpx

from app.core.config import settings


class LlmGenerationError(Exception):
    """Raised when the configured LLM provider fails to produce a completion."""


class LlmClient:
    def __init__(self, transport=None, enabled=None):
        self.transport = transport
        self._enabled_override = enabled

    @property
    def enabled(self) -> bool:
        if self._enabled_override is not None:
            return self._enabled_override
        return bool(settings.LLM_ANSWER_ENABLED and settings.LLM_ANSWER_API_KEY)

    def generate(self, system: str, prompt: str) -> str:
        if self.transport:
            return self.transport(system, prompt)

        provider = settings.LLM_ANSWER_PROVIDER
        if provider != "openai_compatible":
            raise LlmGenerationError(f"Unsupported LLM answer provider: {provider}")

        try:
            response = httpx.post(
                f"{settings.LLM_ANSWER_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_ANSWER_API_KEY}"},
                json={
                    "model": settings.LLM_ANSWER_MODEL,
                    "temperature": settings.LLM_ANSWER_TEMPERATURE,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=settings.LLM_ANSWER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError) as error:
            raise LlmGenerationError(str(error)) from error
