"""Extract corporate careers URL from ATS HTML."""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ExtractionResult
from urllib.parse import urlparse

from ..patterns.ats_patterns import DOMAIN_MARKERS, detect
from ..patterns.careers_indicators import has_careers_indicator, has_careers_text


COMPANY_SITE_TEXT = [
    "company website",
    "company site",
    "website",
    "visit website",
    "main website",
]

APPLY_COMPANY_TEXT = [
    "apply on company site",
    "apply on company website",
    "apply on company page",
    "apply on company", 
    "apply on website",
]

ATS_SCRIPT_URL_PATTERNS = {
    "LEVER": [
        re.compile(r"\"companyUrl\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
        re.compile(r"\"companyWebsite\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
        re.compile(r"\"company_website\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
    ],
    "GREENHOUSE": [
        re.compile(r"\"companyUrl\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
        re.compile(r"\"company_website\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
    ],
    "WORKABLE": [
        re.compile(r"\"company_website\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
        re.compile(r"\"website\"\s*:\s*\"(?P<url>https?://[^\"]+)\"", re.IGNORECASE),
    ],
}

VENDOR_DOMAIN_BLOCKLIST = {
    "jazzhr.com",
    "lever.co",
    "greenhouse.io",
    "job-boards.greenhouse.io",
    "workable.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "jobvite.com",
    "icims.com",
    "bamboohr.com",
    "applytojob.com",
    "teamtailor.com",
    "teamtailor-app.com",
    "pinpointhq.com",
    "recruitee.com",
    "breezy.hr",
    "personio.com",
    "bullhornstaffing.com",
    "manatal.com",
    "gem.com",
    "comeet.co",
    "successfactors.com",
    "oracle.com",
    "taleo.net",
    "ukg.com",
}


def _iter_json_ld_objects(soup: BeautifulSoup) -> Iterable[dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                for item in data["@graph"]:
                    if isinstance(item, dict):
                        yield item
            else:
                yield data


def _extract_org_urls(obj: dict) -> list[str]:
    types = obj.get("@type")
    if isinstance(types, list):
        type_list = [t.lower() for t in types if isinstance(t, str)]
    elif isinstance(types, str):
        type_list = [types.lower()]
    else:
        type_list = []
    if "organization" not in type_list:
        return []
    urls = []
    if isinstance(obj.get("url"), str):
        urls.append(obj["url"])
    return urls


def _extract_same_as_urls(obj: dict) -> list[str]:
    same_as = obj.get("sameAs")
    if isinstance(same_as, list):
        return [u for u in same_as if isinstance(u, str)]
    if isinstance(same_as, str):
        return [same_as]
    return []


def _filter_http(urls: Iterable[str]) -> list[str]:
    out = []
    for url in urls:
        if not url:
            continue
        cleaned = url.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            out.append(cleaned)
    return out


def _is_vendor_domain(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return False
    for markers in DOMAIN_MARKERS.values():
        for marker in markers:
            if marker and (netloc.endswith(marker) or marker in netloc):
                return True
    for blocked in VENDOR_DOMAIN_BLOCKLIST:
        if netloc.endswith(blocked):
            return True
    return False


def _is_non_ats(url: str) -> bool:
    return detect(url) is None and not _is_vendor_domain(url)


def is_valid_corporate_url(url: str) -> bool:
    """Return True if url looks like a company (non-ATS) domain."""
    return _is_non_ats(url)


def _has_company_site_text(text: str) -> bool:
    if not text:
        return False
    normalized = " ".join(text.lower().split())
    return any(term in normalized for term in COMPANY_SITE_TEXT)


def _has_apply_company_text(text: str) -> bool:
    if not text:
        return False
    normalized = " ".join(text.lower().split())
    return any(term in normalized for term in APPLY_COMPANY_TEXT)


def _extract_ats_specific_urls(html: str, ats_name: Optional[str]) -> list[str]:
    if not html or not ats_name:
        return []
    patterns = ATS_SCRIPT_URL_PATTERNS.get(ats_name, [])
    if not patterns:
        return []
    urls: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(html):
            url = match.group("url")
            if url:
                urls.append(url)
    return urls


def extract(html: str, base_url: str) -> Optional[ExtractionResult]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    inferred_candidates: list[ExtractionResult] = []
    ats_name = None
    detection = detect(base_url)
    if detection:
        ats_name, _ = detection

    # ATS-specific script parsers
    for url in _filter_http(_extract_ats_specific_urls(html, ats_name)):
        if _is_non_ats(url) and has_careers_indicator(url):
            return ExtractionResult(value=url, source="ats-script", confidence="verified")

    # JSON-LD
    for obj in _iter_json_ld_objects(soup):
        for url in _filter_http(_extract_org_urls(obj)):
            if _is_non_ats(url) and has_careers_indicator(url):
                return ExtractionResult(value=url, source="json-ld", confidence="verified")
        for url in _filter_http(_extract_same_as_urls(obj)):
            if _is_non_ats(url) and has_careers_indicator(url):
                inferred_candidates.append(
                    ExtractionResult(value=url, source="json-ld", confidence="inferred")
                )

    # Meta tags
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or "").lower()
        if prop not in {"og:see_also"}:
            continue
        url = meta.get("content")
        if not url:
            continue
        if _is_non_ats(url) and has_careers_indicator(url):
            inferred_candidates.append(
                ExtractionResult(value=url, source="meta", confidence="inferred")
            )

    # Links with careers indicators
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        if _is_non_ats(full) and has_careers_indicator(full):
            return ExtractionResult(value=full, source="link", confidence="verified")

    # Links with careers text
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if has_careers_text(text):
            if _is_non_ats(full) and has_careers_indicator(full):
                return ExtractionResult(value=full, source="link-text", confidence="verified")
            if _is_non_ats(full):
                inferred_candidates.append(
                    ExtractionResult(value=full, source="link-text", confidence="inferred")
                )

    # Apply on company site links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if _has_apply_company_text(text) and _is_non_ats(full):
            return ExtractionResult(value=full, source="apply-link", confidence="verified")

    # Links to company site (homepage candidates)
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if _has_company_site_text(text) and _is_non_ats(full):
            inferred_candidates.append(
                ExtractionResult(value=full, source="company-site", confidence="inferred")
            )

    # Logo/header links
    for link in soup.find_all("a", href=True):
        classes = " ".join(link.get("class", [])).lower()
        if "logo" in classes or "brand" in classes:
            full = urljoin(base_url, link.get("href", ""))
            if _is_non_ats(full):
                inferred_candidates.append(
                    ExtractionResult(value=full, source="logo", confidence="inferred")
                )

    if inferred_candidates:
        return inferred_candidates[0]

    return None


def extract_homepage(html: str, base_url: str) -> Optional[ExtractionResult]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    inferred_candidates: list[ExtractionResult] = []
    ats_name = None
    detection = detect(base_url)
    if detection:
        ats_name, _ = detection

    for url in _filter_http(_extract_ats_specific_urls(html, ats_name)):
        if _is_non_ats(url):
            return ExtractionResult(value=url, source="ats-script", confidence="verified")

    for obj in _iter_json_ld_objects(soup):
        for url in _filter_http(_extract_org_urls(obj)):
            if _is_non_ats(url):
                return ExtractionResult(value=url, source="json-ld", confidence="verified")
        for url in _filter_http(_extract_same_as_urls(obj)):
            if _is_non_ats(url):
                inferred_candidates.append(
                    ExtractionResult(value=url, source="json-ld", confidence="inferred")
                )

    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or "").lower()
        if prop not in {"og:see_also"}:
            continue
        url = meta.get("content")
        if not url:
            continue
        if _is_non_ats(url):
            inferred_candidates.append(
                ExtractionResult(value=url, source="meta", confidence="inferred")
            )

    input_tag = soup.find("input", attrs={"name": "company_website"})
    if input_tag and input_tag.get("value"):
        url = input_tag.get("value")
        if _is_non_ats(url):
            return ExtractionResult(value=url, source="greenhouse-input", confidence="verified")

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if _has_apply_company_text(text) and _is_non_ats(full):
            return ExtractionResult(value=full, source="apply-link", confidence="verified")

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if _has_company_site_text(text) and _is_non_ats(full):
            inferred_candidates.append(
                ExtractionResult(value=full, source="company-site", confidence="inferred")
            )

    for link in soup.find_all("a", href=True):
        classes = " ".join(link.get("class", [])).lower()
        if "logo" in classes or "brand" in classes:
            full = urljoin(base_url, link.get("href", ""))
            if _is_non_ats(full):
                inferred_candidates.append(
                    ExtractionResult(value=full, source="logo", confidence="inferred")
                )

    if inferred_candidates:
        return inferred_candidates[0]

    return None
