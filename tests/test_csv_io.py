"""Tests for site_relinker.csv_io — CSV parsing and output."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from site_relinker.csv_io import parse_csv, write_dry_run_report, write_scan_results
from site_relinker.models import (
    InputError,
    Operation,
    OperationResult,
    ResultStatus,
    ScanResult,
)


class TestParseCSV:
    """Tests for the parse_csv function."""

    def test_parse_valid_csv(
        self, csv_file: Callable[..., Path]
    ) -> None:
        """All columns, multiple rows are parsed correctly."""
        rows = [
            {
                "operation": "add",
                "url": "/page.html",
                "anchor": "click here",
                "target_url": "/target.html",
                "scope_type": "element_id",
                "scope_value": "content",
                "if_linked": "skip",
                "max_occurrences": "1",
            },
            {
                "operation": "remove",
                "url": "/other.html",
                "anchor": "old link",
                "target_url": "",
                "scope_type": "",
                "scope_value": "",
                "if_linked": "",
                "max_occurrences": "",
            },
        ]
        path = csv_file(rows)
        operations = parse_csv(path)
        assert len(operations) == 2
        assert operations[0].operation == Operation.ADD
        assert operations[0].target_url == "/target.html"
        assert operations[1].operation == Operation.REMOVE
        assert operations[1].target_url is None

    def test_parse_minimal_csv(
        self, csv_file: Callable[..., Path]
    ) -> None:
        """Only required columns are provided."""
        rows = [
            {
                "operation": "scan",
                "url": "/page.html",
                "anchor": "some text",
            },
        ]
        path = csv_file(rows)
        operations = parse_csv(path)
        assert len(operations) == 1
        assert operations[0].operation == Operation.SCAN

    def test_parse_missing_required_column(
        self, csv_file: Callable[..., Path]
    ) -> None:
        """InputError raised when required column is missing."""
        rows: list[dict[str, Any]] = [
            {
                "operation": "add",
                "url": "/page.html",
            },
        ]
        path = csv_file(rows)
        with pytest.raises(InputError, match="anchor"):
            parse_csv(path)

    def test_parse_invalid_operation_value(
        self, csv_file: Callable[..., Path]
    ) -> None:
        """InputError raised with row number for invalid operation."""
        rows = [
            {
                "operation": "invalid",
                "url": "/page.html",
                "anchor": "click here",
            },
        ]
        path = csv_file(rows)
        with pytest.raises(InputError, match="Row 2"):
            parse_csv(path)

    def test_parse_add_without_target_url(
        self, csv_file: Callable[..., Path]
    ) -> None:
        """InputError raised for add without target_url."""
        rows = [
            {
                "operation": "add",
                "url": "/page.html",
                "anchor": "click here",
                "target_url": "",
            },
        ]
        path = csv_file(rows)
        with pytest.raises(InputError, match="target_url"):
            parse_csv(path)

    def test_parse_empty_csv(self, tmp_path: Path) -> None:
        """InputError raised for empty CSV file."""
        path = tmp_path / "empty.csv"
        path.write_text("")
        with pytest.raises(InputError, match="empty"):
            parse_csv(path)


class TestWriteScanResults:
    """Tests for the write_scan_results function."""

    def test_write_scan_results_to_file(self, tmp_path: Path) -> None:
        """CSV output matches expected format."""
        results = [
            ScanResult(
                url="/page.html",
                operation=Operation.SCAN,
                anchor="click here",
                status=ResultStatus.SUCCESS,
                found=True,
                linked=True,
                current_target_url="/target.html",
                current_classes="inner-link",
                occurrence_count=2,
            ),
        ]
        output = tmp_path / "scan.csv"
        write_scan_results(results, output)

        content = output.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "url" in lines[0]
        assert "found" in lines[0]
        assert "/page.html" in lines[1]
        assert "True" in lines[1]


class TestWriteDryRunReport:
    """Tests for the write_dry_run_report function."""

    def test_write_dry_run_report_to_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Output captured correctly when writing to stdout."""
        results = [
            OperationResult(
                url="/page.html",
                operation=Operation.ADD,
                anchor="click here",
                status=ResultStatus.WOULD_ADD,
                detail="Would add link to /target.html",
            ),
        ]
        write_dry_run_report(results, None)

        captured = capsys.readouterr()
        assert "url" in captured.out
        assert "would_add" in captured.out
        assert "/page.html" in captured.out
