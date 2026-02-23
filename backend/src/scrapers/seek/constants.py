"""Seek scraper constants and selector fallback chains."""

from __future__ import annotations

BASE_URL = "https://www.seek.com.au"
SEARCH_URL = f"{BASE_URL}/jobs"
PLATFORM = "seek"
MAX_LIMIT = 20
SHORT_DESCRIPTION_MAX_LENGTH = 360

JOB_CARD_SELECTORS = (
    'article[data-testid="job-card"]',
    "article",
)

TITLE_LINK_SELECTORS = (
    'a[data-automation="jobTitle"]',
    'a[data-automation="job-title"]',
    "a[href*='/job/']",
)

COMPANY_SELECTORS = (
    'a[data-automation="jobCompany"]',
    'span[data-automation="jobCompany"]',
)

LOCATION_SELECTORS = (
    'a[data-automation="jobLocation"]',
    'span[data-automation="jobLocation"]',
)

CARD_SNIPPET_SELECTORS = (
    'span[data-automation="jobShortDescription"]',
    'div[data-automation="jobShortDescription"]',
)

DESCRIPTION_SELECTORS = (
    'div[data-automation="jobAdDetails"]',
    'div[data-automation="job-description"]',
)

DESCRIPTION_HTML_SELECTORS = (
    'article[data-automation="jobAdDetails"]',
    'section[data-automation="jobAdDetails"]',
    'div[data-automation="jobAdDetails"]',
    'div[data-automation="job-description"]',
)

DESCRIPTION_HTML_FALLBACK_SELECTORS = (
    "main",
    "article",
    '[data-testid="job-details"]',
)

CLASSIFICATIONS_SELECTORS = (
    '*[data-automation="job-detail-classifications"]',
    '*[data-automation="jobClassifications"]',
)

WORK_TYPE_SELECTORS = (
    '*[data-automation="job-detail-work-type"]',
    '*[data-automation="jobDetailWorkType"]',
)

LOCATION_DETAIL_SELECTORS = (
    '*[data-automation="job-detail-location"]',
    '*[data-automation="jobDetailLocation"]',
)

DATE_POSTED_SELECTORS = (
    '*[data-automation="job-detail-date"]',
    '*[data-automation="jobDetailDate"]',
    '*[data-automation="jobDate"]',
)

SALARY_SELECTORS = (
    '*[data-automation="job-detail-salary"]',
    '*[data-automation="jobSalary"]',
)

JOB_TYPE_HINTS = ("full time", "part time", "contract", "casual", "temporary")
