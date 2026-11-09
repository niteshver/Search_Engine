import json
from pathlib import Path
import xml.etree.ElementTree as ET

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


def test_finalize_crawl_domain_writes_valid_deduplicated_sitemap(
    tmp_path, monkeypatch
):
    seeder = EnterpriseURLSeeder()

    seeder.add_crawl_domain(
        "example.com",
        [
            "https://example.com/a",
            "https://example.com/a#section",
        ],
    )

    monkeypatch.setattr(
        "src.seeder.url_seeder.settings.BASE_DIR",
        Path(tmp_path),
    )

    output = Path(seeder.finalize_crawl_domain())

    assert output.exists()

    assert (
        output.read_text(encoding="utf-8").count(
            "<loc>https://example.com/a</loc>"
        )
        == 1
    )


def test_master_seed_xml_validation(tmp_path, monkeypatch):
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


def test_consolidated_seed_file_contains_unique_urls():
    base = (
        Path(__file__).resolve().parents[1]
        / "data/raw/sitemap"
    )

    with open(base / "seeds.json", encoding="utf-8") as f:
        main = json.load(f)

    urls = main["urls"]

    # Verify consolidation contains the expected number of URLs.
    assert len(urls) == 31419

    # Verify there are no duplicate URLs.
    assert len(urls) == len(set(urls))

    # Verify URLs are sorted.
    assert urls == sorted(urls)

    # Verify metadata matches the consolidated data.
    assert main["metadata"]["total_urls"] == len(urls)

    assert (
        main["metadata"]["sources_succeeded"]
        == len(main["by_source"])
    )

    assert (
        main["metadata"]["sources_failed"]
        == len(main["failed_sources"])
    )

    # Verify additional sources were preserved.
    assert "anthropic.com" in main["by_source"]
    assert "numpy.org" in main["by_source"]

    # Verify expected source counts.
    assert len(main["by_source"]) == 42
    assert len(main["failed_sources"]) == 5