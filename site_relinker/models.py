"""Data models, enums, and exceptions for site_relinker."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, model_validator


class Operation(str, Enum):
    """Link operation types."""

    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"
    SCAN = "scan"


class ScopeType(str, Enum):
    """Content scope types for targeting specific page areas."""

    ELEMENT_ID = "element_id"
    ABOVE = "above"
    BELOW = "below"
    WHOLE_BODY = "whole_body"


class IfLinkedPolicy(str, Enum):
    """Policy when an add operation finds the anchor already linked."""

    SKIP = "skip"
    ERROR = "error"
    REPLACE = "replace"


class MatchStrategy(str, Enum):
    """Strategy for selecting which occurrence(s) to operate on."""

    FIRST = "first"
    ALL = "all"
    ANY = "any"
    NTH = "nth"


class ResultStatus(str, Enum):
    """Status codes for operation results."""

    SUCCESS = "success"
    WOULD_ADD = "would_add"
    WOULD_REPLACE = "would_replace"
    WOULD_REMOVE = "would_remove"
    ALREADY_LINKED = "already_linked"
    NOT_FOUND = "not_found"
    SCOPE_NOT_FOUND = "scope_not_found"
    SKIPPED = "skipped"
    ERROR = "error"


class BackendType(str, Enum):
    """Backend types for processing HTML content."""

    STATIC = "static"
    WORDPRESS = "wordpress"


class SiteRelinkerError(Exception):
    """Base exception for site_relinker errors."""


class ConfigError(SiteRelinkerError):
    """Invalid configuration or arguments."""


class InputError(SiteRelinkerError):
    """Malformed CSV or missing files."""


class BackendError(SiteRelinkerError):
    """Filesystem or database failures."""


class ScopeDefinition(BaseModel):
    """Defines the content scope for an operation.

    Args:
        scope_type: The type of scope to apply.
        scope_value: The value for the scope (element ID or boundary string).
    """

    scope_type: ScopeType = ScopeType.WHOLE_BODY
    scope_value: str | None = None


class LinkOperation(BaseModel):
    """A single link operation parsed from a CSV row.

    Args:
        operation: The type of link operation to perform.
        url: The page URL or path to operate on.
        anchor: The anchor text to find.
        target_url: The link destination (required for add/replace).
        scope_type: Content scope type for targeting specific page areas.
        scope_value: Value for the scope (element ID or boundary string).
        if_linked: Per-row override for already-linked policy.
        max_occurrences: Per-row override for match strategy.
    """

    operation: Operation
    url: str
    anchor: str
    target_url: str | None = None
    scope_type: ScopeType = ScopeType.WHOLE_BODY
    scope_value: str | None = None
    if_linked: IfLinkedPolicy | None = None
    max_occurrences: str | None = None

    @model_validator(mode="after")
    def _validate_target_url_required(self) -> LinkOperation:
        """Ensure target_url is provided for add and replace operations."""
        if self.operation in (Operation.ADD, Operation.REPLACE):
            if not self.target_url:
                raise ValueError(
                    f"target_url is required for {self.operation.value} operations"
                )
        return self


class OperationResult(BaseModel):
    """Result of a single link operation.

    Args:
        url: The page URL that was operated on.
        operation: The operation that was performed.
        anchor: The anchor text that was searched for.
        status: The result status code.
        detail: Additional detail about the result.
        linked: Whether the anchor is currently linked.
        current_target_url: The current href if the anchor is linked.
        current_classes: CSS classes on the current link, if any.
        occurrence_count: Number of occurrences found.
    """

    url: str
    operation: Operation
    anchor: str
    status: ResultStatus
    detail: str = ""
    linked: bool = False
    current_target_url: str | None = None
    current_classes: str | None = None
    occurrence_count: int = 0


class ScanResult(OperationResult):
    """Result of a scan operation with scan-specific fields.

    Args:
        found: Whether the anchor text was found in the page.
    """

    found: bool = False


class StaticConfig(BaseModel):
    """Configuration for the static site backend.

    Args:
        web_root: Base directory for resolving URL paths to files.
        output_dir: Destination for modified files.
        extensions: File types to process.
        encoding: File encoding.
        copy_unchanged: Whether to copy unmodified files to output_dir.
    """

    web_root: Path
    output_dir: Path
    extensions: list[str] = ["html", "htm", "shtml"]
    encoding: str = "utf-8"
    copy_unchanged: bool = False


class WordPressConfig(BaseModel):
    """Configuration for the WordPress backend.

    Args:
        db_host: Database host.
        db_port: Database port.
        db_user: Database user.
        db_password: Database password.
        db_name: Database name.
        table_prefix: WordPress table prefix.
        post_types: Post types to process.
        post_statuses: Post statuses to process.
        backup_table: Whether to create a backup table before modification.
    """

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""
    table_prefix: str = "wp_"
    post_types: list[str] = ["post", "page"]
    post_statuses: list[str] = ["publish"]
    backup_table: bool = False


class AppConfig(BaseModel):
    """Global application configuration.

    Args:
        backend: The backend type (static or wordpress).
        domains: List of domains considered internal.
        dry_run: Whether to run in dry-run mode.
        link_classes: CSS classes to apply to inserted links.
        link_target: Target attribute for inserted links.
        if_linked: Default policy when anchor is already linked.
        match_strategy: Default match strategy.
        match_n: The N value when match_strategy is NTH.
        strict_text_only: Whether to match only within text nodes.
        static: Static site backend configuration.
        wordpress: WordPress backend configuration.
    """

    backend: BackendType
    domains: list[str]
    dry_run: bool = False
    link_classes: list[str] = []
    link_target: str | None = None
    if_linked: IfLinkedPolicy = IfLinkedPolicy.SKIP
    match_strategy: MatchStrategy = MatchStrategy.FIRST
    match_n: int | None = None
    strict_text_only: bool = True
    static: StaticConfig | None = None
    wordpress: WordPressConfig | None = None

    @model_validator(mode="after")
    def _validate_domains_not_empty(self) -> AppConfig:
        """Ensure at least one domain is provided."""
        if not self.domains:
            raise ValueError("At least one domain must be provided")
        return self

    @model_validator(mode="after")
    def _validate_nth_requires_n(self) -> AppConfig:
        """Ensure match_n is set when match_strategy is NTH."""
        if self.match_strategy == MatchStrategy.NTH:
            if self.match_n is None or self.match_n < 1:
                raise ValueError(
                    "match_n must be a positive integer "
                    "when match_strategy is 'nth'"
                )
        return self
