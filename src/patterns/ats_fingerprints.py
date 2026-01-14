"""Lightweight ATS fingerprint detection from HTML."""

from __future__ import annotations

import re


FINGERPRINT_PATTERNS: dict[str, list[re.Pattern]] = {
    "GREENHOUSE": [
        re.compile(r"greenhouse\.io", re.IGNORECASE),
        re.compile(r"boards\.greenhouse\.io", re.IGNORECASE),
        re.compile(r"data-grnhse", re.IGNORECASE),
    ],
    "LEVER": [
        re.compile(r"lever\.co", re.IGNORECASE),
        re.compile(r"posting-title", re.IGNORECASE),
        re.compile(r"lever-app", re.IGNORECASE),
    ],
    "ASHBY": [
        re.compile(r"ashbyhq", re.IGNORECASE),
        re.compile(r"__ashby__", re.IGNORECASE),
        re.compile(r"jobs\.ashbyhq\.com", re.IGNORECASE),
    ],
    "WORKABLE": [
        re.compile(r"workable\.com", re.IGNORECASE),
        re.compile(r"apply\.workable\.com", re.IGNORECASE),
    ],
    "WORKDAY": [
        re.compile(r"myworkdayjobs", re.IGNORECASE),
        re.compile(r"/wd\\d+/", re.IGNORECASE),
    ],
    "SMARTRECRUITERS": [
        re.compile(r"smartrecruiters\.com", re.IGNORECASE),
    ],
}


def detect_fingerprints(html: str) -> set[str]:
    if not html:
        return set()
    hits: set[str] = set()
    for ats_name, patterns in FINGERPRINT_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(html):
                hits.add(ats_name)
                break
    return hits
