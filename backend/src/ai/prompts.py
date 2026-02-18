"""Prompt templates for AI relevance scoring workflows."""

from __future__ import annotations

import json
from typing import Any


def job_scoring_prompt(job_data: dict[str, Any], profile_data: dict[str, Any]) -> str:
    """Build a deterministic prompt for job relevance scoring.

    Args:
        job_data: Job posting details.
        profile_data: Candidate profile details.

    Returns:
        Prompt asking the model for JSON-only job relevance scoring.
    """
    serialized_job = json.dumps(job_data, ensure_ascii=True, sort_keys=True)
    serialized_profile = json.dumps(profile_data, ensure_ascii=True, sort_keys=True)

    return (
        "You are an ATS relevance scoring engine.\n"
        "Given candidate profile data and a job posting, output only strict JSON.\n"
        "No markdown, no code block fences, no commentary, and no surrounding text.\n"
        "\n"
        "Scoring rubric (integer 0-100):\n"
        "- 90-100: Strong skills and experience alignment, location/role fit\n"
        "- 70-89: Good alignment with minor gaps\n"
        "- 50-69: Partial alignment with notable gaps\n"
        "- 0-49: Weak alignment or major mismatch\n"
        "\n"
        "Response schema:\n"
        "{\n"
        '  "score": <integer 0-100>,\n'
        '  "category": "Most Relevant" | "Relevant" | "Somewhat Relevant" | "Not Relevant",\n'
        '  "explanation": "2-3 concise sentences"\n'
        "}\n"
        "\n"
        "Candidate profile JSON:\n"
        f"{serialized_profile}\n"
        "\n"
        "Job posting JSON:\n"
        f"{serialized_job}\n"
    )


def extract_skills_prompt(job_description: str) -> str:
    """Build a deterministic prompt to extract technical skills.

    Args:
        job_description: Full or partial job description text.

    Returns:
        Prompt asking the model for JSON-only skill extraction.
    """
    clean_description = job_description.strip()

    return (
        "Extract concrete technical skills from the provided job description.\n"
        "Return only strict JSON with no additional text, explanation, or markdown.\n"
        "Include only tools, languages, frameworks, platforms, certifications, and databases.\n"
        "Exclude soft skills and generic traits.\n"
        "\n"
        "Response schema:\n"
        "{\n"
        '  "skills": ["skill one", "skill two"]\n'
        "}\n"
        "\n"
        "Job description:\n"
        f"{clean_description}\n"
    )


__all__ = ["extract_skills_prompt", "job_scoring_prompt"]
