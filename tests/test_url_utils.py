"""Tests for site_relinker.url_utils — URL classification and normalization."""

from __future__ import annotations

import pytest

from site_relinker.models import ConfigError
from site_relinker.url_utils import (
    is_internal,
    normalize_to_relative,
    resolve_relative,
    sanitize_classes,
)


class TestIsInternal:
    """Tests for the is_internal function."""

    def test_is_internal_https_match(self) -> None:
        """HTTPS URL with matching domain is internal."""
        assert is_internal("https://example.com/page", ["example.com"]) is True

    def test_is_internal_http_match(self) -> None:
        """HTTP URL with matching domain is internal."""
        assert is_internal("http://example.com/page", ["example.com"]) is True

    def test_is_internal_protocol_relative(self) -> None:
        """Protocol-relative URL with matching domain is internal."""
        assert is_internal("//example.com/page", ["example.com"]) is True

    def test_is_internal_root_relative(self) -> None:
        """Root-relative URL is always internal."""
        assert is_internal("/page.html", ["example.com"]) is True

    def test_is_internal_external_url(self) -> None:
        """URL with non-matching domain is external."""
        assert is_internal("https://other.com/page", ["example.com"]) is False

    def test_is_internal_subdomain(self) -> None:
        """Subdomain does not match bare domain."""
        assert (
            is_internal("https://sub.example.com/page", ["example.com"]) is False
        )


class TestNormalizeToRelative:
    """Tests for the normalize_to_relative function."""

    def test_normalize_strips_domain(self) -> None:
        """Full URL is normalized to root-relative path."""
        result = normalize_to_relative(
            "https://example.com/help/topic.html", ["example.com"]
        )
        assert result == "/help/topic.html"

    def test_normalize_preserves_path_and_query(self) -> None:
        """Query string and fragment are preserved after normalization."""
        result = normalize_to_relative(
            "https://example.com/page?q=1#section", ["example.com"]
        )
        assert result == "/page?q=1#section"

    def test_normalize_external_raises(self) -> None:
        """ValueError is raised for external URLs."""
        with pytest.raises(ValueError, match="external"):
            normalize_to_relative(
                "https://other.com/page", ["example.com"]
            )


class TestResolveRelative:
    """Tests for the resolve_relative function."""

    def test_resolve_relative_absolute_href(self) -> None:
        """Absolute href is returned as-is."""
        result = resolve_relative(
            "https://example.com/dir/page.html",
            "https://other.com/page",
        )
        assert result == "https://other.com/page"

    def test_resolve_relative_path(self) -> None:
        """Relative path is resolved against base URL."""
        result = resolve_relative(
            "https://example.com/dir/page.html",
            "other.html",
        )
        assert result == "https://example.com/dir/other.html"


class TestSanitizeClasses:
    """Tests for the sanitize_classes function."""

    def test_sanitize_classes_rejects_invalid(self) -> None:
        """Class name with invalid characters raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid CSS class name"):
            sanitize_classes(["valid-class", "class!name"])
