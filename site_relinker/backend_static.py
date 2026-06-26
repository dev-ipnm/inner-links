"""Static site filesystem backend for link operations."""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from pathlib import Path

from site_relinker.html_ops import process_operation
from site_relinker.models import (
    AppConfig,
    BackendError,
    LinkOperation,
    OperationResult,
)

logger = logging.getLogger(__name__)


class StaticSiteBackend:
    """Processes link operations on static HTML files.

    Reads files from a web root directory and writes modified files
    to a separate output directory, preserving directory structure.
    Never writes to the source tree.

    Args:
        config: The global application configuration.

    Raises:
        BackendError: If the web root does not exist.
    """

    def __init__(self, config: AppConfig) -> None:
        if config.static is None:
            raise BackendError("Static backend configuration is required")

        self._config = config
        self._static = config.static

        if not self._static.web_root.is_dir():
            raise BackendError(
                f"Web root does not exist: {self._static.web_root}"
            )

        self._static.output_dir.mkdir(parents=True, exist_ok=True)

    def resolve_url(self, url: str) -> Path:
        """Resolve a URL path to a filesystem path under web_root.

        Args:
            url: The URL path (root-relative, e.g. "/help/topic.html").

        Returns:
            The resolved filesystem path.

        Raises:
            BackendError: If the file does not exist or has a
                non-matching extension.
        """
        url_path = url.lstrip("/")
        file_path = self._static.web_root / url_path

        if not file_path.is_file():
            raise BackendError(f"File not found: {file_path}")

        ext = file_path.suffix.lstrip(".")
        if ext not in self._static.extensions:
            raise BackendError(
                f"File extension '{ext}' not in allowed extensions: "
                f"{self._static.extensions}"
            )

        return file_path

    def process_operations(
        self, operations: list[LinkOperation]
    ) -> list[OperationResult]:
        """Process link operations grouped by URL.

        Reads each file once per URL, applies all operations for that
        URL, and writes the modified file to the output directory.

        Args:
            operations: The list of link operations to process.

        Returns:
            A list of OperationResult for all operations.
        """
        grouped: dict[str, list[LinkOperation]] = defaultdict(list)
        for op in operations:
            grouped[op.url].append(op)

        all_results: list[OperationResult] = []

        for url, ops in grouped.items():
            results = self._process_url(url, ops)
            all_results.extend(results)

        if self._static.copy_unchanged:
            self._copy_unchanged_files(grouped)

        return all_results

    def _process_url(
        self, url: str, operations: list[LinkOperation]
    ) -> list[OperationResult]:
        """Process all operations for a single URL.

        Args:
            url: The page URL.
            operations: The operations targeting this URL.

        Returns:
            A list of OperationResult for the operations.
        """
        try:
            file_path = self.resolve_url(url)
        except BackendError as e:
            from site_relinker.models import Operation, ResultStatus

            return [
                OperationResult(
                    url=url,
                    operation=op.operation,
                    anchor=op.anchor,
                    status=ResultStatus.ERROR,
                    detail=str(e),
                )
                for op in operations
            ]

        html = file_path.read_text(encoding=self._static.encoding)
        modified = html
        results: list[OperationResult] = []

        for op in operations:
            modified, op_results = process_operation(modified, op, self._config)
            results.extend(op_results)

        if not self._config.dry_run and modified != html:
            self._write_output(url, modified)
            logger.info("Modified: %s", url)
        elif modified != html:
            logger.debug("Dry run — would modify: %s", url)

        return results

    def _write_output(self, url: str, content: str) -> None:
        """Write modified content to the output directory.

        Args:
            url: The URL path used to determine the output file path.
            content: The modified HTML content.
        """
        url_path = url.lstrip("/")
        output_path = self._static.output_dir / url_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding=self._static.encoding)

    def _copy_unchanged_files(
        self, processed_urls: dict[str, list[LinkOperation]]
    ) -> None:
        """Copy unmodified files to the output directory.

        Args:
            processed_urls: URLs that were already processed.
        """
        processed_paths = set()
        for url in processed_urls:
            try:
                processed_paths.add(self.resolve_url(url))
            except BackendError:
                pass

        for ext in self._static.extensions:
            for file_path in self._static.web_root.rglob(f"*.{ext}"):
                if file_path in processed_paths:
                    continue
                rel = file_path.relative_to(self._static.web_root)
                dest = self._static.output_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
