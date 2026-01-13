"""ATS URL to corporate URL resolver."""

from __future__ import annotations

from dataclasses import dataclass

from ..extractors.company_name import extract as extract_company_name
from ..extractors.corporate_url import extract as extract_corporate_url
from ..extractors.domain import extract_domain
from ..models import CompanyRecord, UnresolvedRecord
from ..patterns.ats_patterns import detect, normalize
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
class DirectResolver:
    client: HTTPClient
    mode: str = "strict"

    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        detection = detect(input_url)
        if not detection:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Not a recognized ATS URL",
            )

        ats_name, slug = detection
        root_url = normalize(input_url)

        ats_validation = await self.client.validate(root_url)
        if not _is_valid_validation(
            ats_validation.status_code,
            ats_validation.is_soft_404,
            ats_validation.is_sso_redirect,
        ):
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=ats_name,
                reason=f"ATS URL invalid: {ats_validation.status_code}",
            )

        html, ats_final_url, _ = await self.client.fetch_html(ats_validation.final_url)

        corp_result = extract_corporate_url(html, ats_final_url)
        corp_url = None
        if corp_result and corp_result.confidence == "verified":
            corp_url = corp_result.value
        corp_status = None
        corp_final_url = None
        corp_ok = False
        if corp_url:
            corp_validation = await self.client.validate(corp_url)
            corp_status = corp_validation.status_code
            corp_final_url = corp_validation.final_url
            corp_ok = _is_valid_validation(
                corp_validation.status_code,
                corp_validation.is_soft_404,
                corp_validation.is_sso_redirect,
            )
            if not corp_ok:
                corp_final_url = None
                corp_url = None
                corp_status = None

        company_name = extract_company_name(html, slug=slug, mode="strict")
        domain = extract_domain(corp_final_url or corp_url) if corp_url else None

        confidence = "verified"
        if self.mode != "strict":
            if not corp_ok or not corp_result or corp_result.confidence != "verified":
                confidence = "inferred"

        return CompanyRecord(
            company_ats_name=ats_name,
            company_ats_url=ats_validation.final_url,
            company_name_clean=company_name or "",
            company_domain=domain,
            corporate_url=corp_final_url or corp_url,
            ats_status=ats_validation.status_code,
            corporate_status=corp_status,
            discovery_method="direct",
            confidence=confidence,
        )
