from src.patterns.ats_fingerprints import detect_fingerprints


def test_detect_fingerprints_greenhouse():
    html = "<script>var x = 'boards.greenhouse.io';</script>"
    assert detect_fingerprints(html) == {"GREENHOUSE"}


def test_detect_fingerprints_multiple():
    html = "lever.co and apply.workable.com"
    assert detect_fingerprints(html) == {"LEVER", "WORKABLE"}
