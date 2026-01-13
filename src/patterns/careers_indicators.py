"""Shared patterns for careers URL detection."""

from __future__ import annotations

import re
from urllib.parse import urlparse

CAREERS_PATH_PATTERNS = [
    r"/careers?/?",
    r"/jobs?/?",
    r"/join[-_]?us/?",
    r"/work[-_]?(with[-_]?us|here|at[-_]?[a-z0-9_-]+)/?",
    r"/opportunities/?",
    r"/openings/?",
    r"/vacancies/?",
    r"/hiring/?",
    r"/employment/?",
    r"/team/?",
    r"/people/?",
    r"/about[-_]?us/careers?/?",
    r"/company/careers?/?",
    r"/en/careers/?",
]

CAREERS_LINK_TEXT = [
    "careers",
    "career",
    "jobs",
    "join us",
    "join our team",
    "work with us",
    "work here",
    "we are hiring",
    "we're hiring",
    "hiring",
    "open positions",
    "view all jobs",
    "see all jobs",
    "opportunities",
    "vacancies",
    "employment",
]

CAREERS_PATH_RE = re.compile("|".join(CAREERS_PATH_PATTERNS), re.IGNORECASE)
CAREERS_PAGE_INDICATORS = [
    r"open\\s+positions?",
    r"current\\s+openings?",
    r"job\\s+listings?",
    r"career\\s+opportunities",
    r"join\\s+our\\s+team",
    r"we('re|\\s+are)\\s+hiring",
    r"view\\s+(all\\s+)?jobs?",
    r"search\\s+(for\\s+)?jobs?",
]
CAREERS_PAGE_RE = re.compile("|".join(CAREERS_PAGE_INDICATORS), re.IGNORECASE)


def has_careers_indicator(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    path = parsed.path or ""
    return bool(CAREERS_PATH_RE.search(path))


def has_careers_text(text: str) -> bool:
    if not text:
        return False
    text = " ".join(text.lower().split())
    return any(term in text for term in CAREERS_LINK_TEXT)


def is_careers_page(html: str) -> bool:
    if not html:
        return False
    return bool(CAREERS_PAGE_RE.search(html))
