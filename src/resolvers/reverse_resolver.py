"""Corporate URL to ATS URL resolver."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..extractors.company_name import extract as extract_company_name
from ..extractors.domain import extract_domain
from ..models import CompanyRecord, UnresolvedRecord
from ..patterns.ats_patterns import detect, normalize
from ..patterns.careers_indicators import has_careers_indicator
from ..validators.http_validator import HTTPClient


def _is_valid_validation(status_code: int, is_soft_404: bool, is_sso_redirect: bool) -> bool:
    if status_code <= 0:
        return False
    if status_code >= 400:
        return False
    if is_soft_404 or is_sso_redirect:
        return False
    return True


@dataclass
class ReverseResolver:
    client: HTTPClient
    mode: str = "strict"

    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        corp_validation = await self.client.validate(input_url)
        if not _is_valid_validation(
            corp_validation.status_code,
            corp_validation.is_soft_404,
            corp_validation.is_sso_redirect,
        ):
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason=f"Corporate URL invalid: {corp_validation.status_code}",
            )

        corp_final_url = corp_validation.final_url
        if self.mode == "strict" and not has_careers_indicator(corp_final_url):
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Corporate URL is not a careers page",
            )

        html, corp_final_url, _ = await self.client.fetch_html(corp_final_url)
        soup = BeautifulSoup(html, "html.parser")

        candidates: list[tuple[str, str]] = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            full = urljoin(corp_final_url, href)
            detection = detect(full)
            if detection:
                ats_name, slug = detection
                candidates.append((ats_name, normalize(full)))

        if not candidates:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="No ATS URLs found on corporate page",
            )

        ats_name = None
        ats_url = None
        ats_validation = None
        for cand_name, cand_url in candidates:
            validation = await self.client.validate(cand_url)
            if _is_valid_validation(
                validation.status_code,
                validation.is_soft_404,
                validation.is_sso_redirect,
            ):
                ats_name = cand_name
                ats_url = validation.final_url
                ats_validation = validation
                break

        if not ats_name or not ats_url or not ats_validation:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="No valid ATS URLs found",
            )

        ats_html, _, _ = await self.client.fetch_html(ats_url)
        slug = detect(ats_url)[1] if detect(ats_url) else None
        company_name = extract_company_name(ats_html, slug=slug, mode=self.mode)
        if self.mode == "strict" and not company_name:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=ats_name,
                reason="Company name not found",
            )

        domain = extract_domain(corp_final_url)
        if self.mode == "strict" and not domain:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=ats_name,
                reason="Company domain not found",
            )

        confidence = "verified"
        if self.mode != "strict" and not has_careers_indicator(corp_final_url):
            confidence = "inferred"

        return CompanyRecord(
            company_ats_name=ats_name,
            company_ats_url=ats_url,
            company_name_clean=company_name or "",
            company_domain=domain,
            corporate_url=corp_final_url,
            ats_status=ats_validation.status_code,
            corporate_status=corp_validation.status_code,
            discovery_method="reverse",
            confidence=confidence,
        )
