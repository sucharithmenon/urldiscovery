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


def test_validate_jazzhr_root_valid():
    html = """
    <title>Acme - Career Page</title>
    <a href="https://acme.applytojob.com/apply/abc123/Engineer">Engineer</a>
    <a href="https://acme.applytojob.com/apply/def456/Designer">Designer</a>
    """
    result = validate_ats_root_content(
        "https://acme.applytojob.com/apply",
        "JAZZHR",
        "acme",
        html,
    )
    assert result.status == "valid"


def test_validate_hiringthing_root_valid():
    html = """
    <title>Careers at Acme</title>
    <a href="/jobs/123">Job 1</a>
    <a href="/jobs/456">Job 2</a>
    """
    result = validate_ats_root_content(
        "https://acme.hiringthing.com/jobs",
        "HIRINGTHING",
        "acme",
        html,
    )
    assert result.status == "valid"


def test_validate_breezy_root_valid():
    html = """
    <title>Careers at Finova</title>
    <a href="/p/8720053a48a301-director-of-software-delivery-management">Job 1</a>
    <a href="/p/95db982b6e6801-principal-engineer">Job 2</a>
    """
    result = validate_ats_root_content(
        "https://finova.breezy.hr",
        "BREEZY_HR",
        "finova",
        html,
    )
    assert result.status == "valid"
