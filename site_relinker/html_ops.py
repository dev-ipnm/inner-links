"""HTML scoping, anchor matching, and link manipulation operations."""

from __future__ import annotations

import re
from copy import copy
from typing import Any, Iterator

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString

from site_relinker.models import (
    OperationResult,
    ScopeDefinition,
    ScopeType,
)


class ContentScope:
    """Resolves a ScopeDefinition against a parsed HTML document.

    Returns the BeautifulSoup tag subtree to operate on, or None if the
    scope target was not found.

    Args:
        soup: The parsed BeautifulSoup document.
        scope: The scope definition to resolve.
    """

    def __init__(self, soup: BeautifulSoup, scope: ScopeDefinition) -> None:
        self._soup = soup
        self._scope = scope

    def resolve(self) -> Tag | None:
        """Resolve the scope and return the target element.

        Returns:
            The Tag subtree to operate on, or None if the scope target
            was not found.
        """
        if self._scope.scope_type == ScopeType.WHOLE_BODY:
            return self._resolve_whole_body()
        elif self._scope.scope_type == ScopeType.ELEMENT_ID:
            return self._resolve_element_id()
        elif self._scope.scope_type == ScopeType.ABOVE:
            return self._resolve_above()
        elif self._scope.scope_type == ScopeType.BELOW:
            return self._resolve_below()
        return None

    def _resolve_whole_body(self) -> Tag | None:
        """Return the entire body element."""
        body = self._soup.find("body")
        if isinstance(body, Tag):
            return body
        return None

    def _resolve_element_id(self) -> Tag | None:
        """Return the element with the specified id."""
        if not self._scope.scope_value:
            return None
        element = self._soup.find(id=self._scope.scope_value)
        if isinstance(element, Tag):
            return element
        return None

    def _resolve_above(self) -> Tag | None:
        """Return a synthetic container with content above the boundary."""
        return self._resolve_boundary(above=True)

    def _resolve_below(self) -> Tag | None:
        """Return a synthetic container with content below the boundary."""
        return self._resolve_boundary(above=False)

    def _resolve_boundary(self, *, above: bool) -> Tag | None:
        """Resolve an above/below boundary scope.

        Args:
            above: If True, collect content before the boundary.
                   If False, collect content after the boundary.

        Returns:
            A synthetic Tag containing the scoped content, or None.
        """
        boundary = self._scope.scope_value
        if not boundary:
            return None

        body = self._soup.find("body")
        if not isinstance(body, Tag):
            return None

        boundary_node = self._find_boundary_node(body, boundary)
        if boundary_node is None:
            return None

        wrapper = self._soup.new_tag("div")
        wrapper["data-scope"] = "synthetic"

        if above:
            self._collect_before(body, boundary_node, boundary, wrapper)
        else:
            self._collect_after(body, boundary_node, boundary, wrapper)

        return wrapper

    def _find_boundary_node(
        self, root: Tag, boundary: str
    ) -> NavigableString | None:
        """Find the first text node containing the boundary string.

        Args:
            root: The root tag to search within.
            boundary: The boundary string to find.

        Returns:
            The NavigableString containing the boundary, or None.
        """
        for node in root.descendants:
            if isinstance(node, NavigableString) and not isinstance(
                node, Comment
            ):
                if boundary in str(node):
                    return node
        return None

    def _collect_before(
        self,
        body: Tag,
        boundary_node: NavigableString,
        boundary: str,
        wrapper: Tag,
    ) -> None:
        """Collect content before the boundary into the wrapper.

        Args:
            body: The body element.
            boundary_node: The text node containing the boundary.
            boundary: The boundary string.
            wrapper: The synthetic wrapper to populate.
        """
        for child in body.children:
            element = child
            if not isinstance(element, (Tag, NavigableString)):
                continue
            if self._contains_node(element, boundary_node):
                partial = self._split_element_before(
                    element, boundary_node, boundary
                )
                if partial is not None:
                    wrapper.append(partial)
                break
            wrapper.append(copy(element))

    def _collect_after(
        self,
        body: Tag,
        boundary_node: NavigableString,
        boundary: str,
        wrapper: Tag,
    ) -> None:
        """Collect content after the boundary into the wrapper.

        Args:
            body: The body element.
            boundary_node: The text node containing the boundary.
            boundary: The boundary string.
            wrapper: The synthetic wrapper to populate.
        """
        found = False
        for child in body.children:
            element = child
            if not isinstance(element, (Tag, NavigableString)):
                continue
            if found:
                wrapper.append(copy(element))
            elif self._contains_node(element, boundary_node):
                partial = self._split_element_after(
                    element, boundary_node, boundary
                )
                if partial is not None:
                    wrapper.append(partial)
                found = True

    def _contains_node(
        self,
        element: Tag | NavigableString,
        target: NavigableString,
    ) -> bool:
        """Check if element contains the target node.

        Args:
            element: The element to check.
            target: The target NavigableString.

        Returns:
            True if the element is or contains the target.
        """
        if element is target:
            return True
        if isinstance(element, Tag):
            for desc in element.descendants:
                if desc is target:
                    return True
        return False

    def _split_element_before(
        self,
        element: Tag | NavigableString,
        boundary_node: NavigableString,
        boundary: str,
    ) -> Tag | NavigableString | None:
        """Extract the portion of an element before the boundary.

        Args:
            element: The element containing the boundary.
            boundary_node: The text node with the boundary.
            boundary: The boundary string.

        Returns:
            A copy of the element with only content before the boundary.
        """
        if element is boundary_node:
            text = str(element)
            idx = text.find(boundary)
            before_text = text[:idx]
            if before_text:
                return NavigableString(before_text)
            return None

        if isinstance(element, Tag):
            attrs: dict[str, Any] = dict(element.attrs)
            new_tag = self._soup.new_tag(element.name, attrs=attrs)
            for child in element.children:
                if not isinstance(child, (Tag, NavigableString)):
                    continue
                if self._contains_node(child, boundary_node):
                    partial = self._split_element_before(
                        child, boundary_node, boundary
                    )
                    if partial is not None:
                        new_tag.append(partial)
                    break
                new_tag.append(copy(child))
            return new_tag

        return None

    def _split_element_after(
        self,
        element: Tag | NavigableString,
        boundary_node: NavigableString,
        boundary: str,
    ) -> Tag | NavigableString | None:
        """Extract the portion of an element after the boundary.

        Args:
            element: The element containing the boundary.
            boundary_node: The text node with the boundary.
            boundary: The boundary string.

        Returns:
            A copy of the element with only content after the boundary.
        """
        if element is boundary_node:
            text = str(element)
            idx = text.find(boundary) + len(boundary)
            after_text = text[idx:]
            if after_text:
                return NavigableString(after_text)
            return None

        if isinstance(element, Tag):
            attrs: dict[str, Any] = dict(element.attrs)
            new_tag = self._soup.new_tag(element.name, attrs=attrs)
            found = False
            for child in element.children:
                if not isinstance(child, (Tag, NavigableString)):
                    continue
                if found:
                    new_tag.append(copy(child))
                elif self._contains_node(child, boundary_node):
                    partial = self._split_element_after(
                        child, boundary_node, boundary
                    )
                    if partial is not None:
                        new_tag.append(partial)
                    found = True
            return new_tag

        return None


class AnchorMatch:
    """Represents a found anchor text occurrence in the document.

    Args:
        text_node: The NavigableString containing the match.
        start: The start index within the text node.
        end: The end index within the text node.
    """

    def __init__(
        self, text_node: NavigableString, start: int, end: int
    ) -> None:
        self.text_node = text_node
        self.start = start
        self.end = end


class AnchorMatcher:
    """Finds anchor text occurrences in text nodes.

    Respects word boundaries, case-insensitivity, and strict-text-only
    mode (skips matches inside existing <a> tags).

    Args:
        scope: The Tag subtree to search within.
        anchor: The anchor text to find.
        strict_text_only: If True, skip text nodes inside <a> tags.
    """

    def __init__(
        self,
        scope: Tag,
        anchor: str,
        *,
        strict_text_only: bool = True,
    ) -> None:
        self._scope = scope
        self._anchor = anchor
        self._strict_text_only = strict_text_only
        self._pattern = self._build_pattern(anchor)

    @staticmethod
    def _build_pattern(anchor: str) -> re.Pattern[str]:
        """Build a word-boundary regex for the anchor text.

        Args:
            anchor: The anchor text to match.

        Returns:
            A compiled regex pattern.
        """
        escaped = re.escape(anchor)
        return re.compile(
            r"(?<![a-zA-Z0-9])" + escaped + r"(?![a-zA-Z0-9])",
            re.IGNORECASE,
        )

    def find_all(self) -> list[AnchorMatch]:
        """Find all matching occurrences within the scope.

        Returns:
            A list of AnchorMatch objects for each occurrence found.
        """
        matches: list[AnchorMatch] = []
        for text_node in self._iter_text_nodes():
            text = str(text_node)
            for m in self._pattern.finditer(text):
                matches.append(
                    AnchorMatch(text_node, m.start(), m.end())
                )
        return matches

    def _iter_text_nodes(self) -> Iterator[NavigableString]:
        """Iterate over text nodes in the scope.

        In strict_text_only mode, skips text nodes that are inside
        existing <a> tags.

        Yields:
            NavigableString instances to search within.
        """
        for node in self._scope.descendants:
            if not isinstance(node, NavigableString):
                continue
            if isinstance(node, Comment):
                continue
            if not str(node).strip():
                continue
            if self._strict_text_only and self._is_inside_link(node):
                continue
            yield node

    @staticmethod
    def _is_inside_link(node: NavigableString) -> bool:
        """Check if a text node is inside an <a> tag.

        Args:
            node: The text node to check.

        Returns:
            True if the node has an <a> ancestor.
        """
        parent = node.parent
        while parent is not None:
            if isinstance(parent, Tag) and parent.name == "a":
                return True
            parent = parent.parent
        return False
