"""Shared patterns for careers URL detection."""

from __future__ import annotations

import re
from urllib.parse import urlparse

CAREERS_PATH_PATTERNS = [
    r"/careers?/?$",
    r"/jobs?/?$",
    r"/join[-_]?us/?$",
    r"/work[-_]?(with[-_]?us|here|at)/?$",
    r"/opportunities/?$",
    r"/openings/?$",
    r"/vacancies/?$",
    r"/hiring/?$",
]

CAREERS_LINK_TEXT = [
    "careers",
    "jobs",
    "join us",
    "join our team",
    "work with us",
    "we are hiring",
    "open positions",
    "view all jobs",
]

CAREERS_PATH_RE = re.compile("|".join(CAREERS_PATH_PATTERNS), re.IGNORECASE)


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
