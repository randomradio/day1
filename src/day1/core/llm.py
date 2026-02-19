"""LLM client for OpenAI-compatible APIs.

Supports OpenAI, Doubao, and any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from day1.config import settings


class DoubaoClient:
    """Doubao (Volces/ByteDance) LLM client with file upload support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize Doubao client.

        Args:
            api_key: API key (defaults to BM_DOUBAO_API_KEY)
            base_url: Base URL (defaults to BM_DOUBAO_BASE_URL)
            model: Model name (defaults to BM_DOUBAO_LLM_MODEL)
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("openai package not installed") from e

        self._api_key = api_key or settings.doubao_api_key
        self._base_url = base_url or settings.doubao_base_url
        self._model = model or getattr(
            settings,
            "doubao_llm_model",
            "doubao-seed-1-6-251015",
        )

        if not self._api_key:
            raise ValueError("Doubao API key not configured (BM_DOUBAO_API_KEY)")

        self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)

    @property
    def model(self) -> str:
        """Return the model name."""
        return self._model

    def upload_file(self, file_path: str | Path, purpose: str = "user_data") -> Any:
        """Upload a file to Doubao for processing.

        Args:
            file_path: Path to the file
            purpose: File purpose (default: "user_data")

        Returns:
            File object with id and status
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            file = self._client.files.create(file=f, purpose=purpose)

        # Wait for processing to complete
        while file.status == "processing":
            time.sleep(2)
            file = self._client.files.retrieve(file.id)

        if file.status == "error":
            raise RuntimeError(f"File processing failed: {file}")
        return file

    def process_document(
        self,
        file_path: str | Path,
        prompt: str = (
            "Provide the document's text content by paragraph"
            " and output it in JSON format, including the"
            " paragraph type (type) and text content (content)."
        ),
    ) -> Any:
        """Upload and process a document with Doubao.

        Args:
            file_path: Path to the document (PDF, etc.)
            prompt: Prompt for document processing

        Returns:
            Response from Doubao
        """
        file = self.upload_file(file_path)

        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_id": file.id,
                        },
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )
        return response

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        """Standard chat completion (if supported by endpoint)."""
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )


class LLMClient:
    """OpenAI-compatible LLM client."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize LLM client.

        Args:
            api_key: API key (defaults to BM_LLM_API_KEY)
            base_url: Base URL (defaults to BM_LLM_BASE_URL)
            model: Model name (defaults to BM_LLM_MODEL)
        """
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("openai package not installed") from e

        self._api_key = api_key or settings.llm_api_key
        self._base_url = base_url or settings.llm_base_url
        self._model = model or settings.llm_model

        if not self._api_key:
            raise ValueError("LLM API key not configured")

        # Build client kwargs
        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        self._client = AsyncOpenAI(**client_kwargs)

    @property
    def model(self) -> str:
        """Return the model name."""
        return self._model or "gpt-3.5-turbo"

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> str:
        """Generate text completion.

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-2)
            system_prompt: Optional system prompt

        Returns:
            Generated text
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    async def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.3,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON output.

        Args:
            prompt: User prompt
            schema: JSON schema for output
            temperature: Sampling temperature
            system_prompt: Optional system prompt

        Returns:
            Parsed JSON response
        """
        import json

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append(
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\nRespond with valid JSON"
                    f" matching this schema:\n"
                    f"{json.dumps(schema)}"
                ),
            }
        )

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding (if LLM supports it)."""
        resp = await self._client.embeddings.create(input=text, model=self.model)
        return resp.data[0].embedding


def get_llm_client() -> LLMClient | None:
    """Factory: return configured LLM client or None."""
    if not settings.llm_api_key:
        return None
    return LLMClient()


def get_doubao_client() -> DoubaoClient | None:
    """Factory: return Doubao client or None."""
    if not settings.doubao_api_key:
        return None
    return DoubaoClient()
