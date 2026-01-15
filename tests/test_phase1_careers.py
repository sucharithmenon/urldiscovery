import asyncio

from src.resolvers.phase1_careers_resolver import Phase1CareersResolver, Phase1Result


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    async def fetch(self, url):
        if url not in self.responses:
            return 404, url, "", 0
        return self.responses[url]

    async def close(self):
        return None


class AllowAllRobots:
    async def allowed(self, url):
        return True


def run_async(coro):
    return asyncio.run(coro)


def test_phase1_internal_careers_url():
    responses = {
        "https://example.com": (200, "https://example.com", "<a href='/careers'>Careers</a>", 0),
        "https://example.com/careers": (
            200,
            "https://example.com/careers",
            "We are hiring. Open positions and jobs.",
            0,
        ),
    }
    resolver = Phase1CareersResolver(client=FakeClient(responses), robots=AllowAllRobots())
    result = run_async(
        resolver.resolve_one(
            company_name="Example",
            primary_domain="example.com",
            website_url="https://example.com",
            linkedin_url="",
        )
    )
    assert isinstance(result, Phase1Result)
    assert result.careers_url == "https://example.com/careers"
    assert result.source == "company_site"
    assert result.confidence == "high"


def test_phase1_linked_ats_url():
    responses = {
        "https://example.com": (
            200,
            "https://example.com",
            "<a href='https://jobs.lever.co/example'>Jobs</a>",
            0,
        ),
        "https://jobs.lever.co/example": (
            200,
            "https://jobs.lever.co/example",
            "Open positions and job openings.",
            0,
        ),
    }
    resolver = Phase1CareersResolver(client=FakeClient(responses), robots=AllowAllRobots())
    result = run_async(
        resolver.resolve_one(
            company_name="Example",
            primary_domain="example.com",
            website_url="https://example.com",
            linkedin_url="",
        )
    )
    assert result.careers_url == "https://jobs.lever.co/example"
    assert result.source == "linked_ats"
    assert result.confidence == "medium"


def test_phase1_social_redirect():
    responses = {
        "https://linkedin.com/company/example": (
            200,
            "https://linkedin.com/company/example",
            "<a href='https://www.example.com'>Website</a>",
            0,
        ),
        "https://example.com": (404, "https://example.com", "", 0),
        "https://www.example.com": (200, "https://www.example.com", "<a href='/jobs'>Jobs</a>", 0),
        "https://www.example.com/jobs": (
            200,
            "https://www.example.com/jobs",
            "Job openings available.",
            0,
        ),
    }
    resolver = Phase1CareersResolver(client=FakeClient(responses), robots=AllowAllRobots())
    result = run_async(
        resolver.resolve_one(
            company_name="Example",
            primary_domain="example.com",
            website_url="",
            linkedin_url="https://linkedin.com/company/example",
        )
    )
    assert result.careers_url == "https://www.example.com/jobs"
    assert result.source == "social_redirect"
    assert result.confidence == "low"
