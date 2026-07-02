# S3 Lazy Streaming — ASDF Metadata Demo

Demonstrates that opening a large ASDF file from S3 streams **only the header/metadata** — not the full file.
A 207 MB Roman Space Telescope calibration file is used; less than 0.05% of it is downloaded.

## Examples

| Script | Mechanism | Bytes counter |
|--------|-----------|---------------|
| `s3example.py` | Custom `S3RangeReader` (boto3 Range GETs) | Yes |
| `s3fsexample.py` | `s3fs` + counting wrapper | Yes |
| `s3nativeexample.py` | `asdf.open("s3://…")` via fsspec | No (asdf owns handle) |

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
python s3nativeexample.py  # asdf native s3:// URI, no custom wrappers
```

All examples access a public NASA bucket — no AWS credentials required.
