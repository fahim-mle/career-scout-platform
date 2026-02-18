#!/usr/bin/env python3
"""Smoke tests for LLM client abstraction."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.ai.llm_client import BaseLLMClient, OpenAIClient, get_llm_client
from src.ai.prompts import job_scoring_prompt


async def test_basic_generation(client: BaseLLMClient) -> None:
    """Test basic text generation via configured provider.

    Args:
        client: Configured LLM client.

    Raises:
        AssertionError: If generation returns an empty response.
    """
    logger.info("Starting basic generation test")
    response = await client.generate(
        "Reply with one short sentence: Hello from Career Scout."
    )
    if not response.strip():
        raise AssertionError("Basic generation returned empty response")
    logger.bind(response_preview=response[:120]).info("Basic generation test passed")


async def test_json_parsing(client: BaseLLMClient) -> None:
    """Test JSON generation and parsing helper.

    Args:
        client: Configured LLM client.

    Raises:
        AssertionError: If parsed JSON does not match expected shape.
    """
    logger.info("Starting JSON parsing test")
    prompt = (
        "Return only strict JSON in exactly this shape: "
        '{"status": "success", "message": "Test passed"}'
    )
    payload = await client.generate_json(prompt=prompt)
    if payload.get("status") != "success":
        raise AssertionError("JSON parsing test returned unexpected status value")
    if "message" not in payload:
        raise AssertionError("JSON parsing test missing message field")
    logger.bind(parsed_json=payload).info("JSON parsing test passed")


async def test_job_scoring_prompt_flow(client: BaseLLMClient) -> None:
    """Test end-to-end job scoring prompt and JSON response flow.

    Args:
        client: Configured LLM client.

    Raises:
        AssertionError: If required scoring fields are missing or invalid.
    """
    logger.info("Starting job scoring prompt flow test")
    job_data = {
        "title": "Senior Python Backend Engineer",
        "company": "Acme Tech",
        "location": "Brisbane",
        "description_full": "Seeking Python, FastAPI, PostgreSQL, Redis, and Docker skills.",
    }
    profile_data = {
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "experience_years": 5,
        "location": "Brisbane",
        "preferences": {"work_type": "hybrid"},
    }

    prompt = job_scoring_prompt(job_data=job_data, profile_data=profile_data)
    score_payload = await client.generate_json(prompt=prompt)

    required_fields = {"score", "category", "explanation"}
    if not required_fields.issubset(score_payload):
        raise AssertionError("Job scoring payload missing required fields")

    score_value = score_payload.get("score")
    if not isinstance(score_value, int) or score_value < 0 or score_value > 100:
        raise AssertionError("Job scoring payload contains invalid score")

    logger.bind(score_payload=score_payload).info("Job scoring prompt flow test passed")


async def run_tests() -> int:
    """Run all LLM client smoke tests.

    Returns:
        Exit status code (0 for success, non-zero for failure).
    """
    logger.info("Initializing LLM client smoke tests")
    client: BaseLLMClient | None = None
    try:
        client = get_llm_client()
        if isinstance(client, OpenAIClient):
            logger.error(
                "Configured LLM provider resolved to OpenAI, but OpenAIClient is not implemented"
            )
            return 2

        await test_basic_generation(client)
        await test_json_parsing(client)
        await test_job_scoring_prompt_flow(client)
        logger.info("All LLM client smoke tests passed")
        return 0
    except Exception as exc:
        logger.error("LLM client smoke tests failed: {}", exc)
        logger.exception("Detailed test failure traceback")
        return 1
    finally:
        if client is not None:
            close_client = getattr(client, "aclose", None)
            if callable(close_client):
                close_result = close_client()
                if asyncio.iscoroutine(close_result):
                    await close_result


def main() -> int:
    """Entrypoint for script execution.

    Returns:
        Exit status code from async test runner.
    """
    return asyncio.run(run_tests())


if __name__ == "__main__":
    raise SystemExit(main())
