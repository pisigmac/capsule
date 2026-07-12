"""Tests for the CapsuleParser."""
import pytest
from datetime import datetime, timezone

from services.parser.parser import CapsuleParser, ParsedCapsule


class TestCapsuleParser:
    """Test suite for capsule parsing."""

    def test_parse_valid_capsule(self, parser, sample_capsule_text):
        """Parser should extract all fields from a valid capsule."""
        parsed = parser.parse_text(sample_capsule_text)

        assert parsed.topic == "Auth middleware bypass in staging"
        assert "JWT verification" in parsed.content
        assert parsed.tags == ["bug", "auth", "staging"]
        assert parsed.confidence == "high"
        assert parsed.source == "Claude session #4482"
        assert parsed.freshness is not None

    def test_parse_without_frontmatter(self, parser):
        """Parser should handle capsules without YAML frontmatter."""
        text = "# My Topic\n\nSome content here."
        parsed = parser.parse_text(text)

        assert parsed.topic == "My Topic"
        assert parsed.content == "Some content here."
        assert parsed.tags == []
        assert parsed.confidence == "medium"

    def test_parse_topic_from_first_line(self, parser):
        """Parser should use first line as topic if no H1 or frontmatter."""
        text = "Just a sentence without headers."
        parsed = parser.parse_text(text)

        assert parsed.topic == "Just a sentence without headers."

    def test_parse_invalid_confidence_defaults_to_medium(self, parser):
        """Parser should default invalid confidence to medium."""
        text = "---\nconfidence: invalid\n---\n\nContent."
        parsed = parser.parse_text(text)

        assert parsed.confidence == "medium"

    def test_parse_tags_as_string(self, parser):
        """Parser should handle comma-separated tags in frontmatter."""
        text = "---\ntags: auth, bug, staging\n---\n\nContent."
        parsed = parser.parse_text(text)

        assert parsed.tags == ["auth", "bug", "staging"]

    def test_validate_valid_capsule(self, parser, sample_capsule_text):
        """Validation should return no errors for valid capsule."""
        errors = parser.validate(sample_capsule_text)
        assert errors == []

    def test_validate_short_topic(self, parser):
        """Validation should catch short topics."""
        text = "---\ntopic: AB\n---\n\nContent here."
        errors = parser.validate(text)

        assert any("at least 3 characters" in e for e in errors)

    def test_validate_short_content(self, parser):
        """Validation should catch short content."""
        text = "---\ntopic: Valid Topic\n---\n\nHi"
        errors = parser.validate(text)

        assert any("at least 10 characters" in e for e in errors)

    def test_to_markdown_roundtrip(self, parser, sample_capsule_text):
        """Serializing and re-parsing should preserve data."""
        parsed = parser.parse_text(sample_capsule_text)
        md = parser.to_markdown(parsed)
        reparsed = parser.parse_text(md)

        assert reparsed.topic == parsed.topic
        assert reparsed.confidence == parsed.confidence
        assert reparsed.tags == parsed.tags

    def test_parse_file(self, parser, tmp_path):
        """Parser should read from file path."""
        file_path = tmp_path / "test.capsule.md"
        file_path.write_text("---\ntopic: File Test\n---\n\nFile content.")

        parsed = parser.parse_file(file_path)
        assert parsed.topic == "File Test"
        assert parsed.file_path == str(file_path)


class TestParsedCapsule:
    """Tests for the ParsedCapsule dataclass."""

    def test_default_values(self):
        """ParsedCapsule should have sensible defaults."""
        pc = ParsedCapsule(topic="Test", content="Content")

        assert pc.tags == []
        assert pc.confidence == "medium"
        assert pc.freshness is None
        assert pc.source is None
