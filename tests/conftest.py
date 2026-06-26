"""Shared fixtures for site_relinker tests."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from site_relinker.models import (
    AppConfig,
    BackendType,
    IfLinkedPolicy,
    LinkOperation,
    MatchStrategy,
    Operation,
    ScopeType,
    StaticConfig,
)


@pytest.fixture
def make_operation() -> Callable[..., LinkOperation]:
    """Factory fixture to create LinkOperation instances with sensible defaults."""

    def _make(
        operation: str = "add",
        url: str = "/page.html",
        anchor: str = "click here",
        target_url: str | None = "/target.html",
        scope_type: str | None = None,
        scope_value: str | None = None,
        if_linked: str | None = None,
        max_occurrences: str | None = None,
    ) -> LinkOperation:
        return LinkOperation(
            operation=Operation(operation),
            url=url,
            anchor=anchor,
            target_url=target_url,
            scope_type=ScopeType(scope_type) if scope_type else ScopeType.WHOLE_BODY,
            scope_value=scope_value,
            if_linked=IfLinkedPolicy(if_linked) if if_linked else None,
            max_occurrences=max_occurrences,
        )

    return _make


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., AppConfig]:
    """Factory fixture to create AppConfig instances with sensible defaults."""

    def _make(
        backend: str = "static",
        domains: list[str] | None = None,
        dry_run: bool = False,
        link_classes: list[str] | None = None,
        link_target: str | None = None,
        if_linked: str = "skip",
        match_strategy: str = "first",
        match_n: int | None = None,
        strict_text_only: bool = True,
        web_root: Path | None = None,
        output_dir: Path | None = None,
        extensions: list[str] | None = None,
        encoding: str = "utf-8",
        copy_unchanged: bool = False,
    ) -> AppConfig:
        static_config = StaticConfig(
            web_root=web_root or tmp_path / "site",
            output_dir=output_dir or tmp_path / "output",
            extensions=extensions or ["html", "htm", "shtml"],
            encoding=encoding,
            copy_unchanged=copy_unchanged,
        )
        return AppConfig(
            backend=BackendType(backend),
            domains=domains or ["example.com"],
            dry_run=dry_run,
            link_classes=link_classes or [],
            link_target=link_target,
            if_linked=IfLinkedPolicy(if_linked),
            match_strategy=MatchStrategy(match_strategy),
            match_n=match_n,
            strict_text_only=strict_text_only,
            static=static_config,
            wordpress=None,
        )

    return _make


@pytest.fixture
def sample_html() -> str:
    """Realistic HTML page with scoped content areas."""
    return """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<div id="header">
    <h1>Welcome to the Site</h1>
</div>
<div id="main-content">
    <p>This is the main content area. You can click here for more info.</p>
    <p>Another paragraph with some help text and details.</p>
    <h2>Section Divider</h2>
    <p>Content below the divider with a click here link opportunity.</p>
</div>
<div id="sidebar">
    <p>Sidebar content with click here text too.</p>
</div>
<div id="footer">
    <p>Footer content goes here.</p>
</div>
</body>
</html>"""


@pytest.fixture
def sample_html_with_links() -> str:
    """HTML with pre-existing internal and external links."""
    return """<!DOCTYPE html>
<html>
<head><title>Test Page With Links</title></head>
<body>
<div id="main-content">
    <p>Visit our <a href="/help.html" class="inner-link">help page</a>.</p>
    <p>Check out <a href="https://external.com/page">external site</a>.</p>
    <p>This click here text is not linked yet.</p>
    <p>Another <a href="/old-link.html" class="inner-link">click here</a>.</p>
</div>
</body>
</html>"""


@pytest.fixture
def tmp_site(tmp_path: Path) -> Path:
    """Create a temporary static site structure with sample HTML files."""
    site_root = tmp_path / "site"
    site_root.mkdir()

    index = site_root / "index.html"
    index.write_text(
        """<!DOCTYPE html>
<html>
<head><title>Home</title></head>
<body>
<div id="content">
    <p>Welcome to our site. Click here for more information.</p>
    <p>Visit the help page for assistance.</p>
</div>
</body>
</html>""",
        encoding="utf-8",
    )

    help_dir = site_root / "help"
    help_dir.mkdir()
    help_page = help_dir / "topic.html"
    help_page.write_text(
        """<!DOCTYPE html>
<html>
<head><title>Help Topic</title></head>
<body>
<div id="content">
    <p>This is a help topic. Click here for related articles.</p>
    <p>Find help on the <a href="/index.html">home page</a>.</p>
</div>
</body>
</html>""",
        encoding="utf-8",
    )

    about = site_root / "about.html"
    about.write_text(
        """<!DOCTYPE html>
<html>
<head><title>About</title></head>
<body>
<div id="content">
    <p>About our company. Click here to learn more.</p>
</div>
</body>
</html>""",
        encoding="utf-8",
    )

    return site_root


@pytest.fixture
def csv_file(tmp_path: Path) -> Callable[..., Path]:
    """Factory to create temporary CSV files with given rows."""

    def _make(
        rows: list[dict[str, Any]],
        filename: str = "operations.csv",
    ) -> Path:
        filepath = tmp_path / filename
        if not rows:
            filepath.write_text("")
            return filepath

        fieldnames = list(rows[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    return _make
