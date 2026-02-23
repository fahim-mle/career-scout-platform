"""LinkedIn scraper constants and selector fallbacks."""

from __future__ import annotations

import re

BASE_URL = "https://www.linkedin.com"
LOGIN_URL = f"{BASE_URL}/login"
SEARCH_URL = f"{BASE_URL}/jobs/search/"
PLATFORM = "linkedin"
MAX_LIMIT = 10

CHALLENGE_URL_CUES = ("checkpoint", "challenge", "captcha")
CHALLENGE_SELECTORS = (
    "form[action*='checkpoint/challenge']",
    "iframe[src*='captcha']",
    "input[name='captcha']",
    "#captcha-internal",
    "[data-test-id*='challenge']",
)

JITTER_MIN_SECONDS = 0.2
JITTER_MAX_SECONDS = 0.8

DESCRIPTION_SELECTORS = (
    ".show-more-less-html__markup",
    ".jobs-description-content__text",
    ".jobs-description__content",
    "div.jobs-description-content__text--stretch",
    "#job-details",
    ".description__text",
    ".jobs-box__html-content",
    ".jobs-description__container",
)

DESCRIPTION_SHOW_MORE_SELECTORS = (
    "button.show-more-less-html__button",
    "button[aria-label*='Show more']",
    "button[aria-label*='See more']",
)

DESCRIPTION_HTML_SELECTORS = (
    "#job-details",
    "div.jobs-box__html-content",
    "section.show-more-less-html",
    "div.show-more-less-html__markup",
    "div.jobs-description-content__text--stretch",
    "div.jobs-description-content__text",
    "div.jobs-description__content",
)

CARD_SNIPPET_SELECTORS = (
    ".job-search-card__snippet",
    ".job-card-list__description",
    ".base-search-card__metadata",
    ".job-search-card__snippet-wrapper",
)

DESCRIPTION_FALLBACK_SELECTORS = ("main", "section", "article", "body")

MAX_DETAIL_EXTRACTION_ATTEMPTS = 2
SHORT_DESCRIPTION_MAX_LENGTH = 360
MAX_DESCRIPTION_FULL_LENGTH = 3_000
MAX_FALLBACK_DESCRIPTION_HTML_LENGTH = 100_000

DESCRIPTION_END_MARKERS = (
    "Set alert for similar jobs",
    "Interested in working with us in the future?",
    "Looking for talent? Post a job",
    "About the company",
)

DESCRIPTION_TRAILING_MORE_PATTERN = re.compile(
    r"(?:\.\.\.|…)\s*more\s*$", re.IGNORECASE
)

JOB_CARD_SELECTORS = (
    "ul.jobs-search__results-list li",
    "ul.scaffold-layout__list-container li.jobs-search-results__list-item",
    "li.jobs-search-results__list-item",
    "[data-occludable-job-id]",
    "li.scaffold-layout__list-item",
    "div.scaffold-layout__list-container li",
)

JOB_LINK_SELECTORS = (
    "a.base-card__full-link",
    "a.job-card-container__link",
    "a.job-card-list__title--link",
    "a[data-control-name='job_card_click']",
)

TITLE_SELECTORS = (
    "h3.base-search-card__title",
    "a.job-card-list__title--link",
    ".job-card-list__title",
    "h3 a",
)

COMPANY_SELECTORS = (
    "h4.base-search-card__subtitle",
    ".job-card-container__company-name",
    "a.job-card-container__company-name",
    ".artdeco-entity-lockup__subtitle span",
)

LOCATION_SELECTORS = (
    "span.job-search-card__location",
    ".job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption span",
)

DETAIL_JOB_TYPE_SELECTORS = (
    ".job-details-jobs-unified-top-card__job-insight",
    ".jobs-unified-top-card__job-insight",
    ".jobs-unified-top-card__workplace-type",
)

TOP_CARD_METADATA_SELECTORS = (
    ".job-details-jobs-unified-top-card__primary-description-container",
    ".job-details-jobs-unified-top-card__tertiary-description-container",
    ".jobs-unified-top-card__primary-description-container",
    ".jobs-unified-top-card__subtitle-primary-grouping",
)

JOB_TYPE_HINTS = (
    "full-time",
    "part-time",
    "contract",
    "internship",
    "temporary",
    "freelance",
    "casual",
)
