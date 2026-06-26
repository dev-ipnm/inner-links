"""Tests for site_relinker.html_ops — HTML scoping and anchor matching."""

from __future__ import annotations

from bs4 import BeautifulSoup

from site_relinker.html_ops import AnchorMatcher, ContentScope
from site_relinker.models import ScopeDefinition, ScopeType


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class TestContentScope:
    """Tests for the ContentScope class (tests 1-5)."""

    def test_scope_element_id_found(self, sample_html: str) -> None:
        """Scopes to the correct element by id."""
        soup = _parse(sample_html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.ELEMENT_ID,
            scope_value="main-content",
        )
        scope = ContentScope(soup, scope_def)
        result = scope.resolve()

        assert result is not None
        assert result.get("id") == "main-content"
        text = result.get_text()
        assert "main content area" in text
        assert "Sidebar" not in text

    def test_scope_element_id_missing(self, sample_html: str) -> None:
        """Returns None when element id is not found."""
        soup = _parse(sample_html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.ELEMENT_ID,
            scope_value="nonexistent",
        )
        scope = ContentScope(soup, scope_def)
        result = scope.resolve()

        assert result is None

    def test_scope_below_boundary(self, sample_html: str) -> None:
        """Content after boundary only is returned."""
        soup = _parse(sample_html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="Section Divider",
        )
        scope = ContentScope(soup, scope_def)
        result = scope.resolve()

        assert result is not None
        text = result.get_text()
        assert "below the divider" in text
        assert "Section Divider" not in text
        assert "main content area" not in text

    def test_scope_above_boundary(self, sample_html: str) -> None:
        """Content before boundary only is returned."""
        soup = _parse(sample_html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.ABOVE,
            scope_value="Section Divider",
        )
        scope = ContentScope(soup, scope_def)
        result = scope.resolve()

        assert result is not None
        text = result.get_text()
        assert "main content area" in text
        assert "Section Divider" not in text
        assert "below the divider" not in text

    def test_scope_whole_body(self, sample_html: str) -> None:
        """Full body when no scope defined."""
        soup = _parse(sample_html)
        scope_def = ScopeDefinition()
        scope = ContentScope(soup, scope_def)
        result = scope.resolve()

        assert result is not None
        assert result.name == "body"
        text = result.get_text()
        assert "main content area" in text
        assert "Sidebar" in text
        assert "Footer" in text


class TestAnchorMatcher:
    """Tests for the AnchorMatcher class (tests 6-10)."""

    def test_anchor_match_case_insensitive(self) -> None:
        """'Help' matches 'help' case-insensitively."""
        html = "<html><body><p>Get help with your account.</p></body></html>"
        soup = _parse(html)
        body = soup.find("body")
        assert body is not None

        matcher = AnchorMatcher(body, "Help")
        matches = matcher.find_all()

        assert len(matches) == 1
        assert str(matches[0].text_node)[matches[0].start : matches[0].end].lower() == "help"

    def test_anchor_match_word_boundary(self) -> None:
        """'link' doesn't match 'linking' due to word boundary."""
        html = "<html><body><p>We are linking to pages. Here is a link.</p></body></html>"
        soup = _parse(html)
        body = soup.find("body")
        assert body is not None

        matcher = AnchorMatcher(body, "link")
        matches = matcher.find_all()

        assert len(matches) == 1
        text = str(matches[0].text_node)
        assert text[matches[0].start : matches[0].end].lower() == "link"

    def test_anchor_match_at_start_of_text(self) -> None:
        """Boundary at text node start is handled correctly."""
        html = "<html><body><p>click here for more</p></body></html>"
        soup = _parse(html)
        body = soup.find("body")
        assert body is not None

        matcher = AnchorMatcher(body, "click here")
        matches = matcher.find_all()

        assert len(matches) == 1
        assert matches[0].start == 0

    def test_anchor_match_at_end_of_text(self) -> None:
        """Boundary at text node end is handled correctly."""
        html = "<html><body><p>please click here</p></body></html>"
        soup = _parse(html)
        body = soup.find("body")
        assert body is not None

        matcher = AnchorMatcher(body, "click here")
        matches = matcher.find_all()

        assert len(matches) == 1
        text = str(matches[0].text_node)
        assert matches[0].end == len(text)

    def test_strict_text_only_skips_linked(self) -> None:
        """In strict mode, doesn't match inside existing <a> tags."""
        html = (
            "<html><body>"
            '<p>Visit <a href="/page">click here</a> or click here again.</p>'
            "</body></html>"
        )
        soup = _parse(html)
        body = soup.find("body")
        assert body is not None

        matcher = AnchorMatcher(body, "click here", strict_text_only=True)
        matches = matcher.find_all()

        assert len(matches) == 1
        parent = matches[0].text_node.parent
        assert parent is not None
        assert parent.name != "a"

        matcher_non_strict = AnchorMatcher(
            body, "click here", strict_text_only=False
        )
        matches_non_strict = matcher_non_strict.find_all()
        assert len(matches_non_strict) == 2
