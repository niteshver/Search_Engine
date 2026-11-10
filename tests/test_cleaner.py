from src.processing.cleaner import TextCleaner

def test_cleaner_html_stripping():
    cleaner = TextCleaner()
    html_text = "<html><body><h1>Hello World</h1><p>This is a test page.</p></body></html>"
    res = cleaner.clean(html_text, "https://example.com/test")
    assert "<html>" not in res["text"]
    assert "Hello World" in res["text"]
    assert "test page" in res["text"]

def test_cleaner_unicode_and_whitespace():
    cleaner = TextCleaner()
    text = "Hello\u00a0World!   This   is   a \n\n\n\n test."
    res = cleaner.clean(text, "https://example.com/test")
    assert "  " not in res["text"]
    # Check that newlines are normalized to at most 2 consecutive newlines
    assert "\n\n\n" not in res["text"]
    assert "Hello World!" in res["text"]

def test_cleaner_pii_masking():
    cleaner = TextCleaner()
    text = "Contact me at user@example.com or call +1-555-0199. My IP is 192.168.1.1."
    res = cleaner.clean(text, "https://example.com/test")
    assert "user@example.com" not in res["text"]
    assert "192.168.1.1" not in res["text"]
    assert "[EMAIL_MASKED]" in res["text"]
    assert "[IP_MASKED]" in res["text"]

def test_cleaner_metadata_extraction():
    cleaner = TextCleaner()
    text = "This is a simple document with some content. Code: ```python print('hello') ```"
    res = cleaner.clean(text, "https://example.com/test")
    meta = res["metadata"]
    assert meta["word_count"] > 5
    assert meta["has_code"] is True
    assert meta["language"] == "en"
    assert meta["domain"] == "example.com"

def test_cleaner_removes_scripts_and_styles():
    cleaner = TextCleaner()

    html = (
        "<html><head><style>body {color: red;}</style></head>"
        "<body><script>alert('hello')</script>"
        "<p>Useful content</p></body></html>"
    )

    result = cleaner.clean(html, "https://example.com")

    assert "Useful content" in result["text"]
    assert "alert" not in result["text"]
    assert "color: red" not in result["text"]


def test_cleaner_decodes_html_entities():
    cleaner = TextCleaner()

    result = cleaner.clean(
        "<p>Python &amp; Machine Learning&nbsp;Tutorial</p>",
        "https://example.com",
    )

    assert "Python & Machine Learning Tutorial" in result["text"]
    assert "&amp;" not in result["text"]


def test_cleaner_preserves_technical_numbers():
    cleaner = TextCleaner()

    result = cleaner.clean(
        "Python 3.14 was released in 2025. "
        "The server returned HTTP 404 and 500.",
        "https://example.com",
    )

    assert "3.14" in result["text"]
    assert "2025" in result["text"]
    assert "404" in result["text"]
    assert "500" in result["text"]