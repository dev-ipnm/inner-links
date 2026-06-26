"""CLI entry point and orchestration for site_relinker."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from site_relinker.backend_static import StaticSiteBackend
from site_relinker.backend_wordpress import WordPressBackend
from site_relinker.csv_io import parse_csv, write_dry_run_report, write_scan_results
from site_relinker.models import (
    AppConfig,
    BackendError,
    BackendType,
    ConfigError,
    IfLinkedPolicy,
    InputError,
    MatchStrategy,
    ScanResult,
    StaticConfig,
    WordPressConfig,
)
from site_relinker.reporter import Reporter
from site_relinker.url_utils import sanitize_classes

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Define all CLI arguments for site-relinker.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="site-relinker",
        description=(
            "Batch manipulation of internal links across "
            "static HTML sites and WordPress installations."
        ),
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=["static", "wordpress"],
        help="Backend mode: 'static' or 'wordpress'",
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Path to the CSV file containing link operations",
    )
    parser.add_argument(
        "--domains",
        required=True,
        help="Comma-separated list of internal domains",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without modifying anything",
    )
    parser.add_argument(
        "--link-classes",
        default="",
        help="Comma-separated CSS classes for inserted links",
    )
    parser.add_argument(
        "--link-target",
        default=None,
        help="Target attribute for inserted links (e.g. '_blank')",
    )
    parser.add_argument(
        "--if-linked",
        default="skip",
        choices=["skip", "error", "replace"],
        help="Policy when anchor is already linked (default: skip)",
    )
    parser.add_argument(
        "--match-strategy",
        default="first",
        help="Match strategy: first, all, any, or N (positive integer)",
    )
    parser.add_argument(
        "--cross-tag-match",
        action="store_true",
        default=False,
        help="Enable matching across inline child elements",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for scan results or dry-run report",
    )

    static = parser.add_argument_group("static backend")
    static.add_argument(
        "--web-root",
        type=Path,
        default=None,
        help="Base directory for resolving URL paths",
    )
    static.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory for modified files",
    )
    static.add_argument(
        "--extensions",
        default="html,htm,shtml",
        help="Comma-separated file extensions (default: html,htm,shtml)",
    )
    static.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding (default: utf-8)",
    )
    static.add_argument(
        "--copy-unchanged",
        action="store_true",
        default=False,
        help="Copy unmodified files to output directory",
    )

    wp = parser.add_argument_group("wordpress backend")
    wp.add_argument(
        "--db-host", default=None, help="Database host (or WP_DB_HOST)"
    )
    wp.add_argument(
        "--db-port",
        type=int,
        default=None,
        help="Database port (or WP_DB_PORT, default: 3306)",
    )
    wp.add_argument(
        "--db-user", default=None, help="Database user (or WP_DB_USER)"
    )
    wp.add_argument(
        "--db-password",
        default=None,
        help="Database password (or WP_DB_PASSWORD)",
    )
    wp.add_argument(
        "--db-name", default=None, help="Database name (or WP_DB_NAME)"
    )
    wp.add_argument(
        "--table-prefix",
        default="wp_",
        help="WordPress table prefix (default: wp_)",
    )
    wp.add_argument(
        "--post-types",
        default="post,page",
        help="Comma-separated post types (default: post,page)",
    )
    wp.add_argument(
        "--post-statuses",
        default="publish",
        help="Comma-separated post statuses (default: publish)",
    )
    wp.add_argument(
        "--backup-table",
        action="store_true",
        default=False,
        help="Create backup table before modifying posts",
    )

    return parser


def load_config(args: argparse.Namespace) -> AppConfig:
    """Merge CLI arguments with environment variables and build AppConfig.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A validated AppConfig instance.

    Raises:
        ConfigError: If required arguments are missing or invalid.
    """
    load_dotenv()

    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    link_classes = [
        c.strip() for c in args.link_classes.split(",") if c.strip()
    ]

    if link_classes:
        sanitize_classes(link_classes)

    strategy_str: str = args.match_strategy
    match_n: int | None = None
    if strategy_str.isdigit():
        match_strategy = MatchStrategy.NTH
        match_n = int(strategy_str)
    else:
        try:
            match_strategy = MatchStrategy(strategy_str)
        except ValueError:
            raise ConfigError(
                f"Invalid match strategy: {strategy_str!r}. "
                "Use first, all, any, or a positive integer."
            ) from None

    strict_text_only = not args.cross_tag_match
    backend_type = BackendType(args.mode)

    static_config: StaticConfig | None = None
    wp_config: WordPressConfig | None = None

    if backend_type == BackendType.STATIC:
        if args.web_root is None:
            raise ConfigError(
                "--web-root is required for static mode"
            )
        if args.output_dir is None:
            raise ConfigError(
                "--output-dir is required for static mode"
            )

        extensions = [e.strip() for e in args.extensions.split(",")]
        static_config = StaticConfig(
            web_root=args.web_root,
            output_dir=args.output_dir,
            extensions=extensions,
            encoding=args.encoding,
            copy_unchanged=args.copy_unchanged,
        )
    else:
        db_host = args.db_host or os.environ.get(
            "WP_DB_HOST", "localhost"
        )
        db_port = args.db_port or int(
            os.environ.get("WP_DB_PORT", "3306")
        )
        db_user = args.db_user or os.environ.get("WP_DB_USER", "")
        db_password = args.db_password or os.environ.get(
            "WP_DB_PASSWORD", ""
        )
        db_name = args.db_name or os.environ.get("WP_DB_NAME", "")

        post_types = [t.strip() for t in args.post_types.split(",")]
        post_statuses = [
            s.strip() for s in args.post_statuses.split(",")
        ]

        wp_config = WordPressConfig(
            db_host=db_host,
            db_port=db_port,
            db_user=db_user,
            db_password=db_password,
            db_name=db_name,
            table_prefix=args.table_prefix,
            post_types=post_types,
            post_statuses=post_statuses,
            backup_table=args.backup_table,
        )

    return AppConfig(
        backend=backend_type,
        domains=domains,
        dry_run=args.dry_run,
        link_classes=link_classes,
        link_target=args.link_target,
        if_linked=IfLinkedPolicy(args.if_linked),
        match_strategy=match_strategy,
        match_n=match_n,
        strict_text_only=strict_text_only,
        static=static_config,
        wordpress=wp_config,
    )


def main() -> int:
    """Parse args, load config, process operations, and report results.

    Returns:
        Exit code: 0 on success, 1 on input/config error, 2 on runtime error.
    """
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.dry_run else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    try:
        config = load_config(args)
    except (ConfigError, ValidationError) as e:
        logger.error("Configuration error: %s", e)
        return 1

    try:
        operations = parse_csv(args.csv)
    except InputError as e:
        logger.error("Input error: %s", e)
        return 1

    try:
        if config.backend == BackendType.STATIC:
            results = StaticSiteBackend(config).process_operations(
                operations
            )
        else:
            results = WordPressBackend(config).process_operations(
                operations
            )
    except BackendError as e:
        logger.error("Backend error: %s", e)
        return 2

    scan_results = [r for r in results if isinstance(r, ScanResult)]
    if scan_results:
        write_scan_results(scan_results, args.output)

    if config.dry_run and not scan_results:
        write_dry_run_report(results, args.output)

    reporter = Reporter(results)
    sys.stderr.write(reporter.summary() + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
