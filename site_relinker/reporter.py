"""Result formatting for dry-run and execution reports."""

from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

from site_relinker.models import OperationResult, ResultStatus

logger = logging.getLogger(__name__)

_SUCCESS_STATUSES = {
    ResultStatus.SUCCESS,
    ResultStatus.WOULD_ADD,
    ResultStatus.WOULD_REPLACE,
    ResultStatus.WOULD_REMOVE,
}

_SKIP_STATUSES = {
    ResultStatus.ALREADY_LINKED,
    ResultStatus.NOT_FOUND,
    ResultStatus.SCOPE_NOT_FOUND,
    ResultStatus.SKIPPED,
}


class Reporter:
    """Formats and outputs operation results.

    Args:
        results: List of OperationResult objects to report on.
    """

    def __init__(self, results: list[OperationResult]) -> None:
        self._results = results

    def format_human(self) -> str:
        """Format results as a human-readable table for stderr.

        Returns:
            A formatted string with aligned columns.
        """
        if not self._results:
            return "No operations to report."

        header = f"{'URL':<40} {'OP':<8} {'ANCHOR':<25} {'STATUS':<18} DETAIL"
        separator = "-" * len(header)
        lines = [header, separator]

        for r in self._results:
            url_display = _truncate(r.url, 40)
            anchor_display = _truncate(r.anchor, 25)
            lines.append(
                f"{url_display:<40} {r.operation.value:<8} "
                f"{anchor_display:<25} {r.status.value:<18} {r.detail}"
            )

        return "\n".join(lines)

    def format_csv(self, output: Path | None) -> None:
        """Write results as CSV to a file or stdout.

        Args:
            output: Path to the output file, or None for stdout.
        """
        fieldnames = [
            "url",
            "operation",
            "anchor",
            "status",
            "detail",
            "linked",
            "current_target_url",
            "current_classes",
            "occurrence_count",
        ]

        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w", newline="", encoding="utf-8") as f:
                self._write_csv(f, fieldnames)
        else:
            self._write_csv(sys.stdout, fieldnames)

    def _write_csv(
        self, f: object, fieldnames: list[str]
    ) -> None:
        """Write CSV rows to a file-like object.

        Args:
            f: A file-like object supporting write().
            fieldnames: List of column names.
        """
        writer = csv.DictWriter(f, fieldnames=fieldnames)  # type: ignore[arg-type]
        writer.writeheader()
        for r in self._results:
            writer.writerow(
                {
                    "url": r.url,
                    "operation": r.operation.value,
                    "anchor": r.anchor,
                    "status": r.status.value,
                    "detail": r.detail,
                    "linked": r.linked,
                    "current_target_url": r.current_target_url or "",
                    "current_classes": r.current_classes or "",
                    "occurrence_count": r.occurrence_count,
                }
            )

    def format_json(self, output: Path | None) -> None:
        """Write results as JSON to a file or stdout.

        Args:
            output: Path to the output file, or None for stdout.
        """
        data = [
            {
                "url": r.url,
                "operation": r.operation.value,
                "anchor": r.anchor,
                "status": r.status.value,
                "detail": r.detail,
                "linked": r.linked,
                "current_target_url": r.current_target_url,
                "current_classes": r.current_classes,
                "occurrence_count": r.occurrence_count,
            }
            for r in self._results
        ]
        content = json.dumps(data, indent=2)

        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content + "\n")

    def summary(self) -> str:
        """Generate a one-line summary of results.

        Returns:
            A string like "Modified 14, skipped 3, errors 2".
        """
        if not self._results:
            return "No operations performed."

        modified = sum(
            1 for r in self._results if r.status in _SUCCESS_STATUSES
        )
        skipped = sum(
            1 for r in self._results if r.status in _SKIP_STATUSES
        )
        errors = sum(
            1 for r in self._results if r.status == ResultStatus.ERROR
        )

        return f"Modified {modified}, skipped {skipped}, errors {errors}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed.

    Args:
        text: The string to truncate.
        max_len: Maximum length.

    Returns:
        The truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
