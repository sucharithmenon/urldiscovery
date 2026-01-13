from src.patterns.ats_patterns import detect, normalize, is_job_url


def test_greenhouse_normalize():
    url = "https://boards.greenhouse.io/algolia/jobs/4823265"
    assert normalize(url) == "https://boards.greenhouse.io/algolia"
    assert is_job_url(url)


def test_lever_normalize():
    url = "https://jobs.lever.co/stripe/abc-123-def"
    assert normalize(url) == "https://jobs.lever.co/stripe"


def test_workday_normalize():
    url = "https://company.wd5.myworkdayjobs.com/careers/job/NYC/Engineer/12345"
    assert normalize(url) == "https://company.wd5.myworkdayjobs.com/careers"


def test_workday_alt_normalize():
    url = "https://cisco.wd5.myworkdayjobs.com/External_Careers/12345"
    assert normalize(url) == "https://cisco.wd5.myworkdayjobs.com/External_Careers"


def test_detect():
    assert detect("https://boards.greenhouse.io/algolia") == ("GREENHOUSE", "algolia")
    assert detect("https://jobs.lever.co/stripe") == ("LEVER", "stripe")
    assert detect("https://example.com/careers") is None


def test_registry_detect():
    url = "https://paycomonline.net/v4/ats/web.php/portal/61EC6A9ACCFDEBAEE9753D4F68AFC981/jobs/27194"
    assert detect(url) == ("PAYCOM", "")
