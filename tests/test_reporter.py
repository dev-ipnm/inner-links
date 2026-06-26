"""Tests for site_relinker.reporter — result formatting."""

from __future__ import annotations

import json
from pathlib import Path

from site_relinker.models import Operation, OperationResult, ResultStatus
from site_relinker.reporter import Reporter


def _make_result(
    status: ResultStatus,
    url: str = "/page.html",
    anchor: str = "click here",
    operation: Operation = Operation.ADD,
    detail: str = "",
) -> OperationResult:
    return OperationResult(
        url=url,
        operation=operation,
        anchor=anchor,
        status=status,
        detail=detail,
    )


class TestFormatHuman:
    """Tests for the format_human method."""

    def test_format_human_mixed_results(self) -> None:
        """Readable table includes all status types."""
        results = [
            _make_result(ResultStatus.SUCCESS, detail="Added link"),
            _make_result(ResultStatus.ALREADY_LINKED, detail="Skipped"),
            _make_result(ResultStatus.ERROR, detail="Parse failure"),
        ]
        reporter = Reporter(results)
        output = reporter.format_human()

        assert "success" in output
        assert "already_linked" in output
        assert "error" in output
        assert "URL" in output


class TestFormatCSV:
    """Tests for the format_csv method."""

    def test_format_csv_output(
        self, tmp_path: Path
    ) -> None:
        """Valid CSV with headers is produced."""
        results = [
            _make_result(ResultStatus.SUCCESS, detail="Done"),
            _make_result(ResultStatus.NOT_FOUND, detail="Missing"),
        ]
        reporter = Reporter(results)
        output_path = tmp_path / "report.csv"
        reporter.format_csv(output_path)

        content = output_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 3
        assert "url" in lines[0]
        assert "status" in lines[0]


class TestFormatJSON:
    """Tests for the format_json method."""

    def test_format_json_output(self, tmp_path: Path) -> None:
        """Valid JSON array is produced."""
        results = [
            _make_result(ResultStatus.WOULD_ADD, detail="Dry run"),
        ]
        reporter = Reporter(results)
        output_path = tmp_path / "report.json"
        reporter.format_json(output_path)

        content = output_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["status"] == "would_add"
        assert data[0]["url"] == "/page.html"


class TestSummary:
    """Tests for the summary method."""

    def test_summary_counts(self) -> None:
        """Summary correctly counts modified, skipped, and errors."""
        results = [
            _make_result(ResultStatus.SUCCESS),
            _make_result(ResultStatus.SUCCESS),
            _make_result(ResultStatus.SUCCESS),
            _make_result(ResultStatus.ALREADY_LINKED),
            _make_result(ResultStatus.SKIPPED),
            _make_result(ResultStatus.ERROR),
        ]
        reporter = Reporter(results)
        summary = reporter.summary()
        assert summary == "Modified 3, skipped 2, errors 1"

    def test_empty_results(self) -> None:
        """Graceful handling of no operations."""
        reporter = Reporter([])
        assert reporter.format_human() == "No operations to report."
        assert reporter.summary() == "No operations performed."

    def test_summary_all_success(self) -> None:
        """Clean message when everything worked."""
        results = [
            _make_result(ResultStatus.SUCCESS),
            _make_result(ResultStatus.SUCCESS),
        ]
        reporter = Reporter(results)
        summary = reporter.summary()
        assert summary == "Modified 2, skipped 0, errors 0"
