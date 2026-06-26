# site-relinker

Batch manipulation of internal links across static HTML sites and WordPress
(MySQL) installations. Reads a CSV file describing link operations (add,
replace, remove, scan) and applies them to scoped content areas within target
pages, with full dry-run support.

## Installation

```bash
pip install -e .
```

For WordPress support (requires PyMySQL):

```bash
pip install -e ".[wordpress]"
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

### Static Site Mode

Process link operations on a static HTML site. Modified files are written to a
separate output directory; source files are never modified.

```bash
site-relinker --mode static \
    --csv operations.csv \
    --domains example.com,www.example.com \
    --web-root /var/www/html \
    --output-dir /tmp/relinked \
    --link-classes inner-link,batch-2024 \
    --match-strategy first \
    --if-linked skip \
    --dry-run
```

### WordPress Mode

Process link operations on WordPress post content via MySQL. Changes are
wrapped in a database transaction with optional backup table creation.
Database credentials can be provided via CLI flags or environment variables
(`WP_DB_HOST`, `WP_DB_PORT`, `WP_DB_USER`, `WP_DB_PASSWORD`, `WP_DB_NAME`)
or a `.env` file.

```bash
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

## CSV Format

| Column           | Required       | Description                                 |
|------------------|----------------|---------------------------------------------|
| `operation`      | yes            | `add`, `replace`, `remove`, `scan`          |
| `url`            | yes            | Page URL / path                             |
| `anchor`         | yes            | Text to find                                |
| `target_url`     | for add/replace| Link destination                            |
| `scope_type`     | no             | `element_id`, `above`, `below`, or blank    |
| `scope_value`    | no             | Element ID or boundary string               |
| `if_linked`      | no             | Per-row override: `skip`, `error`, `replace`|
| `max_occurrences`| no             | Per-row override for match strategy         |

Example:

```csv
operation,url,anchor,target_url,scope_type,scope_value
add,/index.html,Click here,/target.html,element_id,main-content
replace,/about.html,learn more,/new-page.html,,
remove,/help.html,old link,,,
scan,/index.html,contact us,,,
```

## Operations

- **add** -- Wrap found anchor text in an `<a>` tag pointing to the target URL.
- **replace** -- Change the `href` of an existing `<a>` tag around the anchor.
- **remove** -- Strip an `<a>` tag from around the anchor, leaving the text.
- **scan** -- Search for anchor text and report its link status.

## CLI Reference

### Required Arguments

| Flag        | Description                              |
|-------------|------------------------------------------|
| `--mode`    | Backend: `static` or `wordpress`         |
| `--csv`     | Path to the CSV operations file          |
| `--domains` | Comma-separated list of internal domains |

### Common Options

| Flag               | Default   | Description                                  |
|--------------------|-----------|----------------------------------------------|
| `--dry-run`        | off       | Preview changes without modifying anything   |
| `--link-classes`   | *(none)*  | Comma-separated CSS classes for new links    |
| `--link-target`    | *(none)*  | Target attribute (e.g. `_blank`)             |
| `--if-linked`      | `skip`    | Policy for already-linked anchors            |
| `--match-strategy` | `first`   | `first`, `all`, `any`, or N (1-based int)    |
| `--cross-tag-match`| off       | Match across inline child elements           |
| `--output`         | stdout    | Output file for scan/dry-run reports         |

### Static Backend Options

| Flag              | Default           | Description                       |
|-------------------|-------------------|-----------------------------------|
| `--web-root`      | *(required)*      | Base directory for URL resolution  |
| `--output-dir`    | *(required)*      | Destination for modified files     |
| `--extensions`    | `html,htm,shtml`  | File extensions to process         |
| `--encoding`      | `utf-8`           | File encoding                      |
| `--copy-unchanged`| off               | Copy unmodified files to output    |

### WordPress Backend Options

| Flag              | Default     | Env Var          | Description             |
|-------------------|-------------|------------------|-------------------------|
| `--db-host`       | `localhost` | `WP_DB_HOST`     | Database host            |
| `--db-port`       | `3306`      | `WP_DB_PORT`     | Database port            |
| `--db-user`       | *(empty)*   | `WP_DB_USER`     | Database user            |
| `--db-password`   | *(empty)*   | `WP_DB_PASSWORD` | Database password        |
| `--db-name`       | *(empty)*   | `WP_DB_NAME`     | Database name            |
| `--table-prefix`  | `wp_`       |                  | WordPress table prefix   |
| `--post-types`    | `post,page` |                  | Post types to process    |
| `--post-statuses` | `publish`   |                  | Post statuses to include |
| `--backup-table`  | off         |                  | Create backup table      |

## Exit Codes

| Code | Meaning                                          |
|------|--------------------------------------------------|
| 0    | All operations completed (or dry-run done)       |
| 1    | Input error (bad CSV, missing columns, bad args) |
| 2    | Runtime error (file I/O failure, DB error)       |

## Content Scoping

Operations can target a specific subset of the page:

- **`element_id`** -- Operate within the element with the given `id`.
- **`above`** -- Operate in content above the first occurrence of a string.
- **`below`** -- Operate in content below the first occurrence of a string.
- *(blank)* -- Operate on the entire `<body>`.

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
mypy site_relinker/ --strict

# Linting
ruff check site_relinker/ tests/

# Coverage report
pytest tests/ -v --cov=site_relinker --cov-report=term-missing
```

## License

See LICENSE file for details.
