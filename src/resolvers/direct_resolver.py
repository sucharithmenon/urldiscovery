"""ATS URL to corporate URL resolver."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin

from ..extractors.company_name import extract as extract_company_name
from ..extractors.corporate_url import extract as extract_corporate_url
from ..extractors.domain import extract_domain, extract_homepage
from ..models import CompanyRecord, UnresolvedRecord
from ..patterns.ats_patterns import detect, normalize
from ..patterns.ats_fingerprints import detect_fingerprints
from ..validators.ats_root_validator import validate_ats_root_content
from ..patterns.careers_indicators import (
    COMMON_CAREERS_PATHS,
    has_careers_indicator,
    is_careers_page,
)
from ..validators.http_validator import HTTPClient
from ..utils.logging import log_validation_signals, log_http_validation


_URL_RE = re.compile(r"https?://[^\\s'\\\"<>]+", re.IGNORECASE)


def _is_valid_validation(status_code: int, is_soft_404: bool, is_sso_redirect: bool) -> bool:
    if status_code <= 0:
        return False
    if status_code >= 400:
        return False
    if is_soft_404 or is_sso_redirect:
        return False
    return True


def _extract_ats_candidates(html: str, base_url: str) -> list[tuple[str, str]]:
    if not html:
        return []
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_candidate(raw_url: str) -> None:
        if not raw_url:
            return
        full = urljoin(base_url, raw_url)
        detection = detect(full)
        if not detection:
            return
        ats_name, _ = detection
        root = normalize(full)
        key = f"{ats_name}|{root}"
        if key in seen:
            return
        seen.add(key)
        candidates.append((ats_name, root))

    for match in _URL_RE.findall(html):
        add_candidate(match)

    return candidates


def _is_corporate_valid(status_code: int, is_sso_redirect: bool) -> bool:
    if status_code <= 0:
        return False
    if status_code >= 400:
        return False
    if is_sso_redirect:
        return False
    return True


@dataclass
class DirectResolver:
    client: HTTPClient
    mode: str = "strict"
    logger = None  # Optional logger for debugging

    def __init__(self, client: HTTPClient, mode: str = "strict", logger=None) -> None:
        self.client = client
        self.mode = mode
        self.logger = logger

    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        detection = detect(input_url)
        
        if not detection:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Not a recognized ATS URL",
                error_category="detection_error",
                validation_signals=["no_ats_pattern"],
            )

        ats_name, slug = detection
        root_url = normalize(input_url)

        ats_validation, ats_html = await self.client.fetch_and_validate(root_url)
        ats_inferred = False
        if not _is_valid_validation(
            ats_validation.status_code,
            ats_validation.is_soft_404,
            ats_validation.is_sso_redirect,
        ):
            if (
                self.mode != "strict"
                and ats_validation.status_code > 0
                and ats_validation.status_code < 400
                and ats_validation.is_soft_404
                and not ats_validation.is_sso_redirect
            ):
                ats_inferred = True
            else:
                fingerprints = detect_fingerprints(ats_html)
                candidates = _extract_ats_candidates(ats_html, ats_validation.final_url)
                if fingerprints:
                    candidates = [item for item in candidates if item[0] in fingerprints]
                recovered = False
                for candidate_ats_name, candidate_root in candidates:
                    candidate_validation, candidate_html = await self.client.fetch_and_validate(
                        candidate_root
                    )
                    if _is_valid_validation(
                        candidate_validation.status_code,
                        candidate_validation.is_soft_404,
                        candidate_validation.is_sso_redirect,
                    ):
                        detection = detect(candidate_root)
                        ats_name = candidate_ats_name
                        if detection:
                            _, slug = detection
                        root_url = candidate_root
                        ats_validation = candidate_validation
                        ats_html = candidate_html
                        recovered = True
                        break
                if not recovered:
                    error_category = "http_error" if ats_validation.status_code >= 400 else "validation_error"
                    if ats_validation.status_code == 404:
                        error_category = "not_found"
                    elif ats_validation.status_code >= 500:
                        error_category = "server_error"
                    
                    record = UnresolvedRecord(
                        input_url=input_url,
                        ats_name=ats_name,
                        reason=f"ATS URL invalid: {ats_validation.status_code}",
                        error_category=error_category,
                        http_status=ats_validation.status_code,
                        final_url=ats_validation.final_url,
                        validation_signals=[f"http_{ats_validation.status_code}"],
                    )
        if self.logger:
            log_http_validation(
                input_url, 
                ats_validation.status_code, 
                ats_validation.final_url,
                ats_validation.is_soft_404,
                ats_validation.is_sso_redirect,
                self.logger
            )
        return record

        ats_final_url = ats_validation.final_url
        if slug:
            validation_result = validate_ats_root_content(
                ats_final_url,
                ats_name,
                slug,
                ats_html,
            )
            if validation_result.status == "invalid":
                record = UnresolvedRecord(
                    input_url=input_url,
                    ats_name=ats_name,
                    reason="ATS root validation failed",
                    error_category="validation_error",
                    http_status=ats_validation.status_code,
                    final_url=ats_validation.final_url,
                    validation_signals=validation_result.signals,
                )
                if self.logger:
                    log_validation_signals(validation_result.signals, input_url, self.logger)
                return record

        corp_result = extract_corporate_url(ats_html, ats_final_url)
        corp_url = None
        corp_inferred = False
        if corp_result:
            if corp_result.confidence == "verified":
                corp_url = corp_result.value
            elif self.mode != "strict":
                corp_url = corp_result.value
                corp_inferred = True
        if corp_url and not has_careers_indicator(corp_url):
            if self.mode == "strict":
                corp_url = None
            else:
                corp_url = None
                corp_inferred = True

        if not corp_url and not detect(ats_final_url):
            if has_careers_indicator(ats_final_url) or is_careers_page(ats_html):
                corp_url = ats_final_url
                if not has_careers_indicator(ats_final_url):
                    corp_inferred = True

        corp_status = None
        corp_final_url = None
        corp_ok = False
        if corp_url:
            corp_validation = await self.client.validate(corp_url)
            corp_status = corp_validation.status_code
            corp_final_url = corp_validation.final_url
            corp_ok = _is_corporate_valid(
                corp_validation.status_code,
                corp_validation.is_sso_redirect,
            )
            if not corp_ok:
                corp_final_url = None
                corp_url = None
                corp_status = None

        if not corp_url and self.mode != "strict":
            home_candidates = []
            if corp_result and corp_result.value and not detect(corp_result.value):
                home_candidates.append(corp_result.value)
            if ats_final_url and not detect(ats_final_url):
                home_candidates.append(ats_final_url)
            for candidate in home_candidates:
                homepage = extract_homepage(candidate)
                if not homepage:
                    continue
                base = homepage.rstrip("/")
                for path in COMMON_CAREERS_PATHS:
                    careers_candidate = f"{base}{path}"
                    validation = await self.client.validate(careers_candidate)
                    if _is_corporate_valid(
                        validation.status_code,
                        validation.is_sso_redirect,
                    ):
                        corp_url = validation.final_url
                        corp_final_url = validation.final_url
                        corp_status = validation.status_code
                        corp_ok = True
                        corp_inferred = True
                        break
                if corp_url:
                    break

        company_name = extract_company_name(ats_html, slug=slug, mode=self.mode)
        domain = extract_domain(corp_final_url or corp_url) if corp_url else None

        confidence = "verified"
        if not company_name or not corp_url or not corp_ok or corp_inferred or ats_inferred:
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
