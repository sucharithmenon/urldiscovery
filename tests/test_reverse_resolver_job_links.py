from src.resolvers.reverse_resolver import _find_job_detail_links


def test_find_job_detail_links():
    html = """
    <a href="/careers">Careers</a>
    <a href="/careers/jobs/software-engineer">Software Engineer</a>
    <div data-job-url="https://jobs.company.com/jobs/123">Apply</div>
    <div data-url="/positions/123">View</div>
    """
    links = _find_job_detail_links(html, "https://company.com/careers")

    assert "https://company.com/careers/jobs/software-engineer" in links
    assert "https://jobs.company.com/jobs/123" in links
    assert "https://company.com/positions/123" in links
    assert "https://company.com/careers" not in links
