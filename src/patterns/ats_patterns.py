"""ATS URL detection and normalization."""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse
from pathlib import Path


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


ALLOWED_ATS_NAMES = {
    "LEVER",
    "GREENHOUSE",
    "RECRUITEE",
    "SMARTRECRUITERS",
    "ASHBY",
    "AVATURE",
    "WORKABLE",
    "WORKDAY",
    "META",
    "APPLE",
    "AMAZON",
    "JOBVITE",
    "RIPPLING",
    "EIGHTFOLD_AI",
    "HUNDRED_HIRES",
    "ADP_WORKFORCE_NOW",
    "BAMBOOHR",
    "BETTERTEAM",
    "BREEZY_HR",
    "BULLHORN",
    "CADIENT",
    "CAREERPLUG",
    "CAREERPUCK",
    "CEIPAL",
    "CLEARCOMPANY",
    "COMEET",
    "CSOD",
    "DARWINBOX",
    "DOVER",
    "FRESHTEAM",
    "GEM",
    "GOHIRE",
    "HIBOB",
    "HIREHIVE",
    "HIRINGTHING",
    "HRONE",
    "IBM_KENEXA",
    "ICIMS",
    "IDEALTRAITS",
    "JAZZHR",
    "JOBDIVA",
    "JOIN_DOT_COM",
    "KEKA",
    "LOXO",
    "MANATAL",
    "MOKA",
    "NEOGOV",
    "OORWIN",
    "ORACLE_CLOUD_HCM",
    "ORACLE_TALEO",
    "PAYLOCITY",
    "PEOPLESTRONG",
    "PERSONIO",
    "PHENOM_PEOPLE",
    "PINPOINT",
    "POLYMER",
    "PYJAMAHR",
    "RECOOTY",
    "RECRUIT_CRM",
    "RECRUITERFLOW",
    "SAP_SUCCESSFACTORS",
    "TALOS",
    "TEAMTAILOR",
    "TRAKSTAR",
    "UKG",
    "ZAPPYHIRE",
    "ZOHO_RECRUIT",
}

NAME_OVERRIDES = {
    "100HIRES": "HUNDRED_HIRES",
    "BREEZY_HR": "BREEZY_HR",
    "JOIN_COM": "JOIN_DOT_COM",
    "UKG_ULTIPRO": "UKG",
    "ZOHO_RECRUIT": "ZOHO_RECRUIT",
    "EIGHTFOLD_AI": "EIGHTFOLD_AI",
}

EXTRA_DOMAIN_MARKERS = {
    "AMAZON": {"amazon.jobs"},
    "APPLE": {"jobs.apple.com"},
    "META": {"metacareers.com", "facebookcareers.com"},
    "AVATURE": {"avature.com", "avature.net"},
    "CSOD": {"csod.com", "cornerstoneondemand.com"},
    "CAREERPUCK": {"careerpuck.com"},
    "HUNDRED_HIRES": {"100hires.com"},
    "JOIN_DOT_COM": {"join.com"},
}


def _normalize_ats_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").upper()
    if cleaned in NAME_OVERRIDES:
        return NAME_OVERRIDES[cleaned]
    return cleaned


def _load_external_domain_markers() -> dict[str, set[str]]:
    path_value = os.environ.get("ATS_DEFINITIONS_PATH", "/Users/sucharith/url_miner_v0/ats_definitions.py")
    path = Path(path_value)
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location("ats_definitions", path)
    if not spec or not spec.loader:
        return {}
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return {}
    catalog = getattr(module, "ATS_CATALOG", {})
    mapping: dict[str, set[str]] = {}
    for name, definition in catalog.items():
        normalized = _normalize_ats_name(name)
        if normalized not in ALLOWED_ATS_NAMES:
            continue
        domain_markers = getattr(definition, "domain_markers", []) or []
        if not domain_markers:
            continue
        mapping.setdefault(normalized, set()).update({m.lower() for m in domain_markers})
    return mapping


DOMAIN_MARKERS = _load_external_domain_markers()
for ats_name, markers in EXTRA_DOMAIN_MARKERS.items():
    if ats_name in ALLOWED_ATS_NAMES:
        DOMAIN_MARKERS.setdefault(ats_name, set()).update({m.lower() for m in markers})


def _match_domain_marker(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return None
    for ats_name, markers in DOMAIN_MARKERS.items():
        for marker in markers:
            if netloc.endswith(marker) or marker in netloc:
                return ats_name
    return None


def detect(url: str) -> Optional[tuple[str, str]]:
    cleaned = _normalize_url(url)
    for pattern in PATTERNS:
        for regex in (pattern.job_regex, pattern.root_regex):
            match = regex.match(cleaned)
            if match:
                slug = match.groupdict().get(pattern.slug_group, "")
                return _normalize_ats_name(pattern.name), slug
    fallback = _match_domain_marker(cleaned)
    if fallback:
        return fallback, ""
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
    if _match_domain_marker(cleaned):
        return cleaned.rstrip("/")
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
