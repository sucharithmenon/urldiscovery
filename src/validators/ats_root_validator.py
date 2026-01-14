"""Deterministic ATS root jobs URL validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..extractors.company_name import extract as extract_company_name


ATSStatus = Literal["valid", "valid_empty", "valid_limited", "invalid"]


@dataclass(frozen=True)
class ATSRootValidationResult:
    status: ATSStatus
    ats: str
    job_count: int
    empty_state: bool
    signals: list[str]


ATS_HOSTS = {
    "GREENHOUSE": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
    "LEVER": {"jobs.lever.co"},
    "ASHBY": {"jobs.ashbyhq.com"},
    "WORKABLE": {"apply.workable.com"},
    "SMARTRECRUITERS": {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"},
    "WORKDAY": {"myworkdayjobs.com"},
    "TEAMTAILOR": {"jobs.teamtailor.com"},
    "PINPOINT": {"jobs.pinpoint.com"},
    "RECRUITEE": {"careers.recruitee.com"},
    "HIRINGTHING": {"hiringthing.com"},
    "JAZZHR": {"applytojob.com"},
    "BREEZY_HR": {"breezy.hr"},
}

JOB_LINK_PATTERNS = {
    "GREENHOUSE": re.compile(r"/jobs/[^\"'\\s>]+", re.IGNORECASE),
    "LEVER": re.compile(r"jobs\\.lever\\.co/[^/]+/[^\"'\\s>]+", re.IGNORECASE),
    "ASHBY": re.compile(r"/role/[^\"'\\s>]+", re.IGNORECASE),
    "WORKABLE": re.compile(r"/j/[A-Za-z0-9]+", re.IGNORECASE),
    "WORKDAY": re.compile(r"/job[s]?/[^\"'\\s>]+", re.IGNORECASE),
    "SMARTRECRUITERS": re.compile(r"/job[s]?/[^\"'\\s>]+", re.IGNORECASE),
    "TEAMTAILOR": re.compile(r"/jobs/[^\"'\\s>]+", re.IGNORECASE),
    "PINPOINT": re.compile(r"/jobs/[^\"'\\s>]+", re.IGNORECASE),
    "RECRUITEE": re.compile(r"/o/[^\"'\\s>]+", re.IGNORECASE),
    "HIRINGTHING": re.compile(r"/jobs/[^\"'\\s>]+", re.IGNORECASE),
    "JAZZHR": re.compile(r"/apply/[^\"'\\s>]+", re.IGNORECASE),
    "BREEZY_HR": re.compile(r"/p/[^\"'\\s>]+", re.IGNORECASE),
}

EMPTY_STATE_RE = re.compile(
    r"(no\s+open\s+positions|no\s+jobs\s+available|we\s*'re\s+not\s+hiring\s+right\s+now|"
    r"no\s+jobs\s+found|no\s+current\s+openings?)",
    re.IGNORECASE,
)

MARKETING_LOGIN_RE = re.compile(
    r"(login|signin|sso|auth|account|candidate\\/(login|signin)|my-profile\\/sign-in)",
    re.IGNORECASE,
)


def _ats_host_matches(host: str, expected_ats: str) -> bool:
    if not host or not expected_ats:
        return False
    host = host.lower()
    expected = expected_ats.upper()
    if expected == "WORKDAY":
        return "myworkdayjobs.com" in host
    for allowed in ATS_HOSTS.get(expected, set()):
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def _company_slug_in_path(path: str, slug: str) -> bool:
    if not path or not slug:
        return False
    return slug.lower().strip("/") in path.lower()


def _company_slug_in_host(host: str, slug: str) -> bool:
    if not host or not slug:
        return False
    host = host.lower()
    slug = slug.lower().strip(".")
    return host.startswith(f"{slug}.")


def _company_slug_matches(expected_ats: str, parsed: urlparse, slug: str) -> bool:
    if not slug:
        return False
    ats = expected_ats.upper()
    host = parsed.netloc or ""
    if ats in {"JAZZHR", "HIRINGTHING", "BREEZY_HR"}:
        return _company_slug_in_host(host, slug)
    return _company_slug_in_path(parsed.path or "", slug)


def _is_marketing_or_login(final_url: str) -> bool:
    if not final_url:
        return True
    return bool(MARKETING_LOGIN_RE.search(final_url))


def _extract_job_links(html: str, base_url: str, expected_ats: str) -> list[str]:
    if not html:
        return []
    pattern = JOB_LINK_PATTERNS.get(expected_ats.upper())
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    # Extract links from anchor tags
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not href:
            continue
        full = urljoin(base_url, href)
        if pattern and pattern.search(full):
            links.add(full)

    # Also search for job links in raw HTML (for dynamic content)
    if pattern:
        for match in pattern.findall(html):
            full = urljoin(base_url, match)
            links.add(full)
    
    # Additional fallback: look for common job link patterns if primary pattern fails
    if not links and expected_ats.upper() == "GREENHOUSE":
        # Greenhouse sometimes uses different patterns
        gh_patterns = [
            re.compile(r"/jobs/\d+", re.IGNORECASE),
            re.compile(r'"id":\d+', re.IGNORECASE),  # Job IDs in JSON
        ]
        for fallback_pattern in gh_patterns:
            for match in fallback_pattern.findall(html):
                if match.isdigit():
                    full = urljoin(base_url, f"/jobs/{match}")
                    links.add(full)

    return list(links)


def _extract_json_ld_jobs(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    count = 0
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(tag.string or "")
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict):
                if item.get("@type") == "JobPosting":
                    count += 1
                if "@graph" in item and isinstance(item["@graph"], list):
                    for graph_item in item["@graph"]:
                        if isinstance(graph_item, dict) and graph_item.get("@type") == "JobPosting":
                            count += 1
    return count


def _extract_job_count_from_text(html: str) -> int:
    """Extract job count from text patterns like '36 jobs'."""
    if not html:
        return 0
    
    # Look for patterns like "36 jobs", "15 openings", etc.
    job_count_patterns = [
        re.compile(r"(\d+)\s+jobs?", re.IGNORECASE),
        re.compile(r"(\d+)\s+openings?", re.IGNORECASE),
        re.compile(r"(\d+)\s+positions?", re.IGNORECASE),
        re.compile(r"job[s]?.*?(\d+)", re.IGNORECASE),
        re.compile(r"(\d+).*?job[s]?", re.IGNORECASE),
    ]
    
    for pattern in job_count_patterns:
        match = pattern.search(html)
        if match:
            try:
                count = int(match.group(1))
                if count > 0:
                    return count
            except ValueError:
                continue
    
    return 0


def _company_scope_confirmed(html: str, slug: str) -> bool:
    if not html:
        return False
    
    # More flexible slug matching
    if slug:
        slug_lower = slug.lower()
        html_lower = html.lower()
        
        # Direct slug match
        if slug_lower in html_lower:
            return True
        
        # Partial slug matching (handle hyphens, underscores, etc.)
        slug_variants = [
            slug_lower.replace("-", "").replace("_", ""),
            slug_lower.replace("-", "_"),
            slug_lower.replace("_", "-"),
        ]
        for variant in slug_variants:
            if variant in html_lower:
                return True
    
    # Try company name extraction with both strict and lenient modes
    company_name = extract_company_name(html, slug=slug, mode="strict")
    if not company_name:
        company_name = extract_company_name(html, slug=slug, mode="lenient")
    
    if company_name:
        return True
    
    # Additional fallback: check for company identification in page title or meta tags
    soup = BeautifulSoup(html, "html.parser")
    
    # Check title tag
    title = soup.find("title")
    if title and slug and slug.lower() in title.get_text().lower():
        return True
    
    # Check meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and slug and slug.lower() in meta_desc.get("content", "").lower():
        return True
    
    # Check for common ATS branding elements
    ats_branding = soup.find_all(text=re.compile(r"jobs\s+at\s+\w+", re.IGNORECASE))
    if ats_branding and slug:
        for branding in ats_branding:
            if slug.lower() in branding.lower():
                return True
    
    return False


def validate_ats_root_content(
    final_url: str,
    expected_ats: str,
    company_slug: str,
    html: str,
) -> ATSRootValidationResult:
    signals: list[str] = []
    result = ATSRootValidationResult(
        status="invalid",
        ats=expected_ats,
        job_count=0,
        empty_state=False,
        signals=signals,
    )
    if not final_url:
        return result

    parsed = urlparse(final_url)
    host = parsed.netloc or ""
    if not _ats_host_matches(host, expected_ats):
        signals.append("ats_host_mismatch")
        return result
    signals.append("ats_host_match")

    if company_slug and not _company_slug_matches(expected_ats, parsed, company_slug):
        signals.append("company_slug_mismatch")
        return result
    if company_slug:
        signals.append("company_slug_match")

    if _is_marketing_or_login(final_url):
        signals.append("marketing_or_login_page")
        return result

    if not html:
        signals.append("empty_html")
        return result

    if not _company_scope_confirmed(html, company_slug):
        signals.append("company_scope_missing")
        return result
    signals.append("company_scope_confirmed")

    if EMPTY_STATE_RE.search(html):
        signals.append("explicit_empty_state")
        return ATSRootValidationResult(
            status="valid_empty",
            ats=expected_ats,
            job_count=0,
            empty_state=True,
            signals=signals,
        )

    job_links = _extract_job_links(html, final_url, expected_ats)
    job_count = len(set(job_links))
    
    # Check for job structure with lower threshold
    if job_count >= 2:
        signals.append("job_structure_detected")
        return ATSRootValidationResult(
            status="valid",
            ats=expected_ats,
            job_count=job_count,
            empty_state=False,
            signals=signals,
        )
    
    # Check for limited job structure (1 job found)
    if job_count >= 1:
        signals.append("limited_job_structure_detected")
        return ATSRootValidationResult(
            status="valid_limited",
            ats=expected_ats,
            job_count=job_count,
            empty_state=False,
            signals=signals,
        )

    json_job_count = _extract_json_ld_jobs(html)
    if json_job_count >= 2:
        signals.append("job_structure_detected")
        return ATSRootValidationResult(
            status="valid",
            ats=expected_ats,
            job_count=json_job_count,
            empty_state=False,
            signals=signals,
        )
    
    # Check for limited JSON job structure (1 job found)
    if json_job_count >= 1:
        signals.append("limited_job_structure_detected")
        return ATSRootValidationResult(
            status="valid_limited",
            ats=expected_ats,
            job_count=json_job_count,
            empty_state=False,
            signals=signals,
        )

    # Additional fallback: check for job count indicators in text
    job_count_text = _extract_job_count_from_text(html)
    if job_count_text > 0:
        signals.append("job_count_text_detected")
        return ATSRootValidationResult(
            status="valid_limited",
            ats=expected_ats,
            job_count=job_count_text,
            empty_state=False,
            signals=signals,
        )

    signals.append("job_structure_missing")
    return result
