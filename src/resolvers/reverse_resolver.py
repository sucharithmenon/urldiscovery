"""Corporate URL to ATS URL resolver with two-hop discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import tldextract
from bs4 import BeautifulSoup

from ..extractors.company_name import extract as extract_company_name
from ..extractors.domain import extract_domain
from ..models import CompanyRecord, UnresolvedRecord
from ..patterns.ats_patterns import detect, normalize
from ..patterns.careers_indicators import (
    has_careers_indicator,
    has_careers_text,
    is_careers_page,
)
from ..validators.http_validator import HTTPClient


COMMON_CAREERS_PATHS = [
    "/careers",
    "/jobs",
    "/about/careers",
    "/company/careers",
    "/en/careers",
    "/work-with-us",
    "/join-us",
    "/join",
    "/opportunities",
]


_TLD_EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=None,
    cache_dir=".tldextract-cache",
)


def _is_valid_validation(status_code: int, is_soft_404: bool, is_sso_redirect: bool) -> bool:
    if status_code <= 0:
        return False
    if status_code >= 400:
        return False
    if is_soft_404 or is_sso_redirect:
        return False
    return True


def _is_corporate_valid(status_code: int, is_sso_redirect: bool) -> bool:
    if status_code <= 0:
        return False
    if status_code >= 400:
        return False
    if is_sso_redirect:
        return False
    return True


def _domain_for(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if not parsed.netloc:
        return ""
    result = _TLD_EXTRACT(parsed.netloc)
    if result.domain and result.suffix:
        return f"{result.domain}.{result.suffix}"
    return ""


def _is_internal(url: str, base_domain: str) -> bool:
    if not url or not base_domain:
        return False
    return _domain_for(url) == base_domain


def _find_ats_link(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        detection = detect(full)
        if detection:
            return full
    return None


def _find_ats_iframe(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for iframe in soup.find_all("iframe", src=True):
        src = iframe.get("src", "").strip()
        if not src:
            continue
        full = urljoin(base_url, src)
        if detect(full):
            return full
    for iframe in soup.find_all("iframe", attrs={"data-src": True}):
        src = iframe.get("data-src", "").strip()
        if not src:
            continue
        full = urljoin(base_url, src)
        if detect(full):
            return full
    return None


def _find_careers_link(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = _domain_for(base_url)

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        if has_careers_indicator(full) and _is_internal(full, base_domain):
            return full

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if has_careers_text(text) and _is_internal(full, base_domain):
            return full

    for container in soup.find_all(["nav", "header", "footer"]):
        for link in container.find_all("a", href=True):
            href = link.get("href", "").strip()
            if not href:
                continue
            full = urljoin(base_url, href)
            text = link.get_text(" ", strip=True)
            if has_careers_text(text) and _is_internal(full, base_domain):
                return full

    return None


def _iter_common_careers_paths(base_url: str) -> Iterable[str]:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    base = f"{parsed.scheme}://{parsed.netloc}"
    return [f"{base}{path}" for path in COMMON_CAREERS_PATHS]


@dataclass
class ReverseResolver:
    client: HTTPClient
    mode: str = "strict"

    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        corp_validation = await self.client.validate(input_url)
        if not _is_corporate_valid(
            corp_validation.status_code,
            corp_validation.is_sso_redirect,
        ):
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason=f"Homepage invalid: {corp_validation.status_code}",
            )

        homepage_url = corp_validation.final_url
        homepage_html, _, _ = await self.client.fetch_html(homepage_url)
        if not homepage_html:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Failed to fetch homepage HTML",
            )

        ats_url = _find_ats_link(homepage_html, homepage_url)
        if not ats_url:
            ats_url = _find_ats_iframe(homepage_html, homepage_url)
        if ats_url:
            return await self._build_record(ats_url, homepage_url, homepage_html)

        careers_url = _find_careers_link(homepage_html, homepage_url)
        if not careers_url:
            for candidate in _iter_common_careers_paths(homepage_url):
                validation = await self.client.validate(candidate)
                if _is_corporate_valid(
                    validation.status_code,
                    validation.is_sso_redirect,
                ):
                    careers_url = validation.final_url
                    break

        if not careers_url:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="No careers page found on homepage or common paths",
            )

        careers_validation = await self.client.validate(careers_url)
        if not _is_corporate_valid(
            careers_validation.status_code,
            careers_validation.is_sso_redirect,
        ):
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason=f"Careers page invalid: {careers_validation.status_code}",
            )

        careers_html, careers_final_url, _ = await self.client.fetch_html(
            careers_validation.final_url
        )
        if not careers_html:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Failed to fetch careers page HTML",
            )

        ats_url = _find_ats_link(careers_html, careers_final_url)
        if not ats_url:
            ats_url = _find_ats_iframe(careers_html, careers_final_url)
        if not ats_url:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="No ATS URLs found on careers page (links/iframes checked)",
            )

        return await self._build_record(ats_url, careers_final_url, careers_html)

    async def _build_record(
        self,
        ats_url: str,
        corporate_url: str,
        html: str,
    ) -> CompanyRecord | UnresolvedRecord:
        detection = detect(ats_url)
        if not detection:
            return UnresolvedRecord(
                input_url=corporate_url,
                ats_name=None,
                reason="ATS detection failed on discovered URL",
            )

        ats_name, slug = detection
        normalized = normalize(ats_url)
        ats_validation = await self.client.validate(normalized)
        if not _is_valid_validation(
            ats_validation.status_code,
            ats_validation.is_soft_404,
            ats_validation.is_sso_redirect,
        ):
            return UnresolvedRecord(
                input_url=corporate_url,
                ats_name=ats_name,
                reason=f"ATS URL invalid: {ats_validation.status_code}",
            )

        company_name = extract_company_name(html, slug=slug, mode="strict")
        domain = extract_domain(corporate_url) if corporate_url else None

        corporate_url_out = None
        if corporate_url and (has_careers_indicator(corporate_url) or is_careers_page(html)):
            corporate_url_out = corporate_url

        confidence = "verified"
        if self.mode != "strict":
            if corporate_url_out is None:
                confidence = "inferred"

        return CompanyRecord(
            company_ats_name=ats_name,
            company_ats_url=ats_validation.final_url,
            company_name_clean=company_name or "",
            company_domain=domain,
            corporate_url=corporate_url_out,
            ats_status=ats_validation.status_code,
            corporate_status=200,
            discovery_method="reverse",
            confidence=confidence,
        )
