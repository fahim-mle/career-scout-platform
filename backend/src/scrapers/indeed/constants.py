"""Indeed scraper constants and selector fallbacks."""

from __future__ import annotations

BASE_URL = "https://au.indeed.com"
SEARCH_URL = f"{BASE_URL}/jobs"
PLATFORM = "indeed"
MAX_LIMIT = 10
SHORT_DESCRIPTION_MAX_LENGTH = 360

JOB_CARD_SELECTORS = (
    "div[data-jk]",
    "article[data-jk]",
    "div.job_seen_beacon",
)

TITLE_LINK_SELECTORS = (
    "h2.jobTitle a",
    "a.jcs-JobTitle",
    "a[data-jk]",
    "a[href*='/viewjob']",
)

COMPANY_SELECTORS = (
    '[data-testid="company-name"]',
    "span.companyName",
    "a[data-testid='company-name']",
)

LOCATION_SELECTORS = (
    '[data-testid="job-location"]',
    '[data-testid="text-location"]',
    "div.companyLocation",
)

CARD_SNIPPET_SELECTORS = (
    '[data-testid="jobsnippet_footer"]',
    '[data-testid="job-snippet"]',
    "div.job-snippet",
)

DESCRIPTION_SELECTORS = (
    "#jobDescriptionText",
    "div#jobDescriptionText",
    "main",
)

DESCRIPTION_HTML_SELECTORS = (
    "#jobDescriptionText",
    'div[data-testid="jobsearch-JobComponent-description"]',
    'section[data-testid="jobsearch-jobDescriptionContainer"]',
)

DESCRIPTION_HTML_FALLBACK_SELECTORS = (
    "main",
    "article",
    "body",
)

SALARY_AND_TYPE_SELECTORS = (
    "#salaryInfoAndJobType",
    '[data-testid="salaryInfoAndJobType"]',
    "div.jobsearch-JobMetadataHeader-item",
)

METADATA_LOCATION_SELECTORS = (
    '[data-testid="job-location"]',
    '[data-testid="text-location"]',
    'div[data-testid="jobsearch-JobInfoHeader-subtitle"] div',
    "div.jobsearch-JobInfoHeader-subtitle div",
)

DATE_POSTED_SELECTORS = (
    '[data-testid="jobsearch-JobMetadataFooter"]',
    "div.jobsearch-JobMetadataFooter",
    '[data-testid="myJobsStateDate"]',
    "span.date",
)

SALARY_TEXT_SELECTORS = (
    '#salaryInfoAndJobType span:has-text("$")',
    '[data-testid="salaryInfoAndJobType"]',
    "div.jobsearch-JobMetadataHeader-item",
)

COMPANY_RATING_SELECTORS = (
    '[data-testid="company-rating"]',
    "span.icl-Ratings-starsCountWrapper",
    "div.jobsearch-CompanyReview--heading",
)

BENEFITS_ITEM_SELECTORS = (
    '[data-testid="benefitItem"]',
    "ul#benefits li",
    'section[data-testid="benefits"] li',
)

HEADER_JOB_TYPE_SELECTORS = (
    "div.jobsearch-JobMetadataHeader-item",
    '[data-testid="jobsearch-JobMetadataHeader-item"]',
)

POPUP_CLOSE_SELECTORS = (
    'button[aria-label="Close"]',
    'button[aria-label="close"]',
    '[data-testid="closeButton"]',
    "button.icl-Modal-close",
)

JOB_TYPE_HINTS = (
    "full-time",
    "part-time",
    "contract",
    "temporary",
    "casual",
    "internship",
)
