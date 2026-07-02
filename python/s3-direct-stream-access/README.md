# S3 Lazy Streaming — ASDF Metadata Demo

Demonstrates that opening a large ASDF file from S3 streams **only the header/metadata** — not the full file.
A 207 MB Roman Space Telescope calibration file is used.

## Examples

| Script | Mechanism | Bytes counter |
|--------|-----------|---------------|
| `s3example.py` | Custom `S3RangeReader` (boto3 Range GETs) | Yes |
| `s3fsexample.py` | `s3fs` + counting wrapper | Yes |
| `s3nativeexample.py` | `asdf.open("s3://…")` via fsspec | Yes — patches `s3fs.S3File._fetch_range` (network layer) |

All three fetch **~89 KB of a 207 MB file (0.04%)** — proof that `asdf.open` with `lazy_load=True` streams only the header/tree from S3.

> ⚠️ Pitfall: with s3fs default settings (`readahead` cache, fill enabled), the native `s3://` path fetches ~50% of the file — every block-header peek pulls a 5 MB readahead block. Disable it via `fsspec.config.conf["s3"] = {"default_fill_cache": False, "default_cache_type": "none"}` (see `s3nativeexample.py`).

## Install

**uv (recommended)**

```bash
uv venv && source .venv/bin/activate
uv pip install asdf boto3 s3fs
```

**pip**

```bash
python -m venv .venv && source .venv/bin/activate
pip install asdf boto3 s3fs
```

> `fsspec` is pulled in automatically as an `s3fs` dependency.

## Run

```bash
python s3example.py        # boto3 Range GETs, shows bytes fetched
python s3fsexample.py      # s3fs, shows bytes fetched
python s3nativeexample.py  # asdf native s3:// URI, shows bytes fetched
```

All examples access a public NASA bucket — no AWS credentials required.
