# Problem: S3 links in Slack are not clickable

**Author**: Emmanuel Joliet
**Date**: 2026-11-11
**Status**: Draft

## Problem Statement

People share `s3://bucket/prefix/key` links in Slack. Slack does not treat `s3://` as a link, so nothing happens on click.

Today I copy the path and open it another way (AWS console, CLI, a notebook). It works, but it breaks flow every time.

The buckets live in my AWS account and are **private**. Any solution must keep them private.

## Desired Experience

1. I see an S3 link in Slack.
2. I click it.
3. A web page opens showing a file tree at that bucket/prefix, like a web file browser.
4. From there, for any file or folder, I can:
   - **Open with** a custom app from a menu, directly in the browser. Each menu entry maps to a configurable action, such as a specific Python command.
   - **Download** the file locally.

## Goals

- One click from a Slack message to a browsable view of the S3 location.
- File tree navigation: folders, files, size, last modified.
- Configurable "Open with" menu, keyed by file type or pattern.
- Local download of single files.
- Access limited to authenticated users with existing AWS permissions.

## Non-Goals

- Making buckets or objects public.
- Uploading, deleting, or editing objects.
- Replacing the AWS console for bucket administration.

## Constraints

| Constraint | Detail |
|------------|--------|
| Privacy | Buckets stay private. No public bucket policies or long-lived public URLs. |
| Auth | The browser must act with my AWS identity, or a role scoped to the shared buckets. |
| Slack | Slack only makes `http(s)://` text clickable. The desktop app cannot be modified by a browser extension. |
| Link origin | Other people post the links. I cannot rely on them changing how they paste. |

## Feasibility

Yes, this is possible. It splits into three independent parts.

| Part | Problem | Possible approaches |
|------|---------|---------------------|
| 1. Click | Turn `s3://...` in Slack into something clickable | Slack app that replies with an `https://` link; Slack message shortcut ("Open in S3 browser"); browser extension that rewrites links (Slack web only) |
| 2. Browse | Show a private bucket as a file tree | Small web app that lists objects with my AWS credentials, hosted locally or behind single sign-on |
| 3. Act | Open or download a file | Short-lived presigned URLs for download; "Open with" entries that launch a viewer URL or run a registered command |

> ⚠️ Part 3 is the hard one. A web page cannot run an arbitrary Python command on my laptop. It needs either a local helper process, or a server-side runner (for example a notebook or viewer service) that the menu links to.

## Answers So Far

| Question | Answer |
|----------|--------|
| Slack app install | Possible, but a workspace admin must approve it. |
| AWS auth | Kion. Its API returns short-term keys, which I export as environment variables. |
| File sizes | A few KB up to multi-GB. |
| ASDF | Open with `pixel-clarity`. |
| FITS | Open with Caltech-IPAC Firefly (`show_data`) or the Jupyter Firefly extension. |
| ASCII / text | Open in a markdown or text editor. |

## Findings: Where Python Runs

Pyodide does run Python in the browser. It does not fit this problem, for four reasons.

| Limit | Why it matters here |
|-------|---------------------|
| 2 GB memory cap (32-bit WebAssembly) | Files reach multi-GB. |
| Requests go through the browser | Every bucket would need CORS rules. |
| No native processes or sockets | `pixel-clarity` ships a server-side Node.js process. Firefly is a Java server. Neither runs in Pyodide. |
| Credentials would live in the page | Kion keys should stay in a process on my machine. |

Marimo's browser-only (WebAssembly) mode is Pyodide, so it has the same limits.

**Conclusion**: run a small Python process on my laptop. It reads the Kion keys from the environment, the same way the CLI does today. The browser is only the display.

## Findings: Tool Fit

| Need | Tool | Status |
|------|------|--------|
| File tree | Marimo run locally: `mo.ui.file_browser(initial_path=S3Path("s3://..."))` via `cloudpathlib` | Documented. Cloud listings default to 50 entries; `limit` raises it. |
| Deep link from Slack | `mo.query_params()` reads `?path=s3://...` from the URL | Documented. |
| ASDF | `pixel_clarity.popup("s3://...")` opens a browser tab from any Python program | Documented. Reads S3 by range requests, so multi-GB is fine. Needs `pixel-clarity[s3]`. |
| FITS | `firefly_client` `show_fits` / `show_data` against a local Firefly (`ipac/firefly` Docker image, `localhost:8080/firefly`), given a presigned URL | API documented. **Unverified**: whether Firefly copies the whole file first. |
| FITS fallback | `pixel-clarity` also reads FITS by range requests | Documented. |
| Text | Render inline in the Marimo page | Fine for small files; cap the size. |
| Download | Presigned URL, opened by the browser | Standard. Streams, so size is not a problem. |

> 💡 Marimo covers the tree, the deep link, and the "Open with" menu in one local app. It is a reasonable first prototype.

> ⚠️ Unverified: showing `pixel-clarity` **inline** in Marimo. Its docs name JupyterLab 4 / Notebook 7 with ipywidgets 8, not Marimo. `popup()` avoids the question.

## Risks

- **Slack still needs an `https://` or `http://` link.** The Slack app must turn `s3://...` into `http://localhost:<port>/?path=s3://...`. That only works on a machine running the local app.
- **Admin approval** may take time or be refused. A fallback without Slack changes is needed (paste box in the app, or a browser extension for Slack on the web).
- **Kion keys expire.** The app must detect expired keys and say so. Presigned URLs die with the keys that signed them.
- **Local-only by design.** Teammates would each run their own copy with their own keys.

## Open Questions

- [ ] Slack desktop app, Slack in the browser, or both?
- [ ] Just me, or teammates too?
- [ ] Does Firefly stream a multi-GB FITS from a presigned URL, or download it all first?
- [ ] Does Slack make `http://localhost:...` links clickable in the desktop app?
- [ ] How long do the Kion keys last?

## Next Steps

1. Prototype the Marimo app locally: `?path=` deep link, S3 tree, download.
2. Add "Open with": `pixel-clarity` popup for ASDF, local Firefly for FITS, inline view for text.
3. Test both viewers on a multi-GB file.
4. Draft the Slack app request for admin approval, with the minimum scopes.

## References

- [Pyodide WebAssembly constraints](https://pyodide.readthedocs.io/en/stable/usage/wasm-constraints.html)
- [Marimo WebAssembly notebooks](https://docs.marimo.io/guides/wasm/)
- [Marimo file browser](https://docs.marimo.io/api/inputs/file_browser/)
- [Marimo query parameters](https://docs.marimo.io/api/query_params/)
- [pixel-clarity on PyPI](https://pypi.org/project/pixel-clarity/)
- [firefly_client API](https://caltech-ipac.github.io/firefly_client/api/firefly_client.FireflyClient.html)
- [jupyter-firefly-extensions on PyPI](https://pypi.org/project/jupyter-firefly-extensions/)
- [Slack link unfurling](https://docs.slack.dev/messaging/unfurling-links-in-messages/)
