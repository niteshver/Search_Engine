"""Process crawled JSON documents into cleaned documents."""

import json
from pathlib import Path

from src.processing.cleaner import TextCleaner


def process_documents(
    input_dir: Path,
    output_dir: Path,
) -> dict:
    """
    Clean crawled JSON documents and save them to the processed directory.

    Returns processing statistics.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    cleaner = TextCleaner()

    stats = {
        "processed": 0,
        "skipped": 0,
        "failed": 0,
    }

    for input_path in sorted(input_dir.glob("*.json")):
        try:
            with input_path.open("r", encoding="utf-8") as file:
                document = json.load(file)

            if not isinstance(document, dict):
                stats["skipped"] += 1
                continue

            markdown = document.get("markdown", "")
            url = document.get("url", "")

            if not isinstance(markdown, str) or not markdown.strip():
                stats["skipped"] += 1
                continue

            if not isinstance(url, str) or not url.strip():
                stats["skipped"] += 1
                continue

            result = cleaner.clean(markdown, url)

            if not result["text"].strip():
                stats["skipped"] += 1
                continue

            processed_document = {
                **document,
                "cleaned_text": result["text"],
                "cleaning_metadata": result["metadata"],
            }

            output_path = output_dir / input_path.name

            with output_path.open("w", encoding="utf-8") as file:
                json.dump(
                    processed_document,
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            stats["processed"] += 1

        except (OSError, ValueError, TypeError):
            stats["failed"] += 1

    return stats


if __name__ == "__main__":
    from src.config.settings import settings

    base_dir = settings.absolute_db_path.parent

    stats = process_documents(
        input_dir=base_dir / "raw/json",
        output_dir=base_dir / "processed",
    )

    print(f"Processing complete: {stats}")