"""Tests for site_relinker.cli — CLI entry point and orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from site_relinker.cli import build_parser, load_config, main
from site_relinker.models import (
    BackendType,
    IfLinkedPolicy,
    MatchStrategy,
)


class TestBuildParser:
    """Tests for argument parser construction."""

    def test_build_parser_static_mode(self) -> None:
        """All static-mode flags are parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "--mode", "static",
                "--csv", "ops.csv",
                "--domains", "example.com,www.example.com",
                "--web-root", "/var/www/html",
                "--output-dir", "/tmp/output",
                "--link-classes", "inner-link,batch-2024",
                "--match-strategy", "first",
                "--if-linked", "skip",
                "--dry-run",
                "--encoding", "latin-1",
                "--extensions", "html,php",
                "--copy-unchanged",
                "--cross-tag-match",
                "--link-target", "_blank",
            ]
        )

        assert args.mode == "static"
        assert args.csv == Path("ops.csv")
        assert args.domains == "example.com,www.example.com"
        assert args.web_root == Path("/var/www/html")
        assert args.output_dir == Path("/tmp/output")
        assert args.link_classes == "inner-link,batch-2024"
        assert args.match_strategy == "first"
        assert args.if_linked == "skip"
        assert args.dry_run is True
        assert args.encoding == "latin-1"
        assert args.extensions == "html,php"
        assert args.copy_unchanged is True
        assert args.cross_tag_match is True
        assert args.link_target == "_blank"

    def test_build_parser_wordpress_mode(self) -> None:
        """All WordPress-mode flags are parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "--mode", "wordpress",
                "--csv", "ops.csv",
                "--domains", "example.com",
                "--db-host", "db.example.com",
                "--db-port", "3307",
                "--db-user", "wp_admin",
                "--db-password", "secret",
                "--db-name", "wp_prod",
                "--table-prefix", "mysite_",
                "--post-types", "post,page,product",
                "--post-statuses", "publish,draft",
                "--backup-table",
            ]
        )

        assert args.mode == "wordpress"
        assert args.db_host == "db.example.com"
        assert args.db_port == 3307
        assert args.db_user == "wp_admin"
        assert args.db_password == "secret"
        assert args.db_name == "wp_prod"
        assert args.table_prefix == "mysite_"
        assert args.post_types == "post,page,product"
        assert args.post_statuses == "publish,draft"
        assert args.backup_table is True


class TestLoadConfig:
    """Tests for configuration loading and merging."""

    def test_load_config_from_args(self, tmp_path: Path) -> None:
        """CLI args produce a correct AppConfig."""
        web_root = tmp_path / "site"
        web_root.mkdir()
        output_dir = tmp_path / "output"

        parser = build_parser()
        args = parser.parse_args(
            [
                "--mode", "static",
                "--csv", str(tmp_path / "ops.csv"),
                "--domains", "example.com,www.example.com",
                "--web-root", str(web_root),
                "--output-dir", str(output_dir),
                "--link-classes", "inner-link",
                "--if-linked", "replace",
                "--match-strategy", "all",
                "--cross-tag-match",
            ]
        )

        config = load_config(args)

        assert config.backend == BackendType.STATIC
        assert config.domains == ["example.com", "www.example.com"]
        assert config.link_classes == ["inner-link"]
        assert config.if_linked == IfLinkedPolicy.REPLACE
        assert config.match_strategy == MatchStrategy.ALL
        assert config.strict_text_only is False
        assert config.static is not None
        assert config.static.web_root == web_root
        assert config.static.output_dir == output_dir

    def test_load_config_env_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables fill missing WordPress DB args."""
        monkeypatch.setenv("WP_DB_HOST", "db.example.com")
        monkeypatch.setenv("WP_DB_PORT", "3307")
        monkeypatch.setenv("WP_DB_USER", "admin")
        monkeypatch.setenv("WP_DB_PASSWORD", "secret123")
        monkeypatch.setenv("WP_DB_NAME", "wordpress")

        parser = build_parser()
        args = parser.parse_args(
            [
                "--mode", "wordpress",
                "--csv", str(tmp_path / "ops.csv"),
                "--domains", "example.com",
            ]
        )

        config = load_config(args)

        assert config.wordpress is not None
        assert config.wordpress.db_host == "db.example.com"
        assert config.wordpress.db_port == 3307
        assert config.wordpress.db_user == "admin"
        assert config.wordpress.db_password == "secret123"
        assert config.wordpress.db_name == "wordpress"


class TestMain:
    """Tests for the main orchestration function."""

    def test_main_dry_run_static(
        self,
        tmp_site: Path,
        csv_file: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dry-run on static site exits 0 and writes no output files."""
        csv_path = csv_file(  # type: ignore[operator]
            [
                {
                    "operation": "add",
                    "url": "/index.html",
                    "anchor": "Click here",
                    "target_url": "/target.html",
                }
            ]
        )
        output_dir = tmp_site.parent / "output"

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(tmp_site),
                "--output-dir", str(output_dir),
                "--dry-run",
            ],
        )

        exit_code = main()

        assert exit_code == 0
        output_files = list(output_dir.rglob("*.html"))
        assert len(output_files) == 0

    def test_main_execute_static(
        self,
        tmp_site: Path,
        csv_file: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Real execution creates modified output files with links."""
        csv_path = csv_file(  # type: ignore[operator]
            [
                {
                    "operation": "add",
                    "url": "/index.html",
                    "anchor": "Click here",
                    "target_url": "/target.html",
                }
            ]
        )
        output_dir = tmp_site.parent / "output"

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(tmp_site),
                "--output-dir", str(output_dir),
            ],
        )

        exit_code = main()

        assert exit_code == 0
        output_file = output_dir / "index.html"
        assert output_file.exists()
        content = output_file.read_text()
        assert "<a" in content
        assert "/target.html" in content

    def test_main_bad_csv_exit_code_1(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Exit code 1 on CSV with missing required columns."""
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("operation,url\nadd,/page.html\n")

        web_root = tmp_path / "site"
        web_root.mkdir()

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(web_root),
                "--output-dir", str(tmp_path / "output"),
            ],
        )

        exit_code = main()

        assert exit_code == 1

    def test_main_missing_web_root_exit_code_2(
        self,
        tmp_path: Path,
        csv_file: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Exit code 2 when web root directory does not exist."""
        csv_path = csv_file(  # type: ignore[operator]
            [
                {
                    "operation": "add",
                    "url": "/page.html",
                    "anchor": "Click here",
                    "target_url": "/target.html",
                }
            ]
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(tmp_path / "nonexistent"),
                "--output-dir", str(tmp_path / "output"),
            ],
        )

        exit_code = main()

        assert exit_code == 2
