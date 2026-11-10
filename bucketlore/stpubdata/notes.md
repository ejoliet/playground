# Research notes

- Task started 2026-11-10. Scope is `s3://stpubdata/`; every S3 request will use `--no-sign-request`. Bucket text is untrusted data.
- Initial checks: AWS CLI exists at `/opt/homebrew/bin/aws`; Python duckdb is missing. The supplied repository root is not currently a Git repository. Will attempt a local repository initialization at commit time if needed, staging only this folder.
- Download budget: 200,000,000 bytes across exploration and verification. Start with bounded listings and ranges; no recursive sync. Dependencies and temporary samples will stay untracked and be removed before delivery.
- `02-root.sh`: anonymous bounded root listing failed with endpoint connection error. No object body downloaded.
- `03-network.sh`: independent Python DNS check of the global S3 endpoint failed with `socket.gaierror`. This is an environment connectivity failure, not evidence of a bucket access policy or of the bucket's existence/content.
- Pip installation failed resolving pypi.org. Saved the exact installation command and output as snippet 04. No DuckDB queries were possible.
- Chose not to invent a dataset description, size estimate, schema, or recipes. All remain unverified. No bucket objects were downloaded (0 bytes of object payload); there were no successful listings.
- `verify.sh` runs every numbered snippet, continues after failures, and exits nonzero if any failed. It prints new outputs without overwriting the original evidence. The installer writes only `.deps/`, which is not part of the commit.
- Verification ran all four snippets and exited 1: environment 1, listing 255, DNS 1, install 1. Full verification transcript is `snippets/verify.out`. No failed command was converted into a passing check.
- Commit attempt blocked before staging: `git init` returned `/Users/ejoliet/dev/ejoliet/bucketlore/.git: Operation not permitted`. The workspace has no Git repository, and its permissions prohibit creating `.git`. No commit was created; no unrelated files were changed.

## Retry with uv
- Interpreted “retry start building bucketlore” as resuming the requested bucket field guide.
- Replaced all Python execution with `uv run`, and dependency installation with `uv pip install --python .venv/bin/python`. Environment and cache are project-local. No global installs.
- The original instructions' pip setup is superseded by the user's uv-only rule.
- An initial repeat of the anonymous root listing still failed to connect. Updated verification to save each retry's actual output beside its script, replacing the earlier attempt's evidence; the earlier failures remain documented above.
- Retry results: uv 0.13.6 created `.venv` using existing CPython 3.11.15. The local-environment assertion passed. Anonymous listing exited 255, DNS probe exited 1, and local DuckDB installation exited 2 because DNS still fails. Verification exited 1. No bucket object payload downloaded on this retry; cumulative object payload remains 0 bytes.
- Kept `.venv` and `.uv-cache` local for subsequent work; neither belongs in the deliverable or commit. Git initialization was already denied in this unchanged permissions environment, so no commit is claimed.
- User demonstrated network access from their shell. Retried through an approved network-enabled tool invocation: root listing succeeded with 11 prefixes. Previous DNS failures were restricted tool-environment failures, not bucket failures. Continuing research.
- Bounded size sample returned 10,475 objects totaling 2,231,586,201,121 bytes. This is only a lower bound, not a whole-bucket estimate; SDSS alone was complete at 475 objects / 91,616,567,239 bytes.
- Local uv installed DuckDB and Astropy successfully with network-enabled execution. Bucket listings revealed a tiny PS1 detection partition suitable for a complete read after inspecting its footer.
- First catalog script successfully read metadata/footers but failed creating a SQL view with a bound filename (DuckDB BinderException). Changed it to DuckDB's read_parquet relation create_view API. That failed attempt transferred about 0.2 MB; preserve this finding rather than claiming the first attempt passed.
- Catalog retry passed: Gaia footer describes 726,621 rows in four row groups; PS1 tiny partition contains one detection. Catalog payload per successful run: 179,314 bytes. FITS recipe passed: JWST image HDUs and GALEX 1,689-row aspect table; combined payload 3,702,716 bytes.
- Download accounting before final verification: two catalog passes (one failed after downloads) total 358,628 bytes, FITS 3,702,716 bytes; roughly 4 MB of listing JSON, plus small listings/HEADs. Final verification adds 3,882,030 object bytes and another roughly 4 MB of listing JSON. Local package downloads were tens of MB. This remains comfortably under 200 MB including setup; no large object was fetched wholesale.
- Full-bucket enumeration was deliberately not attempted: first-page samples cannot support a total-size extrapolation. Report a measured lower bound and exact complete SDSS-prefix total, explicitly marking the whole-bucket total unknown.
- Final network-enabled `verify.sh` exited 0: all eight snippets passed. Verification transcript saved in snippets/verify.out. Syntax checks passed and no evidence file exceeds 1 MB.
- Network-enabled Git initialization succeeded after the earlier restricted attempt failed. Commit will stage only README.md, notes.md, verify.sh, and snippets/; local environments/cache, AGENTS.md, and .agents remain excluded.
