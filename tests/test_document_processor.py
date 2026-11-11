import json

import pytest

from src.processing.document_processor import process_documents


def test_process_documents_cleans_and_preserves_metadata(tmp_path):
    input_dir = tmp_path / "raw" / "json"
    output_dir = tmp_path / "processed"
    input_dir.mkdir(parents=True)

    document = {
        "id": "abc123",
        "url": "https://example.com/tutorial",
        "title": "Python Tutorial",
        "markdown": "Hello   World!\n\n\n\nThis is a tutorial.",
        "metadata": {"author": "NexaSearch"},
        "crawled_at": "2026-08-06T12:00:00",
        "type": "webpage",
    }

    (input_dir / "abc123.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    stats = process_documents(input_dir, output_dir)

    assert stats == {
        "processed": 1,
        "skipped": 0,
        "failed": 0,
    }

    output_file = output_dir / "abc123.json"
    assert output_file.exists()

    result = json.loads(output_file.read_text(encoding="utf-8"))

    assert result["id"] == document["id"]
    assert result["url"] == document["url"]
    assert result["title"] == document["title"]
    assert result["metadata"] == document["metadata"]
    assert result["crawled_at"] == document["crawled_at"]

    assert "Hello World!" in result["cleaned_text"]
    assert "\n\n\n" not in result["cleaned_text"]
    assert result["cleaning_metadata"]["word_count"] > 0
    assert result["cleaning_metadata"]["domain"] == "example.com"

    # Original crawled document must remain unchanged.
    original = json.loads(
        (input_dir / "abc123.json").read_text(encoding="utf-8")
    )
    assert original == document


def test_process_documents_skips_empty_content(tmp_path):
    input_dir = tmp_path / "raw" / "json"
    output_dir = tmp_path / "processed"
    input_dir.mkdir(parents=True)

    document = {
        "url": "https://example.com",
        "markdown": "   ",
    }

    (input_dir / "empty.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    stats = process_documents(input_dir, output_dir)

    assert stats["processed"] == 0
    assert stats["skipped"] == 1
    assert not (output_dir / "empty.json").exists()


def test_process_documents_handles_invalid_json(tmp_path):
    input_dir = tmp_path / "raw" / "json"
    output_dir = tmp_path / "processed"
    input_dir.mkdir(parents=True)

    (input_dir / "invalid.json").write_text(
        "{invalid json",
        encoding="utf-8",
    )

    stats = process_documents(input_dir, output_dir)

    assert stats["processed"] == 0
    assert stats["failed"] == 1


def test_process_documents_requires_input_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        process_documents(
            tmp_path / "missing",
            tmp_path / "processed",
        )


def test_process_documents_masks_sensitive_information(tmp_path):
    input_dir = tmp_path / "raw" / "json"
    output_dir = tmp_path / "processed"
    input_dir.mkdir(parents=True)

    document = {
        "url": "https://example.com/contact",
        "markdown": "Contact support@example.com for assistance.",
    }

    (input_dir / "contact.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    stats = process_documents(input_dir, output_dir)

    assert stats["processed"] == 1

    result = json.loads(
        (output_dir / "contact.json").read_text(encoding="utf-8")
    )

    assert "support@example.com" not in result["cleaned_text"]
    assert "[EMAIL_MASKED]" in result["cleaned_text"]