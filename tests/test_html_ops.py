"""Tests for site_relinker.html_ops — HTML scoping, matching, and manipulation."""

from __future__ import annotations

from collections.abc import Callable

from bs4 import BeautifulSoup, Tag

from site_relinker.html_ops import AnchorMatcher, ContentScope, process_operation
from site_relinker.models import (
    AppConfig,
    LinkOperation,
    ResultStatus,
    ScopeDefinition,
    ScopeType,
)


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

    def test_scope_below_comment_substring(self) -> None:
        """Boundary matches a substring of an HTML comment."""
        html = (
            "<html><body>"
            "<p>Above the comment.</p>"
            "<!-- Content is located below -->"
            "<p>Below the comment.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="is located below -->",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Below the comment" in text
        assert "Above the comment" not in text

    def test_scope_above_comment_substring(self) -> None:
        """Above scope works with a substring of an HTML comment."""
        html = (
            "<html><body>"
            "<p>Above the comment.</p>"
            "<!-- Content is located below -->"
            "<p>Below the comment.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.ABOVE,
            scope_value="<!-- Content",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Above the comment" in text
        assert "Below the comment" not in text

    def test_scope_below_comment_inner_text(self) -> None:
        """Boundary matches the inner text of a comment (no delimiters)."""
        html = (
            "<html><body>"
            "<p>Before.</p>"
            "<!-- SECTION BREAK -->"
            "<p>After.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="SECTION BREAK",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "After" in text
        assert "Before" not in text

    def test_scope_below_text_node_substring(self) -> None:
        """Boundary substring matches within a regular text node."""
        html = (
            "<html><body>"
            "<p>This paragraph has important text here.</p>"
            "<p>Content after boundary.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="important text",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Content after boundary" in text

    def test_scope_below_tag_class_attribute(self) -> None:
        """Boundary matches a class attribute in a div's opening tag."""
        html = (
            "<html><body>"
            "<p>Header area.</p>"
            '<div class="entry-content prose">'
            "<p>Main article content here.</p>"
            "</div>"
            "<p>Footer area.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value='entry-content prose">',
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Main article content" in text
        assert "Footer area" in text
        assert "Header area" not in text

    def test_scope_above_tag_class_attribute(self) -> None:
        """Above scope works with a tag class attribute boundary."""
        html = (
            "<html><body>"
            "<p>Header area.</p>"
            '<div class="entry-content prose">'
            "<p>Main article content here.</p>"
            "</div>"
            "<p>Footer area.</p>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.ABOVE,
            scope_value='class="entry-content prose"',
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Header area" in text
        assert "Main article content" not in text

    def test_scope_below_tag_nested(self) -> None:
        """Tag boundary works when the matching tag is nested."""
        html = (
            "<html><body>"
            "<div id='wrapper'>"
            "<p>Before.</p>"
            '<div class="entry-content prose">'
            "<p>Inside entry.</p>"
            "</div>"
            "<p>After inside wrapper.</p>"
            "</div>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="entry-content prose",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        assert "Inside entry" in text
        assert "After inside wrapper" in text
        assert "Before" not in text

    def test_scope_below_tag_text_node_takes_priority(self) -> None:
        """Text node match takes priority over tag markup match."""
        html = (
            "<html><body>"
            "<p>Look for entry-content prose here.</p>"
            '<div class="entry-content prose">'
            "<p>Inside div.</p>"
            "</div>"
            "</body></html>"
        )
        soup = _parse(html)
        scope_def = ScopeDefinition(
            scope_type=ScopeType.BELOW,
            scope_value="entry-content prose",
        )
        result = ContentScope(soup, scope_def).resolve()

        assert result is not None
        text = result.get_text()
        # Text node match comes first, so "here." is the partial after
        # the boundary, and the div content follows
        assert "Inside div" in text


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
        m = matches[0]
        assert str(m.text_node)[m.start : m.end].lower() == "help"

    def test_anchor_match_word_boundary(self) -> None:
        """'link' doesn't match 'linking' due to word boundary."""
        html = (
            "<html><body><p>We are linking to pages."
            " Here is a link.</p></body></html>"
        )
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


class TestAddLink:
    """Tests for add link operations (tests 11-16)."""

    def test_add_link_basic(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Wraps anchor in <a> with correct href and classes."""
        html = "<html><body><p>Click here for info.</p></body></html>"
        op = make_operation(
            operation="add",
            anchor="Click here",
            target_url="/target.html",
        )
        config = make_config(link_classes=["inner-link", "batch-1"])

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "/target.html"
        assert "inner-link" in link.get("class", [])
        assert "batch-1" in link.get("class", [])
        assert link.get_text() == "Click here"

    def test_add_link_normalizes_internal_url(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Domain stripped on insertion for internal URLs."""
        html = "<html><body><p>Click here for info.</p></body></html>"
        op = make_operation(
            operation="add",
            anchor="Click here",
            target_url="https://example.com/target.html",
        )
        config = make_config(domains=["example.com"])

        modified, results = process_operation(html, op, config)

        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "/target.html"

    def test_add_link_external_url_gets_rel(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """External URL gets rel=noopener noreferrer."""
        html = "<html><body><p>Visit external site here.</p></body></html>"
        op = make_operation(
            operation="add",
            anchor="external site",
            target_url="https://other.com/page",
        )
        config = make_config(domains=["example.com"])

        modified, results = process_operation(html, op, config)

        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "https://other.com/page"
        rel = link.get("rel", [])
        assert "noopener" in rel
        assert "noreferrer" in rel

    def test_add_link_already_linked_skip(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """if_linked=skip leaves existing link unchanged."""
        html = (
            '<html><body><p><a href="/old.html">click here</a></p></body></html>'
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/new.html",
            if_linked="skip",
        )
        config = make_config(if_linked="skip", strict_text_only=False)

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.ALREADY_LINKED
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "/old.html"

    def test_add_link_already_linked_replace(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """if_linked=replace updates existing href."""
        html = (
            '<html><body><p><a href="/old.html">click here</a></p></body></html>'
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/new.html",
            if_linked="replace",
        )
        config = make_config(if_linked="replace", strict_text_only=False)

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "/new.html"

    def test_add_link_already_linked_error(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """if_linked=error records an error."""
        html = (
            '<html><body><p><a href="/old.html">click here</a></p></body></html>'
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/new.html",
            if_linked="error",
        )
        config = make_config(if_linked="error", strict_text_only=False)

        _, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.ERROR
        assert results[0].linked is True


class TestReplaceLink:
    """Tests for replace link operations (tests 17-18)."""

    def test_replace_link_updates_href(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Existing link href is changed."""
        html = (
            '<html><body><p><a href="/old.html">click here</a></p></body></html>'
        )
        op = make_operation(
            operation="replace",
            anchor="click here",
            target_url="/new.html",
        )
        config = make_config()

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        link = soup.find("a")
        assert isinstance(link, Tag)
        assert link["href"] == "/new.html"

    def test_replace_link_not_linked(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Anchor not in <a> tag produces an error."""
        html = "<html><body><p>click here for info</p></body></html>"
        op = make_operation(
            operation="replace",
            anchor="click here",
            target_url="/new.html",
        )
        config = make_config()

        _, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.ERROR
        assert "not inside a link" in results[0].detail


class TestRemoveLink:
    """Tests for remove link operations (tests 19-20)."""

    def test_remove_link_with_class_filter(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Only removes links matching specified classes."""
        html = (
            "<html><body>"
            '<p><a href="/a.html" class="inner-link">link A</a></p>'
            '<p><a href="/b.html" class="other-class">link B</a></p>'
            "</body></html>"
        )
        op_a = make_operation(operation="remove", anchor="link A", target_url=None)
        op_b = make_operation(operation="remove", anchor="link B", target_url=None)
        config = make_config(link_classes=["inner-link"])

        modified_a, results_a = process_operation(html, op_a, config)
        assert results_a[0].status == ResultStatus.SUCCESS

        _, results_b = process_operation(html, op_b, config)
        assert results_b[0].status == ResultStatus.SKIPPED

    def test_remove_link_preserves_text(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Anchor text remains after link removal."""
        html = (
            "<html><body><p>See "
            '<a href="/page.html">click here</a>'
            " for more.</p></body></html>"
        )
        op = make_operation(operation="remove", anchor="click here", target_url=None)
        config = make_config()

        modified, results = process_operation(html, op, config)

        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        assert soup.find("a") is None
        body = soup.find("body")
        assert body is not None
        assert "click here" in body.get_text()


class TestScanLink:
    """Tests for scan operations (tests 21-23)."""

    def test_scan_finds_linked_anchor(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Reports linked=True with target URL."""
        html = (
            "<html><body><p>"
            '<a href="/target.html" class="inner-link">'
            "click here</a></p></body></html>"
        )
        op = make_operation(operation="scan", anchor="click here", target_url=None)
        config = make_config()

        _, results = process_operation(html, op, config)

        assert len(results) >= 1
        assert results[0].status == ResultStatus.SUCCESS
        assert results[0].linked is True
        assert results[0].current_target_url == "/target.html"

    def test_scan_finds_unlinked_anchor(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Reports linked=False for unlinked text."""
        html = "<html><body><p>click here for info</p></body></html>"
        op = make_operation(operation="scan", anchor="click here", target_url=None)
        config = make_config()

        _, results = process_operation(html, op, config)

        assert len(results) >= 1
        assert results[0].status == ResultStatus.SUCCESS
        assert results[0].linked is False

    def test_scan_counts_occurrences(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Occurrence count is correct."""
        html = (
            "<html><body>"
            "<p>click here once</p>"
            "<p>click here twice</p>"
            "<p>click here thrice</p>"
            "</body></html>"
        )
        op = make_operation(operation="scan", anchor="click here", target_url=None)
        config = make_config()

        _, results = process_operation(html, op, config)

        assert len(results) == 3
        assert results[0].occurrence_count == 3


class TestMatchStrategy:
    """Tests for match strategy logic (tests 24-26)."""

    def test_match_strategy_first(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Only first occurrence is affected."""
        html = (
            "<html><body>"
            "<p>click here first</p>"
            "<p>click here second</p>"
            "</body></html>"
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/target.html",
        )
        config = make_config(match_strategy="first")

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        links = soup.find_all("a")
        assert len(links) == 1

    def test_match_strategy_all(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """All occurrences are affected."""
        html = (
            "<html><body>"
            "<p>click here first</p>"
            "<p>click here second</p>"
            "</body></html>"
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/target.html",
        )
        config = make_config(match_strategy="all")

        modified, results = process_operation(html, op, config)

        assert len(results) == 2
        assert all(r.status == ResultStatus.SUCCESS for r in results)
        soup = _parse(modified)
        links = soup.find_all("a")
        assert len(links) == 2

    def test_match_strategy_nth(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """Only Nth occurrence is affected."""
        html = (
            "<html><body>"
            "<p>click here first</p>"
            "<p>click here second</p>"
            "<p>click here third</p>"
            "</body></html>"
        )
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/target.html",
        )
        config = make_config(match_strategy="nth", match_n=2)

        modified, results = process_operation(html, op, config)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        soup = _parse(modified)
        links = soup.find_all("a")
        assert len(links) == 1
        paragraphs = soup.find_all("p")
        assert paragraphs[1].find("a") is not None
        assert paragraphs[0].find("a") is None
        assert paragraphs[2].find("a") is None


class TestDryRun:
    """Tests for dry-run mode (test 27)."""

    def test_dry_run_no_modification(
        self, make_operation: Callable[..., LinkOperation],
        make_config: Callable[..., AppConfig],
    ) -> None:
        """HTML unchanged, status is would_*."""
        html = "<html><body><p>click here for info</p></body></html>"
        op = make_operation(
            operation="add",
            anchor="click here",
            target_url="/target.html",
        )
        config = make_config(dry_run=True)

        modified, results = process_operation(html, op, config)

        assert modified == html
        assert len(results) == 1
        assert results[0].status == ResultStatus.WOULD_ADD
