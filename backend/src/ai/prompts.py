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
    serialized_job = json.dumps(job_data, ensure_ascii=False, sort_keys=True)
    serialized_profile = json.dumps(profile_data, ensure_ascii=False, sort_keys=True)

    return (
        "You are an ATS relevance scoring engine.\n"
        "Given candidate profile data and a job posting, output only strict JSON.\n"
        "No markdown, no code block fences, no commentary, and no surrounding text.\n"
        "\n"
        "Scoring rubric (integer 0-100):\n"
        '- 90-100 => category "Most Relevant": Strong skills and experience alignment, location/role fit\n'
        '- 70-89 => category "Relevant": Good alignment with minor gaps\n'
        '- 50-69 => category "Somewhat Relevant": Partial alignment with notable gaps\n'
        '- 0-49 => category "Not Relevant": Weak alignment or major mismatch\n'
        "Use the category that matches the selected score range.\n"
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


def cv_summary_prompt(raw_cv_text: str) -> str:
    """Build a prompt to summarise raw CV text into a concise profile description.

    Args:
        raw_cv_text: Raw text extracted from the uploaded CV file.

    Returns:
        Prompt asking the model for a plain-text CV summary.
    """
    clean_text = raw_cv_text.strip()

    return (
        "You are a CV parsing assistant.\n"
        "Read the raw CV text below and produce a concise plain-text"
        " summary.\n"
        "Include: key technical skills, years of experience, education,"
        " and a brief work history.\n"
        "Do not use markdown, bullet points, headers, or JSON.\n"
        "Write in plain prose, maximum 300 words.\n"
        "\n"
        "CV text:\n"
        f"{clean_text}\n"
    )


__all__ = ["cv_summary_prompt", "extract_skills_prompt", "job_scoring_prompt"]
