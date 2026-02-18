"""AI package exports for LLM clients and prompt templates."""

from src.ai.llm_client import BaseLLMClient, OllamaClient, OpenAIClient, get_llm_client
from src.ai.prompts import extract_skills_prompt, job_scoring_prompt

__all__ = [
    "BaseLLMClient",
    "OllamaClient",
    "OpenAIClient",
    "extract_skills_prompt",
    "get_llm_client",
    "job_scoring_prompt",
]
