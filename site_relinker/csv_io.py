"""CSV parsing, validation, and output functions."""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

from site_relinker.models import (
    IfLinkedPolicy,
    InputError,
    LinkOperation,
    Operation,
    OperationResult,
    ScanResult,
    ScopeType,
)

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"operation", "url", "anchor"}
OPTIONAL_COLUMNS = {
    "target_url",
    "scope_type",
    "scope_value",
    "if_linked",
    "max_occurrences",
}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

SCAN_HEADERS = [
    "url",
    "anchor",
    "found",
    "linked",
    "current_target_url",
    "current_classes",
    "occurrence_count",
]

DRY_RUN_HEADERS = ["url", "operation", "anchor", "status", "detail"]


def parse_csv(path: Path) -> list[LinkOperation]:
    """Read CSV, validate headers, and parse each row into a LinkOperation.

    Collects all validation errors and raises InputError with a summary
    if any exist.

    Args:
        path: Path to the CSV file.

    Returns:
        A list of parsed LinkOperation objects.

    Raises:
        InputError: If the CSV is missing required columns, has no data rows,
            or contains invalid values.
    """
    if not path.exists():
        raise InputError(f"CSV file not found: {path}")

    with open(path, encoding="utf-8", newline="") as f:
        content = f.read()

    if not content.strip():
        raise InputError("CSV file is empty")

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise InputError("CSV file has no headers")

        headers = set(reader.fieldnames)
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise InputError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )

        operations: list[LinkOperation] = []
        errors: list[str] = []

        for row_num, row in enumerate(reader, start=2):
            try:
                op = _parse_row(row, row_num)
                operations.append(op)
            except (ValueError, KeyError) as e:
                errors.append(f"Row {row_num}: {e}")

    if errors:
        raise InputError(
            f"CSV validation errors:\n" + "\n".join(errors)
        )

    if not operations:
        raise InputError("CSV file contains no data rows")

    logger.info("Parsed %d operations from %s", len(operations), path)
    return operations


def _parse_row(row: dict[str, str], row_num: int) -> LinkOperation:
    """Parse a single CSV row into a LinkOperation.

    Args:
        row: Dictionary of column name to value.
        row_num: The 1-based row number for error reporting.

    Returns:
        A parsed LinkOperation.

    Raises:
        ValueError: If the row contains invalid values.
    """
    operation_str = row.get("operation", "").strip().lower()
    try:
        operation = Operation(operation_str)
    except ValueError:
        raise ValueError(
            f"Invalid operation: {operation_str!r}"
        ) from None

    url = row.get("url", "").strip()
    if not url:
        raise ValueError("Missing required field: url")

    anchor = row.get("anchor", "").strip()
    if not anchor:
        raise ValueError("Missing required field: anchor")

    target_url = row.get("target_url", "").strip() or None

    scope_type_str = row.get("scope_type", "").strip().lower()
    if scope_type_str:
        try:
            scope_type = ScopeType(scope_type_str)
        except ValueError:
            raise ValueError(
                f"Invalid scope_type: {scope_type_str!r}"
            ) from None
    else:
        scope_type = ScopeType.WHOLE_BODY

    scope_value = row.get("scope_value", "").strip() or None

    if_linked_str = row.get("if_linked", "").strip().lower()
    if if_linked_str:
        try:
            if_linked: IfLinkedPolicy | None = IfLinkedPolicy(if_linked_str)
        except ValueError:
            raise ValueError(
                f"Invalid if_linked: {if_linked_str!r}"
            ) from None
    else:
        if_linked = None

    max_occurrences = row.get("max_occurrences", "").strip() or None

    return LinkOperation(
        operation=operation,
        url=url,
        anchor=anchor,
        target_url=target_url,
        scope_type=scope_type,
        scope_value=scope_value,
        if_linked=if_linked,
        max_occurrences=max_occurrences,
    )


def write_scan_results(
    results: list[ScanResult], output: Path | None
) -> None:
    """Write scan results as CSV to a file or stdout.

    Args:
        results: List of ScanResult objects to write.
        output: Path to the output file, or None for stdout.
    """
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", newline="", encoding="utf-8") as f:
            _write_scan_csv(f, results)
        logger.info("Scan results written to %s", output)
    else:
        _write_scan_csv(sys.stdout, results)


def _write_scan_csv(
    f: object, results: list[ScanResult]
) -> None:
    """Write scan CSV rows to a file-like object.

    Args:
        f: A file-like object supporting write().
        results: List of ScanResult objects.
    """
    writer = csv.DictWriter(f, fieldnames=SCAN_HEADERS)  # type: ignore[arg-type]
    writer.writeheader()
    for r in results:
        writer.writerow(
            {
                "url": r.url,
                "anchor": r.anchor,
                "found": r.found,
                "linked": r.linked,
                "current_target_url": r.current_target_url or "",
                "current_classes": r.current_classes or "",
                "occurrence_count": r.occurrence_count,
            }
        )


def write_dry_run_report(
    results: list[OperationResult], output: Path | None
) -> None:
    """Write dry-run report as CSV to a file or stdout.

    Args:
        results: List of OperationResult objects to write.
        output: Path to the output file, or None for stdout.
    """
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", newline="", encoding="utf-8") as f:
            _write_dry_run_csv(f, results)
        logger.info("Dry-run report written to %s", output)
    else:
        _write_dry_run_csv(sys.stdout, results)


def _write_dry_run_csv(
    f: object, results: list[OperationResult]
) -> None:
    """Write dry-run CSV rows to a file-like object.

    Args:
        f: A file-like object supporting write().
        results: List of OperationResult objects.
    """
    writer = csv.DictWriter(f, fieldnames=DRY_RUN_HEADERS)  # type: ignore[arg-type]
    writer.writeheader()
    for r in results:
        writer.writerow(
            {
                "url": r.url,
                "operation": r.operation.value,
                "anchor": r.anchor,
                "status": r.status.value,
                "detail": r.detail,
            }
        )
