from src.validators.ats_root_validator import validate_ats_root_content


def test_validate_greenhouse_root_valid():
    html = """
    <html><head><title>Careers at Acme</title></head>
    <body>
      <a href="/acme/jobs/123">Engineer</a>
      <a href="/acme/jobs/456">Designer</a>
    </body></html>
    """
    result = validate_ats_root_content(
        "https://boards.greenhouse.io/acme",
        "GREENHOUSE",
        "acme",
        html,
    )
    assert result.status == "valid"
    assert result.job_count >= 2


def test_validate_greenhouse_root_empty():
    html = "<title>Careers at Acme</title><div>No open positions</div>"
    result = validate_ats_root_content(
        "https://boards.greenhouse.io/acme",
        "GREENHOUSE",
        "acme",
        html,
    )
    assert result.status == "valid_empty"


def test_validate_greenhouse_root_invalid_slug():
    html = "<title>Careers at Acme</title>"
    result = validate_ats_root_content(
        "https://boards.greenhouse.io/acme",
        "GREENHOUSE",
        "other",
        html,
    )
    assert result.status == "invalid"
