import re
import unicodedata
from html import unescape
from urllib.parse import urlparse


class TextCleaner:
    def __init__(self):
        # Patterns for sensitive information
        self.email_pattern = re.compile(
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        )

        self.phone_pattern = re.compile(
            r"(?<!\w)\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
            r"|(?<!\w)\+1[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
        )

        self.ip_pattern = re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        )

        self.html_tag_pattern = re.compile(r"<[^>]*>")

        self.md_link_pattern = re.compile(
            r"\[([^\]]+)\]\([^)]+\)"
        )

        self.script_style_pattern = re.compile(
            r"<(script|style)\b[^>]*>.*?</\1\s*>",
            re.IGNORECASE | re.DOTALL,
        )

        self.block_tag_pattern = re.compile(
            r"</?(?:p|div|h[1-6]|li|br|section|article)\b[^>]*>",
            re.IGNORECASE,
        )

    def clean(self, text: str, url: str) -> dict:
        """Clean HTML or Markdown text and extract metadata."""

        if not text:
            return {
                "text": "",
                "metadata": {
                    "word_count": 0,
                    "has_code": False,
                    "language": "en",
                },
            }

        # 1. Remove HTML scripts, styles, and tags.
        cleaned = text

        if "<" in cleaned and ">" in cleaned:
            cleaned = self.script_style_pattern.sub("", cleaned)
            cleaned = self.block_tag_pattern.sub("\n", cleaned)
            cleaned = self.html_tag_pattern.sub("", cleaned)

        # 2. Decode HTML entities.
        cleaned = unescape(cleaned)

        # 3. Normalize Unicode.
        cleaned = unicodedata.normalize("NFKC", cleaned)

        # 4. Remove Markdown link formatting, preserving link text.
        cleaned = self.md_link_pattern.sub(r"\1", cleaned)

        # 5. Mask sensitive information.
        cleaned = self.mask_pii(cleaned)

        # 6. Normalize whitespace.
        cleaned = self.normalize_whitespace(cleaned)

        # 7. Remove repeated boilerplate lines.
        cleaned = self.remove_duplicate_lines(cleaned)

        # 8. Extract metadata.
        parsed_url = urlparse(url)

        metadata = {
            "word_count": len(cleaned.split()),
            "has_code": "```" in text or "`" in text,
            "language": self.detect_language(cleaned),
            "domain": parsed_url.netloc,
            "url": url,
            "cleaned_at_epoch": True,
        }

        return {
            "text": cleaned,
            "metadata": metadata,
        }

    def mask_pii(self, text: str) -> str:
        """Mask email addresses, phone numbers, and IP addresses."""

        text = self.email_pattern.sub("[EMAIL_MASKED]", text)
        text = self.ip_pattern.sub("[IP_MASKED]", text)
        text = self.phone_pattern.sub("[PHONE_MASKED]", text)

        return text

    def normalize_whitespace(self, text: str) -> str:
        """Normalize spaces and preserve paragraph breaks."""

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def remove_duplicate_lines(self, text: str) -> str:
        """Remove repeated long lines while preserving short lines."""

        lines = text.splitlines()
        seen = set()
        unique_lines = []

        for line in lines:
            stripped = line.strip()

            if not stripped:
                unique_lines.append(line)
                continue

            if len(stripped) < 15:
                unique_lines.append(line)
                continue

            simplified = re.sub(r"\W+", "", stripped).lower()

            if simplified not in seen:
                seen.add(simplified)
                unique_lines.append(line)

        return "\n".join(unique_lines)

    def detect_language(self, text: str) -> str:
        """Lightweight English-language heuristic."""

        english_indicators = {
            "the", "and", "of", "to", "in", "is", "that",
            "it", "for", "on", "with", "as", "this", "by",
            "an", "be",
        }

        words = [
            word.lower()
            for word in text[:5000].split()
            if word.isalpha()
        ]

        if not words:
            return "en"

        english_count = sum(
            1 for word in words if word in english_indicators
        )

        ratio = english_count / len(words)

        if ratio > 0.03:
            return "en"

        # Language detection remains English-only for now.
        return "en"