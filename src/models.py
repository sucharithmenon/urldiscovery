"""Data models for URL Discovery Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class CompanyRecord(BaseModel):
    """A fully resolved company record."""

    company_ats_name: str = Field(
        description="ATS platform identifier (GREENHOUSE, LEVER, etc.)"
    )
    company_ats_url: str = Field(
        description="Canonical ATS job board root URL"
    )
    company_name_clean: str = Field(
        description="Human-readable company name"
    )
    company_domain: Optional[str] = Field(
        default=None,
        description="Root domain without protocol/www (e.g., 'algolia.com')"
    )
    corporate_url: Optional[str] = Field(
        default=None,
        description="Company careers page URL"
    )
    ats_status: int = Field(
        description="HTTP status code of ATS URL"
    )
    corporate_status: Optional[int] = Field(
        default=None,
        description="HTTP status code of corporate URL"
    )
    discovery_method: Literal["direct", "breadcrumb", "reverse"] = Field(
        description="How this record was discovered"
    )
    confidence: Literal["verified", "inferred"] = Field(
        description="Whether all fields are verified or some are inferred"
    )
    verified_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of verification"
    )

    def to_csv_row(self) -> dict:
        """Convert to CSV row dict."""
        return {
            "company_ats_name": self.company_ats_name,
            "company_ats_url": self.company_ats_url,
            "company_name_clean": self.company_name_clean,
            "company_domain": self.company_domain or "",
            "corporate_url": self.corporate_url or "",
        }


class UnresolvedRecord(BaseModel):
    """A record that could not be fully resolved."""

    input_url: str = Field(
        description="The original input URL"
    )
    ats_name: Optional[str] = Field(
        default=None,
        description="Detected ATS platform (if any)"
    )
    reason: str = Field(
        description="Why this record could not be resolved"
    )
    error_category: Optional[str] = Field(
        default=None,
        description="Category of error (http_error, validation_error, extraction_error, etc.)"
    )
    validation_signals: Optional[list[str]] = Field(
        default=None,
        description="List of validation signals for debugging"
    )
    http_status: Optional[int] = Field(
        default=None,
        description="HTTP status code received"
    )
    final_url: Optional[str] = Field(
        default=None,
        description="Final URL after redirects"
    )
    attempted_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When resolution was attempted"
    )

    def to_csv_row(self) -> dict:
        """Convert to CSV row dict."""
        return {
            "input_url": self.input_url,
            "ats_name": self.ats_name or "",
            "reason": self.reason,
            "error_category": self.error_category or "",
            "validation_signals": ";".join(self.validation_signals or []) if self.validation_signals else "",
            "http_status": str(self.http_status or ""),
            "final_url": self.final_url or "",
            "attempted_at": self.attempted_at.isoformat(),
        }


class ValidationResult(BaseModel):
    """Result of HTTP validation."""

    url: str = Field(description="Original URL")
    final_url: str = Field(description="Final URL after redirects")
    status_code: int = Field(description="HTTP status code")
    redirect_chain: list[str] = Field(
        default_factory=list,
        description="List of URLs in redirect chain"
    )
    is_soft_404: bool = Field(
        default=False,
        description="Whether page is a soft-404"
    )
    is_sso_redirect: bool = Field(
        default=False,
        description="Whether redirected to SSO/login"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if request failed"
    )


class ExtractionResult(BaseModel):
    """Result of extracting a value from HTML."""

    value: str = Field(description="Extracted value")
    source: str = Field(
        description="Where value was extracted from (json-ld, meta, link, etc.)"
    )
    confidence: Literal["verified", "inferred"] = Field(
        default="verified",
        description="Confidence level"
    )


# CSV field order (for consistent output)
CSV_FIELDS = [
    "company_ats_name",
    "company_ats_url",
    "company_name_clean",
    "company_domain",
    "corporate_url",
]

UNRESOLVED_CSV_FIELDS = [
    "input_url",
    "ats_name",
    "reason",
    "error_category",
    "validation_signals",
    "http_status",
    "final_url",
    "attempted_at",
]
