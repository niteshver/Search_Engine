from pathlib import Path

from src.seeder.url_seeder import EnterpriseURLSeeder


def test_add_crawl_domain_deduplicates_and_normalizes_urls():
    seeder = EnterpriseURLSeeder()

    added = seeder.add_crawl_domain(
        "Example.COM",
        [
            "HTTPS://Example.COM/docs#intro",
            "https://example.com/docs",
            "not-a-url",
        ],
    )

    assert added == 1
    assert list(seeder.discovered_urls) == ["https://example.com/docs"]
    assert seeder.urls_by_source["example.com"][0]["source"] == "example.com"


def test_finalize_crawl_domain_writes_valid_deduplicated_sitemap(tmp_path, monkeypatch):
    seeder = EnterpriseURLSeeder()
    seeder.add_crawl_domain("example.com", ["https://example.com/a", "https://example.com/a#section"])
    monkeypatch.setattr("src.seeder.url_seeder.settings.BASE_DIR", Path(tmp_path))

    output = Path(seeder.finalize_crawl_domain())

    assert output.exists()
    assert output.read_text(encoding="utf-8").count("<loc>https://example.com/a</loc>") == 1
