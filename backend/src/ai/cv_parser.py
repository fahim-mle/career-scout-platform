"""CV text extraction and LLM-based summarisation."""

from __future__ import annotations

import io

from loguru import logger

from src.ai.prompts import cv_summary_prompt
from src.core.exceptions import BusinessLogicError

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document",
}


def extract_text_from_file(file_bytes: bytes, mime_type: str) -> str:
    """Extract plain text from a PDF or DOCX file.

    Args:
        file_bytes: Raw file content.
        mime_type: MIME type of the uploaded file.

    Returns:
        Extracted plain text from the document.

    Raises:
        BusinessLogicError: If the file type is unsupported or
            extraction fails.
    """
    log = logger.bind(mime_type=mime_type, size=len(file_bytes))

    if mime_type == "application/pdf":
        return _extract_pdf_text(file_bytes, log)

    if mime_type == (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ):
        return _extract_docx_text(file_bytes, log)

    log.warning("Unsupported CV file type")
    raise BusinessLogicError(
        f"Unsupported file type: {mime_type}. "
        "Only PDF and DOCX files are accepted."
    )


def _extract_pdf_text(file_bytes: bytes, log: object) -> str:
    """Extract text from PDF bytes using pypdf.

    Args:
        file_bytes: Raw PDF content.
        log: Bound logger instance.

    Returns:
        Concatenated text from all PDF pages.

    Raises:
        BusinessLogicError: If PDF parsing fails.
    """
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        log.bind(pages=len(reader.pages)).info("Extracted PDF text")
        return text
    except Exception as exc:
        log.bind(error=str(exc)).error("Failed to extract PDF text")
        raise BusinessLogicError(
            "Failed to extract text from PDF."
        ) from exc


def _extract_docx_text(file_bytes: bytes, log: object) -> str:
    """Extract text from DOCX bytes using python-docx.

    Args:
        file_bytes: Raw DOCX content.
        log: Bound logger instance.

    Returns:
        Concatenated paragraph text from the document.

    Raises:
        BusinessLogicError: If DOCX parsing fails.
    """
    try:
        from docx import Document  # type: ignore[import-untyped]

        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        log.bind(paragraphs=len(paragraphs)).info("Extracted DOCX text")
        return text
    except Exception as exc:
        log.bind(error=str(exc)).error("Failed to extract DOCX text")
        raise BusinessLogicError(
            "Failed to extract text from DOCX."
        ) from exc


async def parse_cv_with_llm(raw_text: str, llm_client: object) -> str:
    """Summarise raw CV text into a concise profile description via LLM.

    Args:
        raw_text: Plain text extracted from the uploaded CV.
        llm_client: LLM client instance with a ``generate`` method.

    Returns:
        Plain-text CV summary suitable for storage in ``resume_text``.

    Raises:
        BusinessLogicError: If the LLM call fails.
    """
    log = logger.bind(raw_text_length=len(raw_text))
    log.info("Summarising CV text with LLM")

    if not raw_text.strip():
        raise BusinessLogicError(
            "CV file contains no extractable text."
        )

    prompt = cv_summary_prompt(raw_text)

    try:
        summary = await llm_client.generate(prompt, temperature=0.3)
        log.bind(summary_length=len(summary)).info("CV summarised")
        return summary.strip()
    except Exception as exc:
        log.bind(error=str(exc)).error("LLM CV summarisation failed")
        raise BusinessLogicError(
            "Failed to summarise CV with LLM."
        ) from exc


__all__ = [
    "ALLOWED_MIME_TYPES",
    "extract_text_from_file",
    "parse_cv_with_llm",
]
