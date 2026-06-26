"""WordPress MySQL backend for link operations."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from site_relinker.html_ops import process_operation
from site_relinker.models import (
    AppConfig,
    BackendError,
    LinkOperation,
    OperationResult,
    ResultStatus,
)

logger = logging.getLogger(__name__)

pymysql: Any = None


def _ensure_pymysql() -> Any:
    """Lazy-import pymysql to avoid hard dependency at module load time."""
    global pymysql
    if pymysql is None:
        import pymysql as _pymysql

        pymysql = _pymysql
    return pymysql


class WordPressBackend:
    """Processes link operations on WordPress post content via MySQL.

    Connects to a WordPress database, resolves URLs to post IDs via
    permalink structure, and applies link operations to post_content
    fields within a transaction.

    Args:
        config: The global application configuration.

    Raises:
        BackendError: If database connection fails or WordPress config
            is missing.
    """

    def __init__(self, config: AppConfig) -> None:
        if config.wordpress is None:
            raise BackendError(
                "WordPress backend configuration is required"
            )

        self._config = config
        self._wp = config.wordpress

        _db = _ensure_pymysql()
        try:
            self._conn: Any = _db.connect(
                host=self._wp.db_host,
                port=self._wp.db_port,
                user=self._wp.db_user,
                password=self._wp.db_password,
                database=self._wp.db_name,
                charset="utf8mb4",
                cursorclass=_db.cursors.DictCursor,
            )
        except Exception as e:
            raise BackendError(f"Database connection failed: {e}") from e

        self._permalink_structure = self._read_permalink_structure()
        self._slug_map = self._build_slug_map()

    def resolve_url(self, url: str) -> int:
        """Resolve a URL path to a WordPress post ID.

        Args:
            url: The URL path to resolve.

        Returns:
            The post_id for the matching post.

        Raises:
            BackendError: If no matching post is found.
        """
        slug = self._extract_slug(url)

        if slug in self._slug_map:
            return self._slug_map[slug]

        raise BackendError(f"No post found for URL: {url}")

    def process_operations(
        self, operations: list[LinkOperation]
    ) -> list[OperationResult]:
        """Process link operations grouped by URL within a transaction.

        Args:
            operations: The list of link operations to process.

        Returns:
            A list of OperationResult for all operations.
        """
        grouped: dict[str, list[LinkOperation]] = defaultdict(list)
        for op in operations:
            grouped[op.url].append(op)

        all_results: list[OperationResult] = []
        modified_posts: dict[int, str] = {}
        post_ids_involved: list[int] = []

        for url, ops in grouped.items():
            try:
                post_id = self.resolve_url(url)
            except BackendError as e:
                all_results.extend(
                    OperationResult(
                        url=url,
                        operation=op.operation,
                        anchor=op.anchor,
                        status=ResultStatus.ERROR,
                        detail=str(e),
                    )
                    for op in ops
                )
                continue

            post_ids_involved.append(post_id)
            html = self._fetch_post_content(post_id)
            modified = html

            for op in ops:
                modified, op_results = process_operation(
                    modified, op, self._config
                )
                all_results.extend(op_results)

            if not self._config.dry_run and modified != html:
                modified_posts[post_id] = modified

        if modified_posts:
            try:
                if self._wp.backup_table:
                    self._backup_rows(list(modified_posts.keys()))

                cursor = self._conn.cursor()
                for post_id, content in modified_posts.items():
                    cursor.execute(
                        f"UPDATE `{self._wp.table_prefix}posts` "
                        "SET `post_content` = %s WHERE `ID` = %s",
                        (content, post_id),
                    )
                self._conn.commit()
                logger.info(
                    "Updated %d posts in database", len(modified_posts)
                )
            except Exception as e:
                self._conn.rollback()
                raise BackendError(
                    f"Database update failed, rolled back: {e}"
                ) from e

        return all_results

    def _read_permalink_structure(self) -> str:
        """Read the permalink_structure option from wp_options.

        Returns:
            The permalink structure string (e.g., "/%postname%/").

        Raises:
            BackendError: If the option cannot be read.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"SELECT `option_value` FROM "
                f"`{self._wp.table_prefix}options` "
                "WHERE `option_name` = 'permalink_structure'",
            )
            row = cursor.fetchone()
            if row is None:
                raise BackendError(
                    "permalink_structure not found in wp_options"
                )
            return str(row["option_value"])
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(
                f"Failed to read permalink structure: {e}"
            ) from e

    def _build_slug_map(self) -> dict[str, int]:
        """Build a reverse map from post slug to post ID.

        Returns:
            A dictionary mapping post slugs to post IDs.
        """
        try:
            cursor = self._conn.cursor()
            type_placeholders = ", ".join(
                ["%s"] * len(self._wp.post_types)
            )
            status_placeholders = ", ".join(
                ["%s"] * len(self._wp.post_statuses)
            )
            cursor.execute(
                f"SELECT `ID`, `post_name`, `post_date` FROM "
                f"`{self._wp.table_prefix}posts` "
                f"WHERE `post_type` IN ({type_placeholders}) "
                f"AND `post_status` IN ({status_placeholders})",
                (*self._wp.post_types, *self._wp.post_statuses),
            )
            rows = cursor.fetchall()
            return {str(row["post_name"]): int(row["ID"]) for row in rows}
        except Exception as e:
            raise BackendError(
                f"Failed to build slug map: {e}"
            ) from e

    def _extract_slug(self, url: str) -> str:
        """Extract the post slug from a URL path.

        Uses the permalink structure to determine which part of the URL
        corresponds to the post slug.

        Args:
            url: The URL path to extract the slug from.

        Returns:
            The extracted post slug.
        """
        path = url.strip("/")
        parts = path.split("/")

        structure = self._permalink_structure.strip("/")
        struct_parts = structure.split("/")

        for i, sp in enumerate(struct_parts):
            if sp == "%postname%" and i < len(parts):
                return parts[i]

        return parts[-1] if parts else path

    def _fetch_post_content(self, post_id: int) -> str:
        """Fetch the post_content for a given post ID.

        Args:
            post_id: The WordPress post ID.

        Returns:
            The post content HTML string.

        Raises:
            BackendError: If the post cannot be fetched.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"SELECT `post_content` FROM "
                f"`{self._wp.table_prefix}posts` WHERE `ID` = %s",
                (post_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise BackendError(
                    f"Post not found for ID: {post_id}"
                )
            return str(row["post_content"])
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(
                f"Failed to fetch post content: {e}"
            ) from e

    def _backup_rows(self, post_ids: list[int]) -> None:
        """Dump affected rows to a timestamped backup table.

        Args:
            post_ids: The list of post IDs to back up.

        Raises:
            BackendError: If backup creation fails.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self._wp.table_prefix}posts_backup_{timestamp}"
        posts_table = f"{self._wp.table_prefix}posts"

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"CREATE TABLE `{backup_name}` LIKE `{posts_table}`"
            )
            placeholders = ", ".join(["%s"] * len(post_ids))
            cursor.execute(
                f"INSERT INTO `{backup_name}` "
                f"SELECT * FROM `{posts_table}` "
                f"WHERE `ID` IN ({placeholders})",
                (*post_ids,),
            )
            logger.info(
                "Backed up %d rows to %s", len(post_ids), backup_name
            )
        except Exception as e:
            raise BackendError(
                f"Failed to create backup table: {e}"
            ) from e
