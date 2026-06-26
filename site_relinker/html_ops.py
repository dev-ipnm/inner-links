"""HTML scoping, anchor matching, and link manipulation operations."""

from __future__ import annotations

import logging
import random
import re
from copy import copy
from typing import Any, Iterator

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import AttributeValueList, NavigableString

from site_relinker.models import (
    AppConfig,
    IfLinkedPolicy,
    LinkOperation,
    MatchStrategy,
    Operation,
    OperationResult,
    ResultStatus,
    ScanResult,
    ScopeDefinition,
    ScopeType,
)
from site_relinker.url_utils import is_internal, normalize_to_relative

logger = logging.getLogger(__name__)


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


def _select_matches(
    matches: list[AnchorMatch],
    strategy: MatchStrategy,
    match_n: int | None,
) -> list[AnchorMatch]:
    """Select which matches to operate on based on the match strategy.

    Args:
        matches: All found matches.
        strategy: The match strategy to apply.
        match_n: The N value for NTH strategy.

    Returns:
        The filtered list of matches to operate on.
    """
    if not matches:
        return []

    if strategy == MatchStrategy.FIRST:
        return [matches[0]]
    elif strategy == MatchStrategy.ALL:
        return matches
    elif strategy == MatchStrategy.ANY:
        return [random.choice(matches)]
    elif strategy == MatchStrategy.NTH:
        if match_n is not None and 1 <= match_n <= len(matches):
            return [matches[match_n - 1]]
        return []
    return matches


def _get_match_strategy(
    operation: LinkOperation, config: AppConfig
) -> tuple[MatchStrategy, int | None]:
    """Determine the match strategy for an operation.

    Per-row max_occurrences overrides the global config. Default
    strategy depends on operation type.

    Args:
        operation: The link operation.
        config: The global app configuration.

    Returns:
        A tuple of (strategy, match_n).
    """
    if operation.max_occurrences is not None:
        val = operation.max_occurrences.strip().lower()
        if val in ("first", "all", "any"):
            return MatchStrategy(val), None
        try:
            n = int(val)
            if n >= 1:
                return MatchStrategy.NTH, n
        except ValueError:
            pass

    if config.match_strategy != MatchStrategy.FIRST:
        return config.match_strategy, config.match_n

    if operation.operation in (Operation.REMOVE, Operation.SCAN):
        return MatchStrategy.ALL, None
    return config.match_strategy, config.match_n


def _get_if_linked_policy(
    operation: LinkOperation, config: AppConfig
) -> IfLinkedPolicy:
    """Determine the if-linked policy for an operation.

    Args:
        operation: The link operation (may have per-row override).
        config: The global app configuration.

    Returns:
        The IfLinkedPolicy to apply.
    """
    if operation.if_linked is not None:
        return operation.if_linked
    return config.if_linked


class LinkManipulator:
    """Stateless operations for adding, replacing, removing, and scanning links.

    Args:
        soup: The parsed BeautifulSoup document.
        config: The global app configuration.
    """

    def __init__(self, soup: BeautifulSoup, config: AppConfig) -> None:
        self._soup = soup
        self._config = config

    def add_link(
        self,
        scope: Tag,
        anchor: str,
        target_url: str,
        operation: LinkOperation,
    ) -> list[OperationResult]:
        """Add a link around anchor text occurrences.

        Args:
            scope: The scoped subtree to operate within.
            anchor: The anchor text to wrap.
            target_url: The link destination.
            operation: The original link operation for context.

        Returns:
            A list of OperationResult for each match processed.
        """
        matcher = AnchorMatcher(
            scope, anchor, strict_text_only=self._config.strict_text_only
        )
        all_matches = matcher.find_all()
        strategy, match_n = _get_match_strategy(operation, self._config)
        selected = _select_matches(all_matches, strategy, match_n)

        if not all_matches:
            return [
                OperationResult(
                    url=operation.url,
                    operation=Operation.ADD,
                    anchor=anchor,
                    status=ResultStatus.NOT_FOUND,
                    detail="Anchor text not found in scope",
                    occurrence_count=0,
                )
            ]

        results: list[OperationResult] = []
        policy = _get_if_linked_policy(operation, self._config)

        for match in selected:
            result = self._add_single(
                match, anchor, target_url, operation.url, policy
            )
            results.append(result)

        return results

    def _add_single(
        self,
        match: AnchorMatch,
        anchor: str,
        target_url: str,
        page_url: str,
        policy: IfLinkedPolicy,
    ) -> OperationResult:
        """Add a link around a single match.

        Args:
            match: The anchor match to wrap.
            anchor: The anchor text.
            target_url: The link destination.
            page_url: The page URL for result reporting.
            policy: The if-linked policy.

        Returns:
            An OperationResult describing what happened.
        """
        parent = match.text_node.parent
        if isinstance(parent, Tag) and parent.name == "a":
            return self._handle_already_linked(
                parent, anchor, target_url, page_url, policy
            )

        if self._config.dry_run:
            return OperationResult(
                url=page_url,
                operation=Operation.ADD,
                anchor=anchor,
                status=ResultStatus.WOULD_ADD,
                detail=f"Would add link to {target_url}",
                occurrence_count=1,
            )

        href = self._resolve_href(target_url)
        new_tag = self._build_link_tag(href, target_url)
        matched_text = str(match.text_node)[match.start : match.end]
        new_tag.string = matched_text

        text = str(match.text_node)
        before = text[: match.start]
        after = text[match.end :]

        parent_tag = match.text_node.parent
        if parent_tag is None:
            return OperationResult(
                url=page_url,
                operation=Operation.ADD,
                anchor=anchor,
                status=ResultStatus.ERROR,
                detail="Text node has no parent element",
                occurrence_count=1,
            )

        idx = list(parent_tag.children).index(match.text_node)
        match.text_node.extract()

        parts: list[NavigableString | Tag] = []
        if before:
            parts.append(NavigableString(before))
        parts.append(new_tag)
        if after:
            parts.append(NavigableString(after))

        for i, part in enumerate(reversed(parts)):
            if idx < len(list(parent_tag.children)):
                ref = list(parent_tag.children)[idx]
                ref.insert_before(part)
            else:
                parent_tag.append(part)

        return OperationResult(
            url=page_url,
            operation=Operation.ADD,
            anchor=anchor,
            status=ResultStatus.SUCCESS,
            detail=f"Added link to {href}",
            occurrence_count=1,
        )

    def _handle_already_linked(
        self,
        link_tag: Tag,
        anchor: str,
        target_url: str,
        page_url: str,
        policy: IfLinkedPolicy,
    ) -> OperationResult:
        """Handle the case where anchor text is already inside an <a> tag.

        Args:
            link_tag: The existing <a> tag.
            anchor: The anchor text.
            target_url: The intended link destination.
            page_url: The page URL for result reporting.
            policy: The if-linked policy to apply.

        Returns:
            An OperationResult describing what happened.
        """
        current_href = str(link_tag.get("href", ""))
        cls_attr = link_tag.get("class")
        current_classes = " ".join(cls_attr) if isinstance(cls_attr, list) else ""

        if policy == IfLinkedPolicy.SKIP:
            return OperationResult(
                url=page_url,
                operation=Operation.ADD,
                anchor=anchor,
                status=ResultStatus.ALREADY_LINKED,
                detail=f"Already linked to {current_href}",
                linked=True,
                current_target_url=str(current_href),
                current_classes=current_classes,
                occurrence_count=1,
            )
        elif policy == IfLinkedPolicy.ERROR:
            return OperationResult(
                url=page_url,
                operation=Operation.ADD,
                anchor=anchor,
                status=ResultStatus.ERROR,
                detail=f"Anchor already linked to {current_href}",
                linked=True,
                current_target_url=str(current_href),
                current_classes=current_classes,
                occurrence_count=1,
            )
        else:
            if self._config.dry_run:
                return OperationResult(
                    url=page_url,
                    operation=Operation.ADD,
                    anchor=anchor,
                    status=ResultStatus.WOULD_REPLACE,
                    detail=(
                        f"Would replace {current_href} with {target_url}"
                    ),
                    linked=True,
                    current_target_url=str(current_href),
                    occurrence_count=1,
                )

            href = self._resolve_href(target_url)
            link_tag["href"] = href
            return OperationResult(
                url=page_url,
                operation=Operation.ADD,
                anchor=anchor,
                status=ResultStatus.SUCCESS,
                detail=f"Replaced existing link with {href}",
                linked=True,
                current_target_url=href,
                occurrence_count=1,
            )

    def replace_link(
        self,
        scope: Tag,
        anchor: str,
        target_url: str,
        operation: LinkOperation,
    ) -> list[OperationResult]:
        """Replace the href of an existing link around anchor text.

        Args:
            scope: The scoped subtree to operate within.
            anchor: The anchor text to find.
            target_url: The new link destination.
            operation: The original link operation for context.

        Returns:
            A list of OperationResult for each match processed.
        """
        matcher = AnchorMatcher(
            scope, anchor, strict_text_only=False
        )
        all_matches = matcher.find_all()
        strategy, match_n = _get_match_strategy(operation, self._config)
        selected = _select_matches(all_matches, strategy, match_n)

        if not all_matches:
            return [
                OperationResult(
                    url=operation.url,
                    operation=Operation.REPLACE,
                    anchor=anchor,
                    status=ResultStatus.NOT_FOUND,
                    detail="Anchor text not found in scope",
                    occurrence_count=0,
                )
            ]

        results: list[OperationResult] = []

        for match in selected:
            parent = match.text_node.parent
            if not isinstance(parent, Tag) or parent.name != "a":
                results.append(
                    OperationResult(
                        url=operation.url,
                        operation=Operation.REPLACE,
                        anchor=anchor,
                        status=ResultStatus.ERROR,
                        detail="Anchor text is not inside a link",
                        occurrence_count=1,
                    )
                )
                continue

            current_href = str(parent.get("href", ""))

            if self._config.dry_run:
                results.append(
                    OperationResult(
                        url=operation.url,
                        operation=Operation.REPLACE,
                        anchor=anchor,
                        status=ResultStatus.WOULD_REPLACE,
                        detail=(
                            f"Would replace {current_href} "
                            f"with {target_url}"
                        ),
                        linked=True,
                        current_target_url=current_href,
                        occurrence_count=1,
                    )
                )
                continue

            href = self._resolve_href(target_url)
            parent["href"] = href
            results.append(
                OperationResult(
                    url=operation.url,
                    operation=Operation.REPLACE,
                    anchor=anchor,
                    status=ResultStatus.SUCCESS,
                    detail=f"Replaced href with {href}",
                    linked=True,
                    current_target_url=href,
                    occurrence_count=1,
                )
            )

        return results

    def remove_link(
        self,
        scope: Tag,
        anchor: str,
        operation: LinkOperation,
    ) -> list[OperationResult]:
        """Remove a link from around anchor text, leaving the text.

        Args:
            scope: The scoped subtree to operate within.
            anchor: The anchor text to find.
            operation: The original link operation for context.

        Returns:
            A list of OperationResult for each match processed.
        """
        matcher = AnchorMatcher(
            scope, anchor, strict_text_only=False
        )
        all_matches = matcher.find_all()
        strategy, match_n = _get_match_strategy(operation, self._config)
        selected = _select_matches(all_matches, strategy, match_n)

        if not all_matches:
            return [
                OperationResult(
                    url=operation.url,
                    operation=Operation.REMOVE,
                    anchor=anchor,
                    status=ResultStatus.NOT_FOUND,
                    detail="Anchor text not found in scope",
                    occurrence_count=0,
                )
            ]

        results: list[OperationResult] = []
        link_classes = self._config.link_classes

        for match in selected:
            parent = match.text_node.parent
            if not isinstance(parent, Tag) or parent.name != "a":
                results.append(
                    OperationResult(
                        url=operation.url,
                        operation=Operation.REMOVE,
                        anchor=anchor,
                        status=ResultStatus.SKIPPED,
                        detail="Anchor text is not inside a link",
                        occurrence_count=1,
                    )
                )
                continue

            cls_raw = parent.get("class")
            tag_classes = set(cls_raw) if isinstance(cls_raw, list) else set()

            if link_classes and not tag_classes.intersection(link_classes):
                results.append(
                    OperationResult(
                        url=operation.url,
                        operation=Operation.REMOVE,
                        anchor=anchor,
                        status=ResultStatus.SKIPPED,
                        detail=(
                            "Link does not have any of the "
                            "specified classes"
                        ),
                        linked=True,
                        current_classes=" ".join(tag_classes),
                        occurrence_count=1,
                    )
                )
                continue

            if self._config.dry_run:
                results.append(
                    OperationResult(
                        url=operation.url,
                        operation=Operation.REMOVE,
                        anchor=anchor,
                        status=ResultStatus.WOULD_REMOVE,
                        detail=f"Would remove link to {parent.get('href', '')}",
                        linked=True,
                        occurrence_count=1,
                    )
                )
                continue

            parent.unwrap()
            results.append(
                OperationResult(
                    url=operation.url,
                    operation=Operation.REMOVE,
                    anchor=anchor,
                    status=ResultStatus.SUCCESS,
                    detail="Removed link, text preserved",
                    occurrence_count=1,
                )
            )

        return results

    def scan_link(
        self,
        scope: Tag,
        anchor: str,
        operation: LinkOperation,
    ) -> list[ScanResult]:
        """Scan for anchor text and report its link status.

        Args:
            scope: The scoped subtree to search within.
            anchor: The anchor text to find.
            operation: The original link operation for context.

        Returns:
            A list of ScanResult for each match found.
        """
        matcher = AnchorMatcher(
            scope, anchor, strict_text_only=False
        )
        all_matches = matcher.find_all()
        strategy, match_n = _get_match_strategy(operation, self._config)
        selected = _select_matches(all_matches, strategy, match_n)

        if not all_matches:
            return [
                ScanResult(
                    url=operation.url,
                    operation=Operation.SCAN,
                    anchor=anchor,
                    status=ResultStatus.SUCCESS,
                    found=False,
                    linked=False,
                    occurrence_count=0,
                )
            ]

        results: list[ScanResult] = []

        for match in selected:
            parent = match.text_node.parent
            is_linked = isinstance(parent, Tag) and parent.name == "a"
            current_href: str | None = None
            current_cls: str | None = None

            if is_linked and isinstance(parent, Tag):
                current_href = str(parent.get("href", ""))
                scan_cls = parent.get("class")
                current_cls = " ".join(scan_cls) if isinstance(scan_cls, list) else ""

            results.append(
                ScanResult(
                    url=operation.url,
                    operation=Operation.SCAN,
                    anchor=anchor,
                    status=ResultStatus.SUCCESS,
                    found=True,
                    linked=is_linked,
                    current_target_url=current_href,
                    current_classes=current_cls,
                    occurrence_count=len(all_matches),
                )
            )

        return results

    def _resolve_href(self, target_url: str) -> str:
        """Resolve a target URL to the appropriate href value.

        Args:
            target_url: The target URL.

        Returns:
            The href string to use in the link tag.
        """
        if is_internal(target_url, self._config.domains):
            try:
                return normalize_to_relative(
                    target_url, self._config.domains
                )
            except ValueError:
                return target_url
        return target_url

    def _build_link_tag(self, href: str, original_url: str) -> Tag:
        """Build an <a> tag with appropriate attributes.

        Args:
            href: The resolved href value.
            original_url: The original target URL for internal/external check.

        Returns:
            A new <a> Tag with href, classes, rel, and target set.
        """
        new_tag = self._soup.new_tag("a", href=href)

        if self._config.link_classes:
            new_tag["class"] = AttributeValueList(self._config.link_classes)

        if not is_internal(original_url, self._config.domains):
            new_tag["rel"] = "noopener noreferrer"

        if self._config.link_target:
            new_tag["target"] = self._config.link_target

        return new_tag


def process_operation(
    html: str, operation: LinkOperation, config: AppConfig
) -> tuple[str, list[OperationResult]]:
    """Process a single link operation on an HTML document.

    Parse HTML, resolve scope, match anchor, manipulate link, and
    serialize back.

    Args:
        html: The HTML content to process.
        operation: The link operation to apply.
        config: The global app configuration.

    Returns:
        A tuple of (modified_html, results). In dry-run mode, returns
        (original_html, results) with appropriate status.
    """
    soup = BeautifulSoup(html, "lxml")

    scope_def = ScopeDefinition(
        scope_type=operation.scope_type,
        scope_value=operation.scope_value,
    )
    scope = ContentScope(soup, scope_def).resolve()

    if scope is None:
        result = OperationResult(
            url=operation.url,
            operation=operation.operation,
            anchor=operation.anchor,
            status=ResultStatus.SCOPE_NOT_FOUND,
            detail=f"Scope not found: {operation.scope_type.value}"
            + (f"={operation.scope_value}" if operation.scope_value else ""),
        )
        return html, [result]

    manipulator = LinkManipulator(soup, config)
    results: list[OperationResult]

    if operation.operation == Operation.ADD:
        results = manipulator.add_link(
            scope,
            operation.anchor,
            operation.target_url or "",
            operation,
        )
    elif operation.operation == Operation.REPLACE:
        results = manipulator.replace_link(
            scope,
            operation.anchor,
            operation.target_url or "",
            operation,
        )
    elif operation.operation == Operation.REMOVE:
        results = manipulator.remove_link(
            scope, operation.anchor, operation
        )
    elif operation.operation == Operation.SCAN:
        scan_results = manipulator.scan_link(
            scope, operation.anchor, operation
        )
        results = list(scan_results)
    else:
        results = [
            OperationResult(
                url=operation.url,
                operation=operation.operation,
                anchor=operation.anchor,
                status=ResultStatus.ERROR,
                detail=f"Unknown operation: {operation.operation.value}",
            )
        ]

    if config.dry_run:
        return html, results

    modified_html = str(soup)
    return modified_html, results
