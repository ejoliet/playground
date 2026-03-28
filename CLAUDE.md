# CLAUDE.md — AI Assistant Guide for `ejoliet/playground`

This file provides context for AI assistants (Claude Code, Copilot, etc.) working in this repository.

## Repository Overview

This is a personal development playground for exploring Python patterns, astronomical data handling, microservices, and deployment tooling. It is **not a production application** — expect experimentation, incomplete code, and redundancy.

**Primary owner**: @ejoliet
**Tech stack**: Python 3.9, Flask, PostgreSQL, SQLite, Docker, Jenkins, astroquery, astropy, NumPy, Pandas

---

## Directory Structure

```
playground/
├── .github/
│   ├── CODEOWNERS                    # @ejoliet owns everything
│   └── pull_request_template.md      # Checklist-based PR template
├── data/                             # Sample astronomical data (FITS, TBL, XML, VOTable)
├── GRITSX/                           # Conference presentation PDF
├── caltech-library-workshop-python/  # Workshop reference material (SQL, Pandas topics)
├── jenkins/                          # Jenkins pipeline definitions
│   ├── demo.jenkinsfile              # Basic 3-stage pipeline demo
│   └── demo-s3-cp.jenkinsfile        # S3 file download pipeline
├── python/
│   ├── Dockerfile                    # Python 3.9-alpine with pyxb, lxml, psycopg2, pytest
│   ├── data-handler/                 # Abstract data handler module (core Python code)
│   │   ├── DataHandler.py            # Abstract base class (ABC pattern)
│   │   ├── DataConverter.py          # Composes two handlers for format conversion
│   │   ├── CvsDataHandler.py         # CSV file handler (Pandas)
│   │   ├── CsvJsonDataHandler.py     # CSV → JSON conversion (extends CSV handler)
│   │   ├── MyDataHandler.py          # PostgreSQL handler (psycopg2)
│   │   ├── test_data_handler.py      # Unit tests (pytest)
│   │   └── test_data_postgres_handler.py  # Postgres tests (unittest.mock)
│   └── microservice/
│       ├── Dockerfile                # Python 3.9-slim
│       ├── requirements.txt          # Flask, astroquery
│       ├── app.py                    # Flask name-resolver for Simbad & NED (canonical)
│       ├── hello-app.py              # Minimal Flask GET example
│       └── micro-resolver.py         # Duplicate of app.py (can be ignored)
└── tpv/
    ├── PTF-sample.fits               # Sample FITS file
    └── setTpv.py                     # Rewrites FITS header CTYPE to TPV projection
```

---

## Key Code Patterns

### Data Handler Module (`python/data-handler/`)

Uses the **Abstract Base Class (ABC)** pattern. All handlers extend `DataHandler`:

```python
from abc import ABC, abstractmethod

class DataHandler(ABC):
    @abstractmethod
    def read_data(self): ...
    @abstractmethod
    def write_data(self, data): ...
```

Concrete implementations:
| Class | File | Backend |
|---|---|---|
| `DatabaseDataHandler` | `DataHandler.py` | SQLite (`sqlite3`) |
| `AsciiFileDataHandler` | `DataHandler.py` | NumPy ASCII |
| `CsvFileDataHandler` | `CvsDataHandler.py` | Pandas CSV |
| `PostgresDataHandler` | `MyDataHandler.py` | psycopg2 |
| `CsvJsonDataHandler` | `CsvJsonDataHandler.py` | Pandas CSV → JSON |

`DataConverter` composes two handlers to pipe data between formats and enforces type-checking.

### Flask Microservice (`python/microservice/app.py`)

Name-resolver REST API for astronomical objects:

- `GET /simbad/<name>` → queries Simbad, returns `{"ra": ..., "dec": ...}`
- `GET /ned/<name>` → queries NED, returns `{"ra": ..., "dec": ...}`

**Known issue**: Host is hardcoded to `172.17.0.2` (Docker bridge IP). Use env vars if you refactor.

### FITS Header Tool (`tpv/setTpv.py`)

Uses `astropy.io.fits` to rewrite `CTYPE1`/`CTYPE2` keywords to TPV projection format.

---

## Development Workflows

### Running Tests

Tests live in `python/data-handler/`. Run with pytest:

```bash
cd python/data-handler
pytest test_data_handler.py -v
pytest test_data_postgres_handler.py -v   # requires mock or live Postgres
```

No root-level test runner or CI for tests. No `Makefile` or `tox.ini`.

### Docker

Each subdirectory with a `Dockerfile` is independently containerized:

```bash
# Python data-handler image
cd python
docker build -t playground-python .

# Microservice image
cd python/microservice
docker build -t playground-microservice .
docker run -p 5000:5000 playground-microservice
```

### Jenkins CI

Two pipeline files in `jenkins/`:
- `demo.jenkinsfile` — sanity-check pipeline (clean + echo)
- `demo-s3-cp.jenkinsfile` — downloads a file from S3 (`ejoliet-dummy` bucket)

No GitHub Actions workflows are configured.

### Installing Dependencies

No root `requirements.txt` or `pyproject.toml`. Install per-module:

```bash
pip install flask astroquery           # microservice
pip install psycopg2 pandas numpy      # data-handler
pip install astropy                    # tpv
```

---

## Conventions & Constraints

- **Branch to develop on**: `claude/add-claude-documentation-dUciV` (or as instructed per session)
- **Do not push to `main` directly** — use PRs with the provided template in `.github/pull_request_template.md`
- **PR template checklist**: tests pass, self-review done, comments added where needed
- **Code owner**: All files are owned by @ejoliet per `.github/CODEOWNERS`
- **No linter or formatter is configured** — match the surrounding style in each file
- **Python version**: 3.9 (pinned in Dockerfiles)
- **Duplicate files**: `micro-resolver.py` duplicates `app.py` — treat `app.py` as canonical
- **Hardcoded values**: Several files contain hardcoded IPs/paths — flag but don't auto-refactor unless asked

---

## Data Files (`data/`)

Sample astronomical datasets in various formats:
- `.tbl` — IPAC table format (Firefly, WISE, Kepler light curve)
- `.xml` / `.vot` — VOTable / VO XML (SCS, CDS, NED results)
- `.fits` — FITS image (PTF sample)

These are static reference files, not generated outputs.

---

## What NOT to Do

- Do not add production-hardening (env var validation, retry logic, auth) unless explicitly asked
- Do not consolidate `app.py` / `micro-resolver.py` unless asked
- Do not add a root `setup.py`, `pyproject.toml`, or CI workflow unless instructed
- Do not refactor working code for style; match existing patterns
- Do not create new directories or files speculatively
