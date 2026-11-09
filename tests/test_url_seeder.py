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

def test_master_seed_xml_validation(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET

    seeder = EnterpriseURLSeeder()

    seeder.add_crawl_domain(
        "example.com",
        [
            "https://example.com/python",
            "https://example.com/java",
            "https://example.com/python",
        ],
    )

    monkeypatch.setattr(
        "src.seeder.url_seeder.settings.BASE_DIR",
        tmp_path,
    )

    output = Path(seeder.finalize_crawl_domain())

    tree = ET.parse(output)
    root = tree.getroot()

    namespace = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9"
    }

    urls = [
        element.text
        for element in root.findall("sm:url/sm:loc", namespace)
    ]

    assert len(urls) == 2
    assert len(urls) == len(set(urls))
def test_seed_domain_failure_does_not_stop_next_domain():
    """Verify that one failed domain does not stop subsequent domains."""
    import asyncio
    from unittest.mock import AsyncMock

    seeder = EnterpriseURLSeeder()

    mock_seeder = AsyncMock()
    mock_seeder.urls.side_effect = [
        RuntimeError("Simulated domain failure"),
        [{"url": "https://example.com/docs"}],
    ]

    config = {
        "urls_estimate": 10,
        "priority": 1,
        "reputation": 1,
        "source_type": "documentation",
    }

    async def run_test():
        await seeder._seed_domain(
            mock_seeder, "failed.example.com", config, 1, 2
        )

        await seeder._seed_domain(
            mock_seeder, "example.com", config, 2, 2
        )

    asyncio.run(run_test())

    assert mock_seeder.urls.await_count == 2
    assert len(seeder.failed_sources) == 1
    assert seeder.failed_sources[0]["domain"] == "failed.example.com"
    assert seeder.failed_sources[0]["error"] == "Simulated domain failure"
    assert "https://example.com/docs" in seeder.discovered_urls
    assert "example.com" in seeder.urls_by_source

