"""Breadcrumb resolver: job URL -> root -> direct resolution."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import CompanyRecord, UnresolvedRecord
from ..patterns.ats_patterns import detect, normalize
from ..validators.http_validator import HTTPClient
from .direct_resolver import DirectResolver


class BreadcrumbResolver:
    client: HTTPClient
    mode: str = "strict"
    logger = None  # Optional logger for debugging
    seen_roots: set[str] = None

    def __init__(self, client: HTTPClient, mode: str = "strict", logger=None) -> None:
        self.client = client
        self.mode = mode
        self.logger = logger
        self.seen_roots = set()

    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        if logger:
            self.logger = logger
        detection = detect(input_url)
        if not detection:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=None,
                reason="Not a recognized ATS URL",
            )

        root_url = normalize(input_url)
        if root_url in self.seen_roots:
            return UnresolvedRecord(
                input_url=input_url,
                ats_name=detection[0],
                reason="Duplicate root URL",
            )
        self.seen_roots.add(root_url)

        direct = DirectResolver(client=self.client, mode=self.mode)
        result = await direct.resolve(root_url)
        if isinstance(result, CompanyRecord):
            return result.model_copy(update={"discovery_method": "breadcrumb"})
        return result
