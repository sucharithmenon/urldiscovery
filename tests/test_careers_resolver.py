import asyncio

from src.models import ValidationResult
from src.resolvers.careers_resolver import CareersResolver


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


def test_resolver_resolves_careers_link():
    ats_url = "https://job-boards.greenhouse.io/acme"
    html = """
    <html>
      <head><title>Careers at Acme</title></head>
      <body>
        <header><a href="https://www.acme.com">Company</a></header>
        <a href="https://www.acme.com/careers">Careers</a>
      </body>
    </html>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            }
        }
    )
    resolver = CareersResolver(client=client, max_fetches=3)
    result, debug = run_async(resolver.resolve_one(ats_url))
    assert result.company_domain == "acme.com"
    assert result.corporate_url == "https://www.acme.com/careers"
    assert debug.status == "RESOLVED"
    assert debug.evidence["careers_source"] == "ATS_ROOT_LINK"


def test_resolver_master_domain_conflict():
    ats_url = "https://jobs.lever.co/acme"
    html = """
    <html>
      <body>
        <footer><a href="https://www.other.com">Company</a></footer>
      </body>
    </html>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://acme.com": {
                "status": 200,
                "final_url": "https://acme.com",
                "html": "<html></html>",
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=3)
    result, debug = run_async(
        resolver.resolve_one(ats_url, master_company_domain="acme.com")
    )
    assert result.company_domain == "acme.com"
    assert result.corporate_url == ""
    assert debug.status == "CONFLICT"
    assert debug.evidence["domain_source"] == "MASTER_DB"


def test_resolver_jsonld_homepage_partial():
    ats_url = "https://jobs.lever.co/example"
    html = """
    <html>
      <script type="application/ld+json">
        {"@type": "Organization", "url": "https://example.com"}
      </script>
    </html>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://www.example.com": {
                "status": 200,
                "final_url": "https://www.example.com",
                "html": "<html></html>",
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(resolver.resolve_one(ats_url))
    assert result.company_domain == "example.com"
    assert result.corporate_url == ""
    assert debug.status == "PARTIAL"
    assert debug.evidence["domain_source"] == "JSON_LD"


def test_resolver_404_with_master_domain_partial():
    ats_url = "https://jobs.lever.co/missing"
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 404,
                "final_url": ats_url,
                "html": "",
            },
            "https://www.master.com": {
                "status": 200,
                "final_url": "https://www.master.com",
                "html": "<html></html>",
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(
        resolver.resolve_one(ats_url, master_company_domain="master.com")
    )
    assert result.company_domain == "master.com"
    assert result.corporate_url == ""
    assert debug.status == "PARTIAL"
    assert debug.evidence["domain_source"] == "MASTER_DB"


def test_social_only_not_found():
    ats_url = "https://jobs.lever.co/social"
    html = """
    <html>
      <footer><a href="https://www.linkedin.com/company/example">LinkedIn</a></footer>
    </html>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            }
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(resolver.resolve_one(ats_url))
    assert result.company_domain == ""
    assert result.corporate_url == ""
    assert debug.status == "NOT_FOUND"


def test_sitemap_resolves_careers():
    ats_url = "https://jobs.lever.co/sitemapco"
    html = """
    <html>
      <footer><a href="https://www.sitemapco.com">Company</a></footer>
    </html>
    """
    sitemap_xml = """
    <urlset>
      <url><loc>https://www.sitemapco.com/careers</loc></url>
      <url><loc>https://www.sitemapco.com/blog</loc></url>
    </urlset>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://www.sitemapco.com": {
                "status": 200,
                "final_url": "https://www.sitemapco.com",
                "html": "<html></html>",
            },
            "https://www.sitemapco.com/sitemap.xml": {
                "status": 200,
                "final_url": "https://www.sitemapco.com/sitemap.xml",
                "html": sitemap_xml,
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(
        resolver.resolve_one(ats_url, enable_sitemap_scan=True)
    )
    assert result.company_domain == "sitemapco.com"
    assert result.corporate_url == "https://www.sitemapco.com/careers"
    assert debug.status == "RESOLVED"
    assert debug.evidence["careers_source"] == "CORP_SITEMAP"
    assert "sitemap_url" in debug.evidence
    assert "sitemap_candidates" in debug.evidence


def test_sitemap_no_careers_partial():
    ats_url = "https://jobs.lever.co/partialco"
    html = """
    <html>
      <footer><a href="https://www.partialco.com">Company</a></footer>
    </html>
    """
    sitemap_xml = """
    <urlset>
      <url><loc>https://www.partialco.com/blog/careers-growth</loc></url>
      <url><loc>https://www.partialco.com/news/jobs-update</loc></url>
    </urlset>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://www.partialco.com": {
                "status": 200,
                "final_url": "https://www.partialco.com",
                "html": "<html></html>",
            },
            "https://www.partialco.com/sitemap.xml": {
                "status": 200,
                "final_url": "https://www.partialco.com/sitemap.xml",
                "html": sitemap_xml,
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(
        resolver.resolve_one(ats_url, enable_sitemap_scan=True)
    )
    assert result.company_domain == "partialco.com"
    assert result.corporate_url == ""
    assert debug.status == "PARTIAL"
    assert "sitemap_no_careers" in debug.notes


def test_sitemap_index_first_child():
    ats_url = "https://jobs.lever.co/indexco"
    html = """
    <html>
      <footer><a href="https://www.indexco.com">Company</a></footer>
    </html>
    """
    sitemap_index = """
    <sitemapindex>
      <sitemap><loc>https://www.indexco.com/sitemap-jobs.xml</loc></sitemap>
    </sitemapindex>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://www.indexco.com": {
                "status": 200,
                "final_url": "https://www.indexco.com",
                "html": "<html></html>",
            },
            "https://www.indexco.com/sitemap.xml": {
                "status": 200,
                "final_url": "https://www.indexco.com/sitemap.xml",
                "html": sitemap_index,
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(
        resolver.resolve_one(ats_url, enable_sitemap_scan=True)
    )
    assert result.company_domain == "indexco.com"
    assert result.corporate_url == ""
    assert debug.status == "PARTIAL"
    assert "sitemap_index_encountered" in debug.notes


def test_sitemap_blocked_partial():
    ats_url = "https://jobs.lever.co/blockedco"
    html = """
    <html>
      <footer><a href="https://www.blockedco.com">Company</a></footer>
    </html>
    """
    client = FakeHTTPClient(
        {
            ats_url: {
                "status": 200,
                "final_url": ats_url,
                "html": html,
            },
            "https://www.blockedco.com": {
                "status": 200,
                "final_url": "https://www.blockedco.com",
                "html": "<html></html>",
            },
            "https://www.blockedco.com/sitemap.xml": {
                "status": 403,
                "final_url": "https://www.blockedco.com/sitemap.xml",
                "html": "",
            },
        }
    )
    resolver = CareersResolver(client=client, max_fetches=4)
    result, debug = run_async(
        resolver.resolve_one(ats_url, enable_sitemap_scan=True)
    )
    assert result.company_domain == "blockedco.com"
    assert result.corporate_url == ""
    assert debug.status == "PARTIAL"
    assert "sitemap_missing" in debug.notes
