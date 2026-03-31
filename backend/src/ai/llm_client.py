"""LLM client abstractions and provider implementations."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

import httpx
from loguru import logger

from src.core.config import settings


class BaseLLMClient(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text from a prompt.

        Args:
            prompt: Prompt text sent to the model.
            temperature: Sampling temperature.
            max_tokens: Optional max number of tokens to generate.

        Returns:
            Generated model text.

        Raises:
            Exception: Provider-specific failures during generation.
        """

    async def generate_json(
        self,
        prompt: str,
        temperature: float = 0.5,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Generate and parse a JSON object response from the model.

        Args:
            prompt: Prompt text asking for JSON output.
            temperature: Sampling temperature.
            max_tokens: Optional max number of tokens to generate.
            max_retries: Maximum generation+parse attempts.

        Returns:
            Parsed JSON object.

        Raises:
            ValueError: If JSON cannot be extracted or parsed.
            RuntimeError: If generation fails for all retry attempts.
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")

        for attempt in range(1, max_retries + 1):
            response_text: str = ""
            try:
                response_text = await self.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                parsed_json = self._extract_json_object(response_text)
                logger.bind(
                    attempt=attempt,
                    max_retries=max_retries,
                ).info("LLM JSON response parsed successfully")
                return parsed_json
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.bind(
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                    response_preview=response_text[:300],
                ).warning("Failed to parse JSON response from LLM")
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                raise ValueError(
                    f"Failed to parse JSON response after {max_retries} attempts"
                ) from exc
            except Exception as exc:
                logger.bind(
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                ).error("LLM JSON generation request failed", exc_info=True)
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                raise RuntimeError(
                    f"LLM JSON generation failed after {max_retries} attempts"
                ) from exc

    @staticmethod
    def _extract_json_object(response_text: str) -> dict[str, Any]:
        """Extract a JSON object from potentially noisy response text.

        Args:
            response_text: Raw model output that may include extra text.

        Returns:
            Parsed JSON object.

        Raises:
            ValueError: If no valid JSON object is found.
        """
        decoder = json.JSONDecoder()
        candidates: list[int] = [
            index for index, char in enumerate(response_text) if char in "[{"
        ]

        for start_index in candidates:
            try:
                parsed, _ = decoder.raw_decode(response_text[start_index:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        raise ValueError("No valid JSON object found in LLM response")


class OllamaClient(BaseLLMClient):
    """Ollama LLM client for local inference."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> None:
        """Initialize Ollama client configuration.

        Args:
            base_url: Ollama base URL.
            model: Model name to run.
            timeout: Request timeout config. If omitted, uses conservative
                defaults with longer read timeout for model generation.
        """
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        if timeout is None:
            self.timeout = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)
        elif isinstance(timeout, httpx.Timeout):
            self.timeout = timeout
        else:
            self.timeout = httpx.Timeout(timeout)

        self._client = httpx.AsyncClient(timeout=self.timeout)

        logger.bind(
            provider="ollama",
            base_url=self.base_url,
            model=self.model,
            timeout=str(self.timeout),
        ).info("Initialized Ollama client")

    async def aclose(self) -> None:
        """Close underlying HTTP resources.

        Returns:
            None.
        """
        if not self._client.is_closed:
            await self._client.aclose()
            logger.bind(provider="ollama", model=self.model).info(
                "Closed Ollama HTTP client"
            )

    async def __aenter__(self) -> OllamaClient:
        """Enter async context manager for resource reuse.

        Returns:
            Current Ollama client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager and close resources.

        Args:
            exc_type: Exception type raised in context, if any.
            exc_val: Exception instance raised in context, if any.
            exc_tb: Traceback object for context exception, if any.

        Returns:
            None.
        """
        await self.aclose()

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text using the Ollama API.

        Args:
            prompt: Prompt text sent to the model.
            temperature: Sampling temperature.
            max_tokens: Optional max number of tokens to generate.

        Returns:
            Generated text from Ollama.

        Raises:
            ValueError: If Ollama returns an unexpected payload.
            httpx.HTTPError: If the request fails.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        logger.bind(
            provider="ollama",
            endpoint=f"{self.base_url}/api/generate",
            model=self.model,
            prompt_length=len(prompt),
            temperature=temperature,
            max_tokens=max_tokens,
        ).info("Sending generation request to Ollama")

        try:
            response = await self._client.post(
                url=f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            response_data = response.json()

            generated_text = response_data.get("response")
            if not isinstance(generated_text, str):
                raise TypeError(
                    "Ollama response did not include string field 'response'"
                )

            logger.bind(
                provider="ollama",
                model=self.model,
                response_length=len(generated_text),
                eval_count=response_data.get("eval_count"),
                eval_duration_ns=response_data.get("eval_duration"),
            ).info("Ollama generation succeeded")
            return generated_text
        except httpx.HTTPError as exc:
            logger.bind(
                provider="ollama",
                endpoint=f"{self.base_url}/api/generate",
                model=self.model,
                error=str(exc),
            ).error("Ollama HTTP request failed", exc_info=True)
            raise
        except TypeError as exc:
            logger.bind(
                provider="ollama",
                model=self.model,
                error=str(exc),
            ).error("Invalid Ollama response payload", exc_info=True)
            raise


class OpenAIClient(BaseLLMClient):
    """OpenAI client placeholder for future implementation."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Initialize OpenAI client placeholder.

        Args:
            api_key: OpenAI API key.
            model: OpenAI model name.
        """
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        logger.bind(provider="openai", model=self.model).warning(
            "OpenAI client initialized but not implemented"
        )

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text using OpenAI.

        Args:
            prompt: Prompt text sent to the model.
            temperature: Sampling temperature.
            max_tokens: Optional max number of tokens to generate.

        Returns:
            Generated text.

        Raises:
            NotImplementedError: Always, until OpenAI integration is implemented.
        """
        logger.bind(
            provider="openai",
            model=self.model,
            prompt_length=len(prompt),
            temperature=temperature,
            max_tokens=max_tokens,
        ).error("OpenAI generation requested but client is not implemented")
        raise NotImplementedError("OpenAI client is not implemented yet")


def get_llm_client() -> BaseLLMClient:
    """Create an LLM client based on configured provider.

    Returns:
        Configured LLM client instance.

    Raises:
        ValueError: If the provider setting is unsupported.
    """
    provider = settings.LLM_PROVIDER.lower().strip()
    logger.bind(provider=provider).info("Resolving configured LLM client")

    if provider == "ollama":
        return OllamaClient()
    if provider == "openai":
        return OpenAIClient()

    logger.bind(provider=provider).error("Unsupported LLM provider configured")
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")


__all__ = [
    "BaseLLMClient",
    "OllamaClient",
    "OpenAIClient",
    "get_llm_client",
]
