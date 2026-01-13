"""ATS URL detection and normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class ATSPattern:
    name: str
    root_regex: re.Pattern
    job_regex: re.Pattern
    root_template: str
    slug_group: str = "slug"


def _strip_query_fragment(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    cleaned = parsed._replace(query="", fragment="")
    return urlunparse(cleaned)


def _normalize_url(url: str) -> str:
    cleaned = _strip_query_fragment(url)
    return cleaned.strip()


def _build_root(pattern: ATSPattern, match: re.Match) -> str:
    parts = match.groupdict()
    root = pattern.root_template.format(**parts)
    return root.rstrip("/")


PATTERNS = [
    ATSPattern(
        name="GREENHOUSE",
        root_regex=re.compile(r"https?://boards\.greenhouse\.io/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://boards\.greenhouse\.io/(?P<slug>[^/?#]+)/jobs/[^/?#]+", re.IGNORECASE),
        root_template="https://boards.greenhouse.io/{slug}",
    ),
    ATSPattern(
        name="GREENHOUSE",
        root_regex=re.compile(r"https?://job-boards\.greenhouse\.io/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://job-boards\.greenhouse\.io/(?P<slug>[^/?#]+)/jobs/[^/?#]+", re.IGNORECASE),
        root_template="https://job-boards.greenhouse.io/{slug}",
    ),
    ATSPattern(
        name="LEVER",
        root_regex=re.compile(r"https?://jobs\.lever\.co/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://jobs\.lever\.co/(?P<slug>[^/?#]+)/[^/?#]+", re.IGNORECASE),
        root_template="https://jobs.lever.co/{slug}",
    ),
    ATSPattern(
        name="WORKDAY",
        root_regex=re.compile(
            r"https?://(?P<tenant>[^./]+)\.wd(?P<wd>\d+)\.myworkdayjobs\.com/(?P<slug>[^/?#]+)/?",
            re.IGNORECASE,
        ),
        job_regex=re.compile(
            r"https?://(?P<tenant>[^./]+)\.wd(?P<wd>\d+)\.myworkdayjobs\.com/(?P<slug>[^/?#]+)/job/.*",
            re.IGNORECASE,
        ),
        root_template="https://{tenant}.wd{wd}.myworkdayjobs.com/{slug}",
    ),
    ATSPattern(
        name="WORKABLE",
        root_regex=re.compile(r"https?://apply\.workable\.com/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://apply\.workable\.com/(?P<slug>[^/?#]+)/j/[^/?#]+", re.IGNORECASE),
        root_template="https://apply.workable.com/{slug}",
    ),
    ATSPattern(
        name="SMARTRECRUITERS",
        root_regex=re.compile(r"https?://careers\.smartrecruiters\.com/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://careers\.smartrecruiters\.com/(?P<slug>[^/?#]+)/[^/?#]+", re.IGNORECASE),
        root_template="https://careers.smartrecruiters.com/{slug}",
    ),
    ATSPattern(
        name="ASHBY",
        root_regex=re.compile(r"https?://jobs\.ashbyhq\.com/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://jobs\.ashbyhq\.com/(?P<slug>[^/?#]+)/.*", re.IGNORECASE),
        root_template="https://jobs.ashbyhq.com/{slug}",
    ),
    ATSPattern(
        name="JOBVITE",
        root_regex=re.compile(r"https?://jobs\.jobvite\.com/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://jobs\.jobvite\.com/(?P<slug>[^/?#]+)/job/.*", re.IGNORECASE),
        root_template="https://jobs.jobvite.com/{slug}",
    ),
    ATSPattern(
        name="ICIMS",
        root_regex=re.compile(r"https?://careers-(?P<slug>[^./]+)\.icims\.com/jobs/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://careers-(?P<slug>[^./]+)\.icims\.com/jobs/[^/?#]+", re.IGNORECASE),
        root_template="https://careers-{slug}.icims.com/jobs",
    ),
    ATSPattern(
        name="BAMBOOHR",
        root_regex=re.compile(r"https?://(?P<slug>[^./]+)\.bamboohr\.com/careers/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://(?P<slug>[^./]+)\.bamboohr\.com/careers/[^/?#]+", re.IGNORECASE),
        root_template="https://{slug}.bamboohr.com/careers",
    ),
    ATSPattern(
        name="JAZZHR",
        root_regex=re.compile(r"https?://(?P<slug>[^./]+)\.applytojob\.com/?", re.IGNORECASE),
        job_regex=re.compile(r"https?://(?P<slug>[^./]+)\.applytojob\.com/apply/[^/?#]+", re.IGNORECASE),
        root_template="https://{slug}.applytojob.com",
    ),
]


def detect(url: str) -> Optional[tuple[str, str]]:
    cleaned = _normalize_url(url)
    for pattern in PATTERNS:
        for regex in (pattern.job_regex, pattern.root_regex):
            match = regex.match(cleaned)
            if match:
                slug = match.groupdict().get(pattern.slug_group, "")
                return pattern.name, slug
    return None


def normalize(url: str) -> str:
    cleaned = _normalize_url(url)
    for pattern in PATTERNS:
        match = pattern.job_regex.match(cleaned)
        if match:
            return _build_root(pattern, match)
        match = pattern.root_regex.match(cleaned)
        if match:
            return _build_root(pattern, match)
    return cleaned.rstrip("/")


def is_job_url(url: str) -> bool:
    cleaned = _normalize_url(url)
    for pattern in PATTERNS:
        if pattern.job_regex.match(cleaned):
            return True
    return False


def get_canonical_root(ats_name: str, slug: str, **kwargs: str) -> Optional[str]:
    for pattern in PATTERNS:
        if pattern.name != ats_name:
            continue
        parts = {pattern.slug_group: slug}
        parts.update(kwargs)
        try:
            return pattern.root_template.format(**parts).rstrip("/")
        except KeyError:
            return None
    return None
