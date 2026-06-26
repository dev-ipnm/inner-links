"""End-to-end integration tests for site_relinker."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from site_relinker.cli import main


def _make_page(path: Path, content: str) -> None:
    """Write an HTML page at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestIntegration:
    """End-to-end integration tests exercising the full pipeline."""

    def test_mixed_operations_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full CSV with add, replace, remove, and scan on a static site."""
        site = tmp_path / "site"
        _make_page(
            site / "page.html",
            "<!DOCTYPE html>\n<html><head><title>Test</title></head><body>\n"
            "<p>Click here for info.</p>\n"
            '<p>Visit our <a href="/old-help.html">help page</a> for assistance.</p>\n'
            '<p>To <a href="/remove-me.html" class="inner-link">'
            "learn more</a> about us.</p>\n"
            "<p>Please contact us for details.</p>\n"
            "</body></html>",
        )

        output_dir = tmp_path / "output"
        scan_output = tmp_path / "scan.csv"

        csv_path = tmp_path / "ops.csv"
        csv_path.write_text(
            "operation,url,anchor,target_url\n"
            "add,/page.html,Click here,/new-target.html\n"
            "replace,/page.html,help page,/new-help.html\n"
            "remove,/page.html,learn more,\n"
            "scan,/page.html,contact us,\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(site),
                "--output-dir", str(output_dir),
                "--link-classes", "inner-link",
                "--output", str(scan_output),
            ],
        )

        exit_code = main()
        assert exit_code == 0

        output_file = output_dir / "page.html"
        assert output_file.exists()
        content = output_file.read_text()

        assert "/new-target.html" in content

        assert "/new-help.html" in content
        assert "/old-help.html" not in content

        assert "learn more" in content
        assert "/remove-me.html" not in content

        assert scan_output.exists()
        scan_text = scan_output.read_text()
        assert "contact us" in scan_text

    def test_dry_run_no_modification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry-run produces a report without modifying source or output."""
        site = tmp_path / "site"
        page_path = site / "page.html"
        original_html = (
            "<!DOCTYPE html>\n<html><head><title>Test</title></head><body>\n"
            "<p>Click here for info.</p>\n"
            "</body></html>"
        )
        _make_page(page_path, original_html)

        output_dir = tmp_path / "output"
        report_path = tmp_path / "report.csv"

        csv_path = tmp_path / "ops.csv"
        csv_path.write_text(
            "operation,url,anchor,target_url\n"
            "add,/page.html,Click here,/target.html\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(site),
                "--output-dir", str(output_dir),
                "--dry-run",
                "--output", str(report_path),
            ],
        )

        exit_code = main()
        assert exit_code == 0

        assert page_path.read_text() == original_html

        output_files = list(output_dir.rglob("*.html"))
        assert len(output_files) == 0

        assert report_path.exists()
        with open(report_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["status"] == "would_add"
        assert rows[0]["anchor"] == "Click here"

    def test_scan_only_outputs_csv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scan-only operations write correct CSV with expected columns."""
        site = tmp_path / "site"
        _make_page(
            site / "page.html",
            "<!DOCTYPE html>\n<html><head><title>Test</title></head><body>\n"
            "<p>Click here for info.</p>\n"
            '<p>Visit our <a href="/help.html" class="inner-link">help page</a>.</p>\n'
            "</body></html>",
        )

        scan_output = tmp_path / "scan_results.csv"

        csv_path = tmp_path / "ops.csv"
        csv_path.write_text(
            "operation,url,anchor,target_url\n"
            "scan,/page.html,Click here,\n"
            "scan,/page.html,help page,\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(csv_path),
                "--domains", "example.com",
                "--web-root", str(site),
                "--output-dir", str(tmp_path / "output"),
                "--output", str(scan_output),
            ],
        )

        exit_code = main()
        assert exit_code == 0

        assert scan_output.exists()
        with open(scan_output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        expected_headers = {
            "url", "anchor", "found", "linked",
            "current_target_url", "current_classes", "occurrence_count",
        }
        assert set(reader.fieldnames or []) == expected_headers

        unlinked = next(r for r in rows if "Click" in r["anchor"])
        assert unlinked["found"] == "True"
        assert unlinked["linked"] == "False"

        linked = next(r for r in rows if "help" in r["anchor"])
        assert linked["found"] == "True"
        assert linked["linked"] == "True"
        assert linked["current_target_url"] == "/help.html"

    def test_error_handling_exit_codes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bad CSV gives exit 1; valid CSV with missing page gives exit 0."""
        site = tmp_path / "site"
        site.mkdir()

        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text(
            "wrong_column\nsome_value\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(bad_csv),
                "--domains", "example.com",
                "--web-root", str(site),
                "--output-dir", str(tmp_path / "output1"),
            ],
        )
        assert main() == 1

        good_csv = tmp_path / "good.csv"
        good_csv.write_text(
            "operation,url,anchor,target_url\n"
            "add,/nonexistent.html,Click here,/target.html\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site-relinker",
                "--mode", "static",
                "--csv", str(good_csv),
                "--domains", "example.com",
                "--web-root", str(site),
                "--output-dir", str(tmp_path / "output2"),
            ],
        )
        assert main() == 0
