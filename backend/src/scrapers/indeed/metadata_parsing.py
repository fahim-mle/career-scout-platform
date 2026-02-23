"""Indeed detail-page metadata parsing helpers."""

from __future__ import annotations

import re
from typing import Any


class IndeedMetadataParsingMixin:
    """Metadata extraction behavior for Indeed detail pages."""

    async def _extract_metadata(
        self,
        salary_type_text: str | None,
        job_type: str | None,
    ) -> dict[str, Any]:
        """Extract structured metadata from Indeed detail page.

        Args:
            salary_type_text: Optional salary/type container text.
            job_type: Optional parsed job type from helper extraction.

        Returns:
            JSON-serializable metadata dictionary with available keys.
        """
        metadata: dict[str, Any] = {"platform": self.PLATFORM}

        location_text = await self._extract_text_from_page_selectors(
            selectors=self.METADATA_LOCATION_SELECTORS
        )
        if location_text:
            metadata["location"] = location_text

        date_posted_text = await self._extract_text_from_page_selectors(
            selectors=self.DATE_POSTED_SELECTORS
        )
        if date_posted_text:
            metadata["date_posted"] = date_posted_text

        work_type = job_type
        if not work_type and salary_type_text:
            work_type = self._extract_job_type_from_text(salary_type_text)
        if not work_type:
            work_type_text = await self._extract_text_from_page_selectors(
                selectors=self.HEADER_JOB_TYPE_SELECTORS
            )
            if work_type_text:
                work_type = self._extract_job_type_from_text(work_type_text)
        if work_type:
            metadata["work_type"] = work_type

        salary_text = self._extract_salary_text(salary_type_text)
        if not salary_text:
            salary_text = self._extract_salary_text(
                await self._extract_text_from_page_selectors(
                    selectors=self.SALARY_TEXT_SELECTORS
                )
            )
        if salary_text:
            metadata["salary_text"] = salary_text

        company_rating = await self._extract_company_rating()
        if company_rating:
            metadata["company_rating"] = company_rating

        benefits = await self._extract_benefits()
        if benefits:
            metadata["benefits"] = benefits

        return metadata

    async def _extract_job_type(self, salary_type_text: str | None) -> str | None:
        """Extract job type from salary/type area and metadata fallback.

        Args:
            salary_type_text: Optional text from salary/type container.

        Returns:
            Inferred job type value when found.
        """
        if salary_type_text:
            parsed = self._extract_job_type_from_text(salary_type_text)
            if parsed:
                return parsed

        metadata_text = await self._extract_text_from_page_selectors(
            selectors=self.HEADER_JOB_TYPE_SELECTORS
        )
        if not metadata_text:
            return None
        return self._extract_job_type_from_text(metadata_text)

    async def _extract_company_rating(self) -> str | None:
        """Extract normalized company rating text from detail page.

        Returns:
            Company rating string when available, otherwise ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        rating_text = await self._extract_text_from_page_selectors(
            selectors=self.COMPANY_RATING_SELECTORS
        )
        if not rating_text:
            return None

        match = re.search(r"\b\d(?:\.\d)?\s*/\s*5\b", rating_text)
        if match:
            return self._normalize_text(match.group(0))
        return rating_text

    async def _extract_benefits(self) -> list[str] | None:
        """Extract benefits list from detail page selectors.

        Returns:
            Ordered list of benefits when found, otherwise ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for selector in self.BENEFITS_ITEM_SELECTORS:
            elements = await self.page.query_selector_all(selector)
            if not elements:
                continue

            values: list[str] = []
            for element in elements:
                try:
                    text_value = await element.inner_text()
                except Exception:
                    continue
                normalized = self._normalize_text(text_value)
                if normalized:
                    values.append(normalized)

            unique_values = self._dedupe_preserve_order(values)
            if unique_values:
                return unique_values

        return None

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        """Return unique values while preserving original order.

        Args:
            values: Raw string values.

        Returns:
            Deduplicated list with deterministic ordering.
        """
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            deduped.append(value)
            seen.add(value)
        return deduped

    @classmethod
    def _extract_salary_text(cls, value: str | None) -> str | None:
        """Extract a salary-like text snippet from mixed metadata text.

        Args:
            value: Candidate metadata text.

        Returns:
            Normalized salary text when detected, otherwise ``None``.
        """
        normalized = cls._normalize_text(value or "")
        if not normalized:
            return None

        if "$" in normalized or "aud" in normalized.lower():
            return normalized
        return None

    @classmethod
    def _extract_job_type_from_text(cls, value: str) -> str | None:
        """Infer normalized job type from free text.

        Args:
            value: Raw metadata text.

        Returns:
            Canonicalized job type label when hint is found.
        """
        normalized = cls._normalize_text(value)
        if not normalized:
            return None

        lowered = normalized.lower()
        for hint in cls.JOB_TYPE_HINTS:
            if hint in lowered:
                return hint.title()
        return None

    @classmethod
    def _extract_salary_range(cls, value: str) -> dict[str, Any] | None:
        """Extract salary range from salary metadata text.

        Args:
            value: Raw salary text from detail page.

        Returns:
            Structured salary range dictionary when both bounds are present.
        """
        normalized = cls._normalize_text(value)
        if not normalized:
            return None

        matches = re.findall(r"(?:AUD\s*)?\$\s*([\d,.]+)\s*([kK]?)", normalized)
        if len(matches) < 2:
            return None

        min_value = cls._parse_salary_number(matches[0][0], bool(matches[0][1]))
        max_value = cls._parse_salary_number(matches[1][0], bool(matches[1][1]))
        if min_value is None or max_value is None:
            return None
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        return {
            "min": min_value,
            "max": max_value,
            "currency": "AUD",
            "raw": normalized,
        }

    @staticmethod
    def _parse_salary_number(value: str, has_k_suffix: bool) -> int | None:
        """Parse a salary number token to integer value.

        Args:
            value: Numeric token string.
            has_k_suffix: Whether token had a ``k`` suffix.

        Returns:
            Parsed integer salary value, otherwise ``None``.
        """
        compact = value.replace(",", "").strip()
        if not compact:
            return None

        try:
            number = float(compact)
        except ValueError:
            return None

        if has_k_suffix:
            number *= 1000

        return int(number)
