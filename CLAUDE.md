# CLAUDE.md — site_relinker Development Specification

## Agent Workflow Rule

**MANDATORY:** After completing each numbered development step (including all
deliverables and verification commands), STOP and ask the user for explicit
confirmation before proceeding to the next step. Do not combine steps or
continue autonomously. Each step is designed to fit within a single session's
resource budget.

---

## Project Overview

**site_relinker** is a Python CLI tool for batch manipulation of internal links
across static HTML sites and WordPress (MySQL) installations. It reads a CSV
file describing link operations (add, replace, remove, scan) and applies them
to scoped content areas within target pages, with full dry-run support.

### Core Capabilities

1. **Add** — wrap a found anchor text in an `<a>` tag pointing to a target URL
2. **Replace** — change the `href` of an existing `<a>` tag around a given anchor
3. **Remove** — strip an `<a>` tag from around a given anchor, leaving the text
4. **Scan** — search for an anchor across pages and report its link status

### Two Backends

- **Static site** — URL maps to a filesystem path under a web root; modified
  files are written to a separate output directory (never in-place)
- **WordPress** — URL maps to a `wp_posts` row via permalink structure
  resolution; changes are wrapped in a DB transaction with optional backup table

---

## Technical Stack

| Component        | Choice                              |
|------------------|-------------------------------------|
| Python           | 3.10+                               |
| HTML parsing     | beautifulsoup4 + lxml parser        |
| Data models      | Pydantic v2                         |
| Environment      | python-dotenv                       |
| MySQL access     | PyMySQL                             |
| CLI framework    | argparse (stdlib)                   |
| Testing          | pytest + pytest-cov                 |
| Type checking    | mypy --strict                       |
| Linting          | ruff                                |

---

## Python Developer Guidelines

### Style & Structure

- PEP 8 compliant, line length ≤ 88 (Black-compatible)
- f-strings over `.format()` or `%`
- `pathlib.Path` over `os.path`
- `with` statements for all resource handling
- No bare `except:` — always catch specific exceptions
- Module block order: docstring → stdlib → third-party → local → constants →
  classes/functions → `if __name__ == "__main__"` guard

### Type Hints

All public functions and methods must have complete type annotations compatible
with `mypy --strict`. Use `from __future__ import annotations` at the top of
every module.

### Docstrings

Google-style docstrings on all public classes, methods, and functions:

```python
def normalize_url(url: str, domains: list[str]) -> str:
    """Strip domain from an internal URL and return a root-relative path.

    Args:
        url: The URL to normalize (absolute or relative).
        domains: List of domains considered internal.

    Returns:
        A root-relative URL path (e.g., "/help/topic.html").

    Raises:
        ValueError: If the URL is external and cannot be normalized.
    """
```

### Error Handling

Three categories with distinct exit codes:

| Category          | Exit Code | Examples                                    |
|-------------------|-----------|---------------------------------------------|
| Success           | 0         | All operations completed (or dry-run done)  |
| User/input error  | 1         | Bad CSV, missing required columns, bad args |
| Runtime error     | 2         | File I/O failure, DB connection error       |

Use custom exception classes inheriting from a base `SiteRelinkerError`:
- `ConfigError(SiteRelinkerError)` — invalid configuration or arguments
- `InputError(SiteRelinkerError)` — malformed CSV or missing files
- `BackendError(SiteRelinkerError)` — filesystem or database failures

### Logging

- Use `logging` module exclusively — no `print()` in production code
- Logger per module: `logger = logging.getLogger(__name__)`
- Format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- Levels: DEBUG for operation detail, INFO for per-file summaries,
  WARNING for skipped operations, ERROR for failures

### Security Rules

- No hardcoded credentials — read DB connection from env vars or `.env`
- No `verify=False` or equivalent insecure defaults
- Sanitize all user-provided CSS class names (alphanumeric + hyphen + underscore only)

---

## Functional Requirements

### R1: Content Area Scoping (`scope_type` / `scope_value`)

Operations target a subset of the page content, not the entire document.

| `scope_type`   | `scope_value`          | Behavior                                |
|----------------|------------------------|-----------------------------------------|
| `element_id`   | An HTML element `id`   | Operate only within that element        |
| `above`        | A literal string       | Operate only in content above the first occurrence of the string |
| `below`        | A literal string       | Operate only in content below the first occurrence of the string |
| *(empty/null)* | *(ignored)*            | Operate on the entire `<body>` content  |

When scope is `above` or `below`, the boundary string itself is excluded from
the operation area. The boundary string is matched literally (case-sensitive)
against the rendered text content of the document.

### R2: Anchor Matching

- **Case-insensitive** comparison
- **Word-boundary** delimited: a match requires that the character immediately
  before and after the anchor text is either a non-alphanumeric character or
  the start/end of the text node
- **`--strict-text-only` is the DEFAULT** — match only within individual text
  nodes; do not span across child elements or existing `<a>` tags. This
  prevents accidentally consuming already-linked substrings.
- Optional `--cross-tag-match` flag enables matching across inline child
  elements (opt-in, non-default)

### R3: Match Strategy (`--match-strategy`)

| Value   | Behavior                                              |
|---------|-------------------------------------------------------|
| `first` | Operate on the first occurrence only (default for add)|
| `all`   | Operate on every occurrence (default for remove/scan) |
| `any`   | Select one occurrence at random                       |
| *N*     | Operate on the Nth occurrence (1-based positive int)  |

Per-row CSV override via `max_occurrences` column.

### R4: Already-Linked Anchor Policy (`--if-linked`)

Applies when an **add** operation finds the anchor already wrapped in `<a>`:

| Value     | Behavior                                         |
|-----------|--------------------------------------------------|
| `skip`    | Leave unchanged (default — idempotent, safe)     |
| `error`   | Record an error for this row                     |
| `replace` | Overwrite the existing href (merge with op 2)    |

Per-row CSV override via `if_linked` column.

### R5: URL Handling

- A list of **domains** is provided via `--domains` (comma-separated)
- URLs matching any listed domain are classified as **internal**
- On insertion, internal URLs are normalized to **root-relative** form:
  `https://example.com/help/topic.html` → `/help/topic.html`
- External URLs are inserted as-is
- Protocol-relative URLs (`//example.com/...`) are treated as internal if the
  domain matches

### R6: Link Attributes on Insertion

- `--link-classes` — comma-separated CSS classes applied to every inserted
  `<a>` tag (e.g., `inner-link,change22`)
- `rel` attribute: auto-set to `noopener noreferrer` for external URLs; empty
  for internal
- `target` attribute: not set by default; settable via `--link-target` (e.g.,
  `_blank`)

### R7: Link Removal Filtering

When `operation=remove`, only remove `<a>` tags that have **at least one** of
the CSS classes specified in `--link-classes`. If `--link-classes` is empty,
remove is unrestricted (operates on any `<a>` around the anchor).

### R8: Dry-Run Mode (`--dry-run`)

Available for all operations. Produces a structured report of what *would*
change without modifying any file or database row. Output columns:

`url, operation, anchor, status, detail`

Status values: `would_add`, `would_replace`, `would_remove`, `already_linked`,
`not_found`, `scope_not_found`, `error`.

### R9: Scan Output

Scan results are written as CSV (to stdout or `--output` file):

`url, anchor, found, linked, current_target_url, current_classes, occurrence_count`

### R10: Static Site Backend

- `--web-root` — base directory for resolving URL paths to files
- `--output-dir` — destination for modified files (mirrored directory tree)
- `--extensions` — file types to process (default: `html,htm,shtml`)
- `--encoding` — file encoding (default: `utf-8`)
- `--copy-unchanged` — if set, copy unmodified files too (off by default)
- **Never writes to the source tree**

### R11: WordPress Backend

- Connection via `--db-host`, `--db-port`, `--db-user`, `--db-password`,
  `--db-name` (all also readable from `WP_DB_*` env vars / `.env`)
- `--table-prefix` — default `wp_`
- `--post-types` — default `post,page`
- `--post-statuses` — default `publish`
- URL-to-post resolution: read `permalink_structure` from `wp_options`,
  reverse-map URL path → `post_id` via slug matching
- All changes wrapped in a DB transaction
- `--backup-table` — if set, dump affected rows to a timestamped table before
  modification

### R12: CSV Input Schema

| Column             | Required       | Description                                  |
|--------------------|----------------|----------------------------------------------|
| `operation`        | yes            | `add`, `replace`, `remove`, `scan`           |
| `url`              | yes            | Page URL / path                              |
| `anchor`           | yes            | Text to find                                 |
| `target_url`       | for add/replace| Link destination                             |
| `scope_type`       | no             | `element_id`, `above`, `below`, or blank     |
| `scope_value`      | no             | Element ID or boundary string                |
| `if_linked`        | no             | Per-row override: `skip`, `error`, `replace` |
| `max_occurrences`  | no             | Per-row override for match strategy           |

---

## Module Architecture (8 modules)

```
site_relinker/
├── __init__.py
├── models.py              # 1 — Pydantic models, enums, exceptions
├── url_utils.py           # 2 — URL classification & normalization
├── html_ops.py            # 3 — HTML scoping, matching, link manipulation
├── csv_io.py              # 4 — CSV parsing & validation
├── reporter.py            # 5 — Dry-run & execution result formatting
├── backend_static.py      # 6 — Static site filesystem backend
├── backend_wordpress.py   # 7 — WordPress MySQL backend
└── cli.py                 # 8 — CLI entry point & orchestration
```

### Dependency Graph (strictly top-down, no circular imports)

```
cli.py
├── models.py
├── csv_io.py           → models.py
├── reporter.py         → models.py
├── backend_static.py
│   ├── models.py
│   ├── html_ops.py     → models.py, url_utils.py
│   └── url_utils.py    → models.py
└── backend_wordpress.py
    ├── models.py
    ├── html_ops.py
    └── url_utils.py
```

---

## Module Specifications

### M1: `models.py`

**Enums:**
- `Operation` — `ADD`, `REPLACE`, `REMOVE`, `SCAN`
- `ScopeType` — `ELEMENT_ID`, `ABOVE`, `BELOW`, `WHOLE_BODY`
- `IfLinkedPolicy` — `SKIP`, `ERROR`, `REPLACE`
- `MatchStrategy` — `FIRST`, `ALL`, `ANY`, `NTH`
- `ResultStatus` — `SUCCESS`, `WOULD_ADD`, `WOULD_REPLACE`, `WOULD_REMOVE`,
  `ALREADY_LINKED`, `NOT_FOUND`, `SCOPE_NOT_FOUND`, `SKIPPED`, `ERROR`
- `BackendType` — `STATIC`, `WORDPRESS`

**Pydantic Models:**
- `ScopeDefinition` — `scope_type: ScopeType`, `scope_value: str | None`
- `LinkOperation` — one parsed CSV row (all columns above, with validators)
- `OperationResult` — per-row outcome: `url`, `operation`, `anchor`, `status`,
  `detail`, `linked` (bool), `current_target_url`, `current_classes`,
  `occurrence_count`
- `ScanResult` — extends OperationResult with scan-specific fields
- `StaticConfig` — `web_root: Path`, `output_dir: Path`,
  `extensions: list[str]`, `encoding: str`, `copy_unchanged: bool`
- `WordPressConfig` — `db_host`, `db_port`, `db_user`, `db_password`,
  `db_name`, `table_prefix`, `post_types: list[str]`,
  `post_statuses: list[str]`, `backup_table: bool`
- `AppConfig` — global settings: `backend: BackendType`, `domains: list[str]`,
  `dry_run: bool`, `link_classes: list[str]`, `link_target: str | None`,
  `if_linked: IfLinkedPolicy`, `match_strategy: MatchStrategy`,
  `match_n: int | None`, `strict_text_only: bool`,
  `static: StaticConfig | None`, `wordpress: WordPressConfig | None`

**Exceptions:**
- `SiteRelinkerError(Exception)` — base
- `ConfigError(SiteRelinkerError)`
- `InputError(SiteRelinkerError)`
- `BackendError(SiteRelinkerError)`

### M2: `url_utils.py`

**Functions:**
- `is_internal(url: str, domains: list[str]) -> bool`
  Classify a URL as internal/external. Handles `https://`, `http://`, `//`,
  and root-relative (`/...`) forms.
- `normalize_to_relative(url: str, domains: list[str]) -> str`
  Strip domain from internal URL, return root-relative path. Raise ValueError
  for external URLs.
- `resolve_relative(base_url: str, href: str) -> str`
  Resolve a potentially relative href against a base URL.
- `extract_domain(url: str) -> str | None`
  Return the domain portion of a URL, or None for relative URLs.
- `sanitize_classes(classes: list[str]) -> list[str]`
  Validate CSS class names (alphanumeric + hyphen + underscore). Raise
  `ConfigError` on invalid names.

### M3: `html_ops.py`

**Classes:**
- `ContentScope` — resolves a `ScopeDefinition` against a parsed document,
  returns the BeautifulSoup tag subtree to operate on
- `AnchorMatcher` — finds anchor text occurrences in text nodes, respecting
  word boundaries and case-insensitivity; implements match-strategy logic
- `LinkManipulator` — stateless operations class:
  - `add_link(scope, anchor, target_url, config) -> OperationResult`
  - `replace_link(scope, anchor, target_url, config) -> OperationResult`
  - `remove_link(scope, anchor, config) -> OperationResult`
  - `scan_link(scope, anchor, config) -> ScanResult`

**Top-level function:**
- `process_operation(html: str, operation: LinkOperation, config: AppConfig) -> tuple[str, OperationResult]`
  Parse HTML → scope → match → manipulate → serialize back. Returns
  (modified_html, result). In dry-run mode, returns (original_html, result)
  with appropriate status.

### M4: `csv_io.py`

**Functions:**
- `parse_csv(path: Path) -> list[LinkOperation]`
  Read CSV, validate headers, parse each row into a `LinkOperation`. Collect
  all validation errors and raise `InputError` with a summary if any exist.
- `write_scan_results(results: list[ScanResult], output: Path | None) -> None`
  Write scan CSV to file or stdout.
- `write_dry_run_report(results: list[OperationResult], output: Path | None) -> None`
  Write dry-run CSV to file or stdout.

### M5: `reporter.py`

**Classes:**
- `Reporter` — accepts a list of `OperationResult`, formats output:
  - `format_human() -> str` — readable table for stderr
  - `format_csv(output: Path | None) -> None` — CSV to file or stdout
  - `format_json(output: Path | None) -> None` — JSON for programmatic use
  - `summary() -> str` — one-line summary: "Modified 14, skipped 3, errors 2"

### M6: `backend_static.py`

**Classes:**
- `StaticSiteBackend`:
  - `__init__(config: AppConfig)` — validate web_root exists, create output_dir
  - `resolve_url(url: str) -> Path` — URL path → filesystem path
  - `process_operations(operations: list[LinkOperation]) -> list[OperationResult]`
    — iterate ops grouped by URL, read file once per URL, apply all ops for
    that URL, write modified file to output_dir
  - Uses `html_ops.process_operation` for each individual operation

### M7: `backend_wordpress.py`

**Classes:**
- `WordPressBackend`:
  - `__init__(config: AppConfig)` — establish DB connection, read permalink
    structure
  - `resolve_url(url: str) -> int` — URL path → post_id
  - `process_operations(operations: list[LinkOperation]) -> list[OperationResult]`
    — group by URL, fetch post_content, apply ops, write back in transaction
  - `_read_permalink_structure() -> str` — query wp_options
  - `_build_slug_map() -> dict[str, int]` — reverse permalink map
  - `_backup_rows(post_ids: list[int]) -> None` — dump to backup table

### M8: `cli.py`

**Functions:**
- `build_parser() -> argparse.ArgumentParser` — define all CLI arguments
  with subcommands or mode flags
- `load_config(args: argparse.Namespace) -> AppConfig` — merge CLI args with
  env vars / `.env` file, validate, return `AppConfig`
- `main() -> int` — orchestration: parse args → load config → read CSV →
  instantiate backend → process operations → report results → return exit code

---

## Testing Strategy

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_models.py           # M1 tests
├── test_url_utils.py        # M2 tests
├── test_html_ops.py         # M3 tests
├── test_csv_io.py           # M4 tests
├── test_reporter.py         # M5 tests
├── test_backend_static.py   # M6 tests
├── test_backend_wordpress.py# M7 tests
└── test_cli.py              # M8 tests
```

### conftest.py Fixtures

```python
# Factory fixtures for common test objects
@pytest.fixture
def make_operation() -> Callable[..., LinkOperation]: ...

@pytest.fixture
def make_config() -> Callable[..., AppConfig]: ...

@pytest.fixture
def sample_html() -> str:
    """Realistic HTML page with scoped content areas."""
    ...

@pytest.fixture
def sample_html_with_links() -> str:
    """HTML with pre-existing internal and external links."""
    ...

@pytest.fixture
def tmp_site(tmp_path: Path) -> Path:
    """Create a temporary static site structure with sample HTML files."""
    ...

@pytest.fixture
def csv_file(tmp_path: Path) -> Callable[..., Path]:
    """Factory to create temporary CSV files with given rows."""
    ...
```

### Named Test Cases by Module

**test_models.py (11 tests):**
1. `test_link_operation_valid_add` — all required fields for add
2. `test_link_operation_valid_remove` — remove without target_url
3. `test_link_operation_missing_target_url_for_add` — validation error
4. `test_link_operation_invalid_operation` — unknown operation string
5. `test_scope_definition_element_id` — valid element_id scope
6. `test_scope_definition_empty_is_whole_body` — blank defaults
7. `test_app_config_domains_required` — must have at least one domain
8. `test_app_config_match_strategy_nth_requires_n` — NTH needs match_n
9. `test_static_config_paths_validated` — web_root must be absolute or resolvable
10. `test_wordpress_config_from_env` — env var fallback
11. `test_custom_exceptions_hierarchy` — all inherit SiteRelinkerError

**test_url_utils.py (12 tests):**
1. `test_is_internal_https_match` — `https://example.com/page` with domain `example.com`
2. `test_is_internal_http_match` — http variant
3. `test_is_internal_protocol_relative` — `//example.com/page`
4. `test_is_internal_root_relative` — `/page.html` always internal
5. `test_is_internal_external_url` — `https://other.com/page` → False
6. `test_is_internal_subdomain` — `sub.example.com` not matching `example.com`
7. `test_normalize_strips_domain` — full URL → root-relative
8. `test_normalize_preserves_path_and_query` — keeps query string and fragment
9. `test_normalize_external_raises` — ValueError for external URLs
10. `test_resolve_relative_absolute_href` — absolute href returned as-is
11. `test_resolve_relative_path` — relative path resolved against base
12. `test_sanitize_classes_rejects_invalid` — `class!name` → ConfigError

**test_html_ops.py (20 tests):**
1. `test_scope_element_id_found` — scopes to correct element
2. `test_scope_element_id_missing` — returns scope_not_found
3. `test_scope_below_boundary` — content after boundary only
4. `test_scope_above_boundary` — content before boundary only
5. `test_scope_whole_body` — full body when no scope defined
6. `test_anchor_match_case_insensitive` — "Help" matches "help"
7. `test_anchor_match_word_boundary` — "link" doesn't match "linking"
8. `test_anchor_match_at_start_of_text` — boundary at text node start
9. `test_anchor_match_at_end_of_text` — boundary at text node end
10. `test_strict_text_only_skips_linked` — doesn't match inside existing `<a>`
11. `test_add_link_basic` — wraps anchor in `<a>` with correct href and classes
12. `test_add_link_normalizes_internal_url` — domain stripped on insertion
13. `test_add_link_external_url_gets_rel` — rel=noopener noreferrer added
14. `test_add_link_already_linked_skip` — if_linked=skip leaves unchanged
15. `test_add_link_already_linked_replace` — if_linked=replace updates href
16. `test_add_link_already_linked_error` — if_linked=error records error
17. `test_replace_link_updates_href` — existing link href changed
18. `test_replace_link_not_linked` — anchor not in `<a>` → error
19. `test_remove_link_with_class_filter` — only removes matching classes
20. `test_remove_link_preserves_text` — anchor text remains after removal
21. `test_scan_finds_linked_anchor` — reports linked=True with target URL
22. `test_scan_finds_unlinked_anchor` — reports linked=False
23. `test_scan_counts_occurrences` — occurrence_count correct
24. `test_match_strategy_first` — only first occurrence affected
25. `test_match_strategy_all` — all occurrences affected
26. `test_match_strategy_nth` — only Nth occurrence affected
27. `test_dry_run_no_modification` — html unchanged, status is would_*

**test_csv_io.py (8 tests):**
1. `test_parse_valid_csv` — all columns, multiple rows
2. `test_parse_minimal_csv` — only required columns
3. `test_parse_missing_required_column` — InputError raised
4. `test_parse_invalid_operation_value` — InputError with row number
5. `test_parse_add_without_target_url` — InputError
6. `test_parse_empty_csv` — InputError (no data rows)
7. `test_write_scan_results_to_file` — CSV output matches expected format
8. `test_write_dry_run_report_to_stdout` — output captured correctly

**test_reporter.py (6 tests):**
1. `test_format_human_mixed_results` — readable table with all status types
2. `test_format_csv_output` — valid CSV with headers
3. `test_format_json_output` — valid JSON array
4. `test_summary_counts` — "Modified 3, skipped 2, errors 1"
5. `test_empty_results` — graceful handling of no operations
6. `test_summary_all_success` — clean message when everything worked

**test_backend_static.py (10 tests):**
1. `test_resolve_url_to_file` — URL path → correct filesystem path
2. `test_resolve_url_missing_file` — BackendError raised
3. `test_resolve_url_wrong_extension` — skipped if not in extensions list
4. `test_process_single_operation` — file read, modified, written to output_dir
5. `test_process_preserves_directory_structure` — nested paths mirrored
6. `test_process_groups_by_url` — multiple ops on same URL read file once
7. `test_output_dir_created_if_missing` — auto-creates output tree
8. `test_copy_unchanged_flag_off` — unmodified files not copied
9. `test_copy_unchanged_flag_on` — unmodified files copied
10. `test_encoding_respected` — non-UTF-8 file read correctly

**test_backend_wordpress.py (8 tests, all using mocked DB):**
1. `test_read_permalink_structure` — reads from wp_options mock
2. `test_build_slug_map_postname` — `/%postname%/` pattern resolved
3. `test_build_slug_map_year_month` — `/%year%/%monthnum%/%postname%/` resolved
4. `test_resolve_url_to_post_id` — URL → correct post_id
5. `test_resolve_url_not_found` — BackendError for unknown URL
6. `test_process_operations_with_transaction` — commit on success
7. `test_process_operations_rollback_on_error` — rollback on failure
8. `test_backup_table_creation` — backup rows dumped before modification

**test_cli.py (8 tests):**
1. `test_build_parser_static_mode` — all static flags parsed
2. `test_build_parser_wordpress_mode` — all WP flags parsed
3. `test_load_config_from_args` — args → AppConfig correctly
4. `test_load_config_env_fallback` — env vars fill missing DB args
5. `test_main_dry_run_static` — end-to-end with tmp_site, dry-run
6. `test_main_execute_static` — end-to-end with tmp_site, real execution
7. `test_main_bad_csv_exit_code_1` — exit code 1 on input error
8. `test_main_missing_web_root_exit_code_2` — exit code 2 on backend error

---

## Development Steps

Each step lists its file deliverables and verification commands. Complete all
verification before requesting confirmation to proceed.

### Step 1: Project Scaffolding

**Deliverables:**
- `pyproject.toml` with project metadata, dependencies, optional `[wordpress]`
  extra, dev dependencies, ruff/mypy configuration
- `site_relinker/__init__.py` (version string, top-level docstring)
- `tests/__init__.py`
- `tests/conftest.py` with all shared fixtures listed above
- `.env.example` with placeholder WP_DB_* variables
- Directory structure in place

**Dependencies in pyproject.toml:**
```
[project]
requires-python = ">=3.10"
dependencies = [
    "beautifulsoup4>=4.12,<5",
    "lxml>=5.0,<6",
    "pydantic>=2.0,<3",
    "python-dotenv>=1.0,<2",
]

[project.optional-dependencies]
wordpress = ["PyMySQL>=1.1,<2"]
dev = [
    "pytest>=8.0,<9",
    "pytest-cov>=5.0,<6",
    "mypy>=1.10,<2",
    "ruff>=0.4,<1",
    "lxml-stubs>=0.5",
]
```

**Verification:**
```bash
pip install -e ".[dev]" --break-system-packages
python -c "import site_relinker; print(site_relinker.__version__)"
pytest tests/ --co -q  # collect-only to verify conftest loads
```

### Step 2: Data Models & Exceptions (`models.py`)

**Deliverables:**
- `site_relinker/models.py` — all enums, Pydantic models, and exceptions
- `tests/test_models.py` — 11 named test cases

**Verification:**
```bash
pytest tests/test_models.py -v
mypy site_relinker/models.py --strict
```

### Step 3: URL Utilities (`url_utils.py`)

**Deliverables:**
- `site_relinker/url_utils.py` — all URL functions
- `tests/test_url_utils.py` — 12 named test cases

**Verification:**
```bash
pytest tests/test_url_utils.py -v
mypy site_relinker/url_utils.py --strict
```

### Step 4: CSV I/O & Reporter (`csv_io.py`, `reporter.py`)

**Deliverables:**
- `site_relinker/csv_io.py` — CSV parsing and output functions
- `site_relinker/reporter.py` — result formatting class
- `tests/test_csv_io.py` — 8 named test cases
- `tests/test_reporter.py` — 6 named test cases

**Verification:**
```bash
pytest tests/test_csv_io.py tests/test_reporter.py -v
mypy site_relinker/csv_io.py site_relinker/reporter.py --strict
```

### Step 5: HTML Operations — Scoping & Matching (`html_ops.py` part 1)

**Deliverables:**
- `site_relinker/html_ops.py` — `ContentScope` class, `AnchorMatcher` class
  (scope resolution + anchor finding only; `LinkManipulator` is Step 6)
- `tests/test_html_ops.py` — test cases 1–10 (scoping and matching tests)

**Verification:**
```bash
pytest tests/test_html_ops.py -v -k "scope or match or strict"
mypy site_relinker/html_ops.py --strict
```

### Step 6: HTML Operations — Link Manipulation (`html_ops.py` part 2)

**Deliverables:**
- `site_relinker/html_ops.py` — complete `LinkManipulator` class and
  `process_operation` top-level function
- `tests/test_html_ops.py` — test cases 11–27 (add, replace, remove, scan,
  strategy, dry-run)

**Verification:**
```bash
pytest tests/test_html_ops.py -v
mypy site_relinker/html_ops.py --strict
```

### Step 7: Static Site Backend (`backend_static.py`)

**Deliverables:**
- `site_relinker/backend_static.py` — `StaticSiteBackend` class
- `tests/test_backend_static.py` — 10 named test cases (using `tmp_site`
  fixture, real filesystem operations)

**Verification:**
```bash
pytest tests/test_backend_static.py -v
mypy site_relinker/backend_static.py --strict
```

### Step 8: WordPress Backend (`backend_wordpress.py`)

**Deliverables:**
- `site_relinker/backend_wordpress.py` — `WordPressBackend` class
- `tests/test_backend_wordpress.py` — 8 named test cases (all DB interactions
  mocked with `unittest.mock.patch`)

**Verification:**
```bash
pytest tests/test_backend_wordpress.py -v
mypy site_relinker/backend_wordpress.py --strict
```

### Step 9: CLI Wiring (`cli.py`)

**Deliverables:**
- `site_relinker/cli.py` — argument parser, config loader, main orchestration
- `tests/test_cli.py` — 8 named test cases (including end-to-end with
  tmp_site)
- Update `pyproject.toml` with `[project.scripts]` entry point:
  `site-relinker = "site_relinker.cli:main"`

**Verification:**
```bash
pytest tests/test_cli.py -v
mypy site_relinker/cli.py --strict
site-relinker --help  # smoke test the CLI entry point
```

### Step 10: Integration Tests & README

**Deliverables:**
- `tests/test_integration.py` — 3-4 end-to-end scenarios:
  1. Full CSV with mixed add/replace/remove/scan on a tmp static site
  2. Dry-run produces correct report without modifying source
  3. Scan-only operation outputs correct CSV
  4. Error handling: bad CSV + missing files produce correct exit codes
- `README.md` — project description, installation, usage examples (static and
  WordPress modes), CSV format reference, CLI flag reference
- Final full test suite run with coverage

**Verification:**
```bash
pytest tests/ -v --cov=site_relinker --cov-report=term-missing
mypy site_relinker/ --strict
ruff check site_relinker/ tests/
```

---

## CLI Usage Reference (Target Interface)

```
site-relinker --mode static \
    --csv operations.csv \
    --domains example.com,www.example.com \
    --web-root /var/www/html \
    --output-dir /tmp/relinked \
    --link-classes inner-link,batch-2024 \
    --match-strategy first \
    --if-linked skip \
    --dry-run

site-relinker --mode wordpress \
    --csv operations.csv \
    --domains example.com \
    --db-host localhost \
    --db-name wp_production \
    --db-user wp_admin \
    --table-prefix wp_ \
    --post-types post,page \
    --backup-table \
    --dry-run
```
