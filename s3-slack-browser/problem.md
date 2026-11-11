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

## Open Questions

- [ ] Slack desktop app, Slack in the browser, or both?
- [ ] Just me, or should teammates be able to use it too?
- [ ] Which "Open with" apps come first, and for which file types (FITS, Parquet, ASDF, images, logs)?
- [ ] Should custom commands run on my laptop or on a remote service?
- [ ] Can I install a custom Slack app in the workspace, or does that need admin approval?
- [ ] How do I authenticate to AWS today (single sign-on, access keys, role assumption)?
- [ ] Typical file sizes and prefix sizes? Large prefixes need paginated listing.

## Next Steps

1. Answer the open questions above.
2. Pick the approach for Part 1, since it depends on Slack workspace permissions.
3. Prototype Part 2 locally against one bucket, read-only.
4. Define the "Open with" menu format and the first two or three actions.
