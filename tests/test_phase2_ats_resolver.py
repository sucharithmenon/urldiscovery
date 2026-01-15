import asyncio

from src.models import ValidationResult
from src.resolvers.phase2_ats_resolver import Phase2ATSResolver


class FakeHTTPClient:
    def __init__(self, responses):
        self.responses = responses

    async def fetch_and_validate(self, url):
        response = self.responses[url]
        return (
            ValidationResult(
                url=url,
                final_url=response["final_url"],
                status_code=response["status"],
                redirect_chain=response.get("redirects", []),
                is_soft_404=False,
                is_sso_redirect=False,
                error=None,
            ),
            response.get("html", ""),
        )


def run_async(coro):
    return asyncio.run(coro)


def test_phase2_domain_match_only():
    url = "https://boards.greenhouse.io/acme"
    client = FakeHTTPClient(
        {
            url: {
                "status": 200,
                "final_url": url,
                "html": "<html></html>",
            }
        }
    )
    resolver = Phase2ATSResolver(client=client)
    result = run_async(resolver.resolve_one("Acme", url))
    assert result.ats_provider == "greenhouse"
    assert result.confidence == "medium"
    assert "final_hostname" in result.detection_signals


def test_phase2_domain_plus_html():
    url = "https://jobs.lever.co/acme"
    client = FakeHTTPClient(
        {
            url: {
                "status": 200,
                "final_url": url,
                "html": "<html>Lever</html>",
            }
        }
    )
    resolver = Phase2ATSResolver(client=client)
    result = run_async(resolver.resolve_one("Acme", url))
    assert result.ats_provider == "lever"
    assert result.confidence == "high"
    assert "final_hostname" in result.detection_signals
    assert "html_marker" in result.detection_signals


def test_phase2_weak_signal_none():
    url = "https://example.com/careers"
    client = FakeHTTPClient(
        {
            url: {
                "status": 200,
                "final_url": url,
                "html": "<html>lever</html>",
            }
        }
    )
    resolver = Phase2ATSResolver(client=client)
    result = run_async(resolver.resolve_one("Acme", url))
    assert result.ats_provider is None
    assert result.ats_base_url is None


def test_phase2_base_url_normalization():
    url = "https://job-boards.greenhouse.io/acme/jobs/123"
    client = FakeHTTPClient(
        {
            url: {
                "status": 200,
                "final_url": url,
                "html": "<html></html>",
            }
        }
    )
    resolver = Phase2ATSResolver(client=client)
    result = run_async(resolver.resolve_one("Acme", url))
    assert result.ats_base_url == "https://job-boards.greenhouse.io/acme"


def test_phase2_workday_base_url():
    url = "https://wd5.myworkdayjobs.com/en-US/CompanyCareers/job/123"
    client = FakeHTTPClient(
        {
            url: {
                "status": 200,
                "final_url": url,
                "html": "<html>workday</html>",
            }
        }
    )
    resolver = Phase2ATSResolver(client=client)
    result = run_async(resolver.resolve_one("Acme", url))
    assert result.ats_provider == "workday"
    assert result.ats_base_url == "https://wd5.myworkdayjobs.com/en-US"
