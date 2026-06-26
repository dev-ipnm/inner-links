"""Data models, enums, and exceptions for site_relinker."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel


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
    """Defines the content scope for an operation."""

    scope_type: ScopeType = ScopeType.WHOLE_BODY
    scope_value: str | None = None


class LinkOperation(BaseModel):
    """A single link operation parsed from a CSV row."""

    operation: Operation
    url: str
    anchor: str
    target_url: str | None = None
    scope_type: ScopeType = ScopeType.WHOLE_BODY
    scope_value: str | None = None
    if_linked: IfLinkedPolicy | None = None
    max_occurrences: str | None = None


class OperationResult(BaseModel):
    """Result of a single link operation."""

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
    """Result of a scan operation with scan-specific fields."""

    found: bool = False


class StaticConfig(BaseModel):
    """Configuration for the static site backend."""

    web_root: Path
    output_dir: Path
    extensions: list[str] = ["html", "htm", "shtml"]
    encoding: str = "utf-8"
    copy_unchanged: bool = False


class WordPressConfig(BaseModel):
    """Configuration for the WordPress backend."""

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
    """Global application configuration."""

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
