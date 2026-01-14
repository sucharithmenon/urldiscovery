from src.extractors.company_name import extract as extract_company_name
from src.extractors.corporate_url import extract as extract_corporate_url
from src.extractors.domain import extract_domain


def test_extract_domain_cc_tld():
    assert extract_domain("https://jobs.company.co.uk") == "company.co.uk"
    assert extract_domain("https://careers.company.com.au/jobs") == "company.com.au"


def test_company_name_title_cleanup():
    html = "<title>Careers at Example Corp</title>"
    assert extract_company_name(html, slug="example", mode="strict") == "Example Corp"


def test_company_name_career_page_cleanup():
    html = "<title>Actif.ai - Career Page</title>"
    assert extract_company_name(html, slug="actif-ai", mode="strict") == "Actif.ai"


def test_company_name_inactive_career_page_cleanup():
    html = "<title>JazzHR - Inactive Career Page</title>"
    assert extract_company_name(html, slug="jazzhr", mode="strict") == "JazzHR"


def test_company_name_current_openings_cleanup():
    html = "<title>Acme Corp - Current Openings</title>"
    assert extract_company_name(html, slug="acme", mode="strict") == "Acme Corp"


def test_company_name_current_openings_prefix_cleanup():
    html = "<title>Current Openings - Beta LLC</title>"
    assert extract_company_name(html, slug="beta", mode="strict") == "Beta LLC"


def test_company_name_search_jobs_prefix_cleanup():
    html = "<title>Search Jobs | Marriott International</title>"
    assert extract_company_name(html, slug="marriott", mode="strict") == "Marriott International"


def test_corporate_url_extractor():
    html = "<a href=\"https://www.example.com/careers\">Careers</a>"
    result = extract_corporate_url(html, "https://boards.greenhouse.io/example")
    assert result is not None
    assert result.value == "https://www.example.com/careers"
    assert result.confidence == "verified"


def test_corporate_url_extractor_rejects_vendor_domain():
    html = "<a href=\"https://info.jazzhr.com/job-seekers.html\">Company Website</a>"
    result = extract_corporate_url(html, "https://example.applytojob.com")
    assert result is None
