"""Configuration settings for URL Discovery Engine."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from typing import Literal, Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Operation mode
    mode: Literal["strict", "lenient"] = "strict"

    # HTTP settings
    http_timeout: int = 30
    max_redirects: int = 5
    user_agent: str = "URLDiscoveryEngine/0.1 (+https://jobboard.app)"

    # Rate limiting (requests per minute)
    default_rate_limit: int = 10
    global_concurrency: int = 50

    # Output paths
    output_dir: str = "./output"
    unresolved_file: str = "unresolved.csv"

    # Optional API keys (for future SERP integration)
    scrape_do_api_token: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Per-domain rate limits (requests per minute)
RATE_LIMITS: dict[str, int] = {
    "default": 10,
    "greenhouse.io": 30,
    "lever.co": 30,
    "myworkdayjobs.com": 20,
    "ashbyhq.com": 20,
    "smartrecruiters.com": 20,
    "workable.com": 20,
    "jobvite.com": 15,
    "icims.com": 15,
    "bamboohr.com": 15,
}


# Domains that indicate SSO redirects (should be treated as failures)
SSO_REDIRECT_DOMAINS: list[str] = [
    "okta.com",
    "auth0.com",
    "login.microsoftonline.com",
    "accounts.google.com",
    "sso.",
    "login.",
    "signin.",
]


# Patterns that indicate a soft-404 (200 status but actually a failure)
SOFT_404_PATTERNS: list[str] = [
    r"page\s*not\s*found",
    r"404",
    r"no\s*jobs?\s*(found|available|posted|open)",
    r"this\s*page\s*(doesn't|does not)\s*exist",
    r"we\s*couldn't\s*find",
    r"position\s*(has\s*been\s*)?(closed|filled)",
    r"no\s*longer\s*accepting",
    r"no\s*open(ings?|\s*positions?)",
]


settings = Settings()
