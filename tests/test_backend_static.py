"""Tests for site_relinker.backend_static — static site filesystem backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from site_relinker.backend_static import StaticSiteBackend
from site_relinker.models import (
    AppConfig,
    BackendError,
    BackendType,
    IfLinkedPolicy,
    LinkOperation,
    MatchStrategy,
    Operation,
    ResultStatus,
    StaticConfig,
)


def _make_static_config(
    tmp_path: Path,
    web_root: Path | None = None,
    output_dir: Path | None = None,
    extensions: list[str] | None = None,
    encoding: str = "utf-8",
    copy_unchanged: bool = False,
) -> AppConfig:
    root = web_root or tmp_path / "site"
    root.mkdir(parents=True, exist_ok=True)
    out = output_dir or tmp_path / "output"
    return AppConfig(
        backend=BackendType.STATIC,
        domains=["example.com"],
        dry_run=False,
        link_classes=[],
        if_linked=IfLinkedPolicy.SKIP,
        match_strategy=MatchStrategy.FIRST,
        strict_text_only=True,
        static=StaticConfig(
            web_root=root,
            output_dir=out,
            extensions=extensions or ["html", "htm", "shtml"],
            encoding=encoding,
            copy_unchanged=copy_unchanged,
        ),
    )


class TestResolveUrl:
    """Tests for URL-to-file resolution."""

    def test_resolve_url_to_file(self, tmp_path: Path) -> None:
        """URL path resolves to the correct filesystem path."""
        config = _make_static_config(tmp_path)
        assert config.static is not None
        page = config.static.web_root / "page.html"
        page.write_text("<html><body>test</body></html>")

        backend = StaticSiteBackend(config)
        result = backend.resolve_url("/page.html")

        assert result == page

    def test_resolve_url_missing_file(self, tmp_path: Path) -> None:
        """BackendError raised for missing file."""
        config = _make_static_config(tmp_path)
        backend = StaticSiteBackend(config)

        with pytest.raises(BackendError, match="not found"):
            backend.resolve_url("/missing.html")

    def test_resolve_url_wrong_extension(self, tmp_path: Path) -> None:
        """BackendError raised for non-allowed extension."""
        config = _make_static_config(tmp_path)
        assert config.static is not None
        page = config.static.web_root / "data.json"
        page.write_text("{}")

        backend = StaticSiteBackend(config)

        with pytest.raises(BackendError, match="extension"):
            backend.resolve_url("/data.json")


class TestProcessOperations:
    """Tests for operation processing."""

    def test_process_single_operation(self, tmp_path: Path) -> None:
        """File is read, modified, and written to output_dir."""
        config = _make_static_config(tmp_path)
        assert config.static is not None
        page = config.static.web_root / "page.html"
        page.write_text(
            "<html><body><p>Click here for info.</p></body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        results = backend.process_operations(ops)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS

        output_file = config.static.output_dir / "page.html"
        assert output_file.exists()
        content = output_file.read_text()
        assert "<a" in content
        assert "/target.html" in content

    def test_process_preserves_directory_structure(
        self, tmp_path: Path
    ) -> None:
        """Nested paths are mirrored in output directory."""
        config = _make_static_config(tmp_path)
        assert config.static is not None
        nested_dir = config.static.web_root / "help" / "topics"
        nested_dir.mkdir(parents=True)
        page = nested_dir / "faq.html"
        page.write_text(
            "<html><body><p>Click here for help.</p></body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/help/topics/faq.html",
                anchor="Click here",
                target_url="/answers.html",
            )
        ]
        results = backend.process_operations(ops)

        assert results[0].status == ResultStatus.SUCCESS
        output_file = config.static.output_dir / "help" / "topics" / "faq.html"
        assert output_file.exists()

    def test_process_groups_by_url(self, tmp_path: Path) -> None:
        """Multiple ops on same URL read file once and apply all."""
        config = _make_static_config(tmp_path, copy_unchanged=False)
        assert config.static is not None
        page = config.static.web_root / "page.html"
        page.write_text(
            "<html><body>"
            "<p>Click here for info.</p>"
            "<p>Read more about us.</p>"
            "</body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="Click here",
                target_url="/info.html",
            ),
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="Read more",
                target_url="/about.html",
            ),
        ]
        results = backend.process_operations(ops)

        assert len(results) == 2
        assert all(r.status == ResultStatus.SUCCESS for r in results)

        output_file = config.static.output_dir / "page.html"
        content = output_file.read_text()
        assert "/info.html" in content
        assert "/about.html" in content

    def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        """Output directory is auto-created."""
        out_dir = tmp_path / "deep" / "nested" / "output"
        config = _make_static_config(tmp_path, output_dir=out_dir)
        assert config.static is not None
        page = config.static.web_root / "page.html"
        page.write_text(
            "<html><body><p>Click here.</p></body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        backend.process_operations(ops)

        assert (out_dir / "page.html").exists()

    def test_copy_unchanged_flag_off(self, tmp_path: Path) -> None:
        """Unmodified files are not copied when flag is off."""
        config = _make_static_config(tmp_path, copy_unchanged=False)
        assert config.static is not None
        (config.static.web_root / "modified.html").write_text(
            "<html><body><p>Click here.</p></body></html>"
        )
        (config.static.web_root / "untouched.html").write_text(
            "<html><body><p>No changes here.</p></body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/modified.html",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        backend.process_operations(ops)

        assert (config.static.output_dir / "modified.html").exists()
        assert not (config.static.output_dir / "untouched.html").exists()

    def test_copy_unchanged_flag_on(self, tmp_path: Path) -> None:
        """Unmodified files are copied when flag is on."""
        config = _make_static_config(tmp_path, copy_unchanged=True)
        assert config.static is not None
        (config.static.web_root / "modified.html").write_text(
            "<html><body><p>Click here.</p></body></html>"
        )
        (config.static.web_root / "untouched.html").write_text(
            "<html><body><p>No changes here.</p></body></html>"
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/modified.html",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        backend.process_operations(ops)

        assert (config.static.output_dir / "modified.html").exists()
        assert (config.static.output_dir / "untouched.html").exists()

    def test_encoding_respected(self, tmp_path: Path) -> None:
        """Non-UTF-8 file is read correctly with specified encoding."""
        config = _make_static_config(tmp_path, encoding="latin-1")
        assert config.static is not None
        page = config.static.web_root / "page.html"
        page.write_text(
            "<html><body><p>Café click here.</p></body></html>",
            encoding="latin-1",
        )

        backend = StaticSiteBackend(config)
        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="click here",
                target_url="/target.html",
            )
        ]
        results = backend.process_operations(ops)

        assert results[0].status == ResultStatus.SUCCESS
        output_file = config.static.output_dir / "page.html"
        content = output_file.read_text(encoding="latin-1")
        assert "Café" in content
        assert "/target.html" in content
