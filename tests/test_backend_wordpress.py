"""Tests for site_relinker.backend_wordpress — WordPress MySQL backend.

All database interactions are mocked with unittest.mock.patch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from site_relinker.backend_wordpress import WordPressBackend
from site_relinker.models import (
    AppConfig,
    BackendError,
    BackendType,
    IfLinkedPolicy,
    LinkOperation,
    MatchStrategy,
    Operation,
    ResultStatus,
    WordPressConfig,
)


def _make_wp_config(
    permalink_structure: str = "/%postname%/",
    post_types: list[str] | None = None,
    post_statuses: list[str] | None = None,
    backup_table: bool = False,
) -> AppConfig:
    return AppConfig(
        backend=BackendType.WORDPRESS,
        domains=["example.com"],
        dry_run=False,
        link_classes=[],
        if_linked=IfLinkedPolicy.SKIP,
        match_strategy=MatchStrategy.FIRST,
        strict_text_only=True,
        wordpress=WordPressConfig(
            db_host="localhost",
            db_port=3306,
            db_user="wp_user",
            db_password="wp_pass",
            db_name="wp_db",
            table_prefix="wp_",
            post_types=post_types or ["post", "page"],
            post_statuses=post_statuses or ["publish"],
            backup_table=backup_table,
        ),
    )


def _mock_cursor(
    query_results: dict[str, list[dict[str, Any]]] | None = None,
) -> MagicMock:
    """Create a mock cursor that returns results based on query substrings."""
    cursor = MagicMock()
    results_map = query_results or {}
    call_results: list[dict[str, Any]] = []

    def execute_side_effect(query: str, *args: Any) -> None:
        nonlocal call_results
        call_results = []
        for key, rows in results_map.items():
            if key.lower() in query.lower():
                call_results = rows
                return

    def fetchone_side_effect() -> dict[str, Any] | None:
        return call_results[0] if call_results else None

    def fetchall_side_effect() -> list[dict[str, Any]]:
        return call_results

    cursor.execute.side_effect = execute_side_effect
    cursor.fetchone.side_effect = fetchone_side_effect
    cursor.fetchall.side_effect = fetchall_side_effect
    return cursor


def _create_backend(
    config: AppConfig,
    permalink_structure: str = "/%postname%/",
    posts: list[dict[str, Any]] | None = None,
) -> tuple[WordPressBackend, MagicMock]:
    """Create a WordPressBackend with a mocked DB connection."""
    posts = posts or [
        {"ID": 1, "post_name": "hello-world", "post_date": "2024-01-01"},
        {"ID": 2, "post_name": "about", "post_date": "2024-01-02"},
        {"ID": 3, "post_name": "contact", "post_date": "2024-01-03"},
    ]

    mock_conn = MagicMock()
    cursor = _mock_cursor(
        {
            "permalink_structure": [
                {"option_value": permalink_structure}
            ],
            "post_type": posts,
        }
    )
    mock_conn.cursor.return_value = cursor

    with patch("site_relinker.backend_wordpress.pymysql") as mock_pymysql:
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = MagicMock()
        backend = WordPressBackend(config)

    return backend, mock_conn


class TestReadPermalinkStructure:
    """Tests for reading permalink structure from wp_options."""

    def test_read_permalink_structure(self) -> None:
        """Reads permalink_structure from wp_options mock."""
        config = _make_wp_config(permalink_structure="/%postname%/")
        backend, _ = _create_backend(config, "/%postname%/")

        assert backend._permalink_structure == "/%postname%/"


class TestBuildSlugMap:
    """Tests for building the slug-to-post-ID map."""

    def test_build_slug_map_postname(self) -> None:
        """/%postname%/ pattern builds correct slug map."""
        config = _make_wp_config(permalink_structure="/%postname%/")
        backend, _ = _create_backend(config, "/%postname%/")

        assert backend._slug_map == {
            "hello-world": 1,
            "about": 2,
            "contact": 3,
        }

    def test_build_slug_map_year_month(self) -> None:
        """/%year%/%monthnum%/%postname%/ pattern builds correct slug map."""
        config = _make_wp_config(
            permalink_structure="/%year%/%monthnum%/%postname%/"
        )
        backend, _ = _create_backend(
            config, "/%year%/%monthnum%/%postname%/"
        )

        assert backend._slug_map == {
            "hello-world": 1,
            "about": 2,
            "contact": 3,
        }


class TestResolveUrl:
    """Tests for URL-to-post-ID resolution."""

    def test_resolve_url_to_post_id(self) -> None:
        """URL resolves to correct post_id."""
        config = _make_wp_config()
        backend, _ = _create_backend(config)

        assert backend.resolve_url("/hello-world/") == 1
        assert backend.resolve_url("/about/") == 2

    def test_resolve_url_not_found(self) -> None:
        """BackendError raised for unknown URL."""
        config = _make_wp_config()
        backend, _ = _create_backend(config)

        with pytest.raises(BackendError, match="No post found"):
            backend.resolve_url("/nonexistent/")


class TestProcessOperations:
    """Tests for operation processing with transactions."""

    def test_process_operations_with_transaction(self) -> None:
        """Commit is called on success."""
        config = _make_wp_config()
        backend, mock_conn = _create_backend(config)

        content_cursor = MagicMock()
        content_cursor.fetchone.return_value = {
            "post_content": (
                "<html><body><p>Click here for info.</p></body></html>"
            )
        }
        update_cursor = MagicMock()

        call_count = 0

        def cursor_factory() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return content_cursor
            return update_cursor

        mock_conn.cursor.side_effect = cursor_factory

        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/hello-world/",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        results = backend.process_operations(ops)

        assert len(results) == 1
        assert results[0].status == ResultStatus.SUCCESS
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

    def test_process_operations_rollback_on_error(self) -> None:
        """Rollback is called on database failure."""
        config = _make_wp_config()
        backend, mock_conn = _create_backend(config)

        content_cursor = MagicMock()
        content_cursor.fetchone.return_value = {
            "post_content": (
                "<html><body><p>Click here for info.</p></body></html>"
            )
        }

        error_cursor = MagicMock()
        error_cursor.execute.side_effect = Exception("DB write error")

        call_count = 0

        def cursor_factory() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return content_cursor
            return error_cursor

        mock_conn.cursor.side_effect = cursor_factory

        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/hello-world/",
                anchor="Click here",
                target_url="/target.html",
            )
        ]

        with pytest.raises(BackendError, match="rolled back"):
            backend.process_operations(ops)

        mock_conn.rollback.assert_called_once()


class TestBackupTable:
    """Tests for backup table creation."""

    def test_backup_table_creation(self) -> None:
        """Backup rows are dumped before modification."""
        config = _make_wp_config(backup_table=True)
        backend, mock_conn = _create_backend(config)

        content_cursor = MagicMock()
        content_cursor.fetchone.return_value = {
            "post_content": (
                "<html><body><p>Click here for info.</p></body></html>"
            )
        }
        work_cursor = MagicMock()

        call_count = 0

        def cursor_factory() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return content_cursor
            return work_cursor

        mock_conn.cursor.side_effect = cursor_factory

        ops = [
            LinkOperation(
                operation=Operation.ADD,
                url="/hello-world/",
                anchor="Click here",
                target_url="/target.html",
            )
        ]
        results = backend.process_operations(ops)

        assert results[0].status == ResultStatus.SUCCESS

        executed_queries = [
            str(c) for c in work_cursor.execute.call_args_list
        ]
        create_calls = [q for q in executed_queries if "CREATE TABLE" in q]
        insert_calls = [q for q in executed_queries if "INSERT INTO" in q]
        assert len(create_calls) == 1
        assert len(insert_calls) == 1
        assert "backup" in create_calls[0].lower()
