# DNS field station

Code-led research app for curious developers. An ivory paper surface, forest ink, Georgia headings, rule-separated navigation, and mathematical specimens give the document the feel of a field notebook. Native controls keep the transport experiment inspectable. No remote fonts or image assets; no entrance animation.

## Implemented tokens

| Role | Value |
| --- | --- |
| Paper / ink / muted text | `#f5f2e9` / `#193d35` / `#53685e` |
| Action and focus / divider | `#a53622` / `#b9c4b8` |
| Notice and code surface / hover and revealed tile | `#e5e9df` / `#e0e7d7` |
| Matched tile / selection | `#d2ddaa` / `#d6dfbc` |
| Body / headings / data | system sans / Georgia / UI monospace |
| App body / intro / data | `17px/1.65` / `22px` / `14px` |
| App H1 / H2 / H3 | `clamp(44px,6vw,78px)` / `36px` / `25px` |
| Control radius / column gap | `4px` / `48px` |

## App layout and states

Header, main, and footer share a `1180px` maximum width and `24px 36px` padding. The station hero and atlas use two equal columns; circular illustrations fill their column. H1 text is limited to `13ch`, introductory text to `45ch`, and paragraphs to `69ch`. At viewport widths of `700px` or less, columns stack with a `20px` gap, outer padding becomes `20px`, navigation wraps below the wordmark, H1 becomes `50px`, and the hero image is capped at `430px`.

Hash navigation reveals one of Station, Atlas, Notebook, Packet pairs, or Resolver lab. The active link has a vermilion underline and `aria-current`. Notebook search hides nonmatching articles and announces the result count, including zero. The game remains a four-column grid (maximum `600px`): numbered dark tiles become pale when revealed and yellow-green when matched; matched tiles are disabled. Move and pair counts announce progress and completion. Unmatched pairs turn back after `800ms`.

Resolver lab starts with “No query sent yet” and a raw-answer placeholder. Querying disables its button; completion shows elapsed time, DNS status, and raw JSON. Failure shows a persistent retry suggestion. A skip link and native keyboard controls support navigation. App focus rings are `3px` vermilion with `4px` offset. Controls use visible borders; state changes also use text, attributes, or disabled behavior.

## Bootstrap layout and states

The loader uses the same palette and `4px` control radius, with `15px/1.5` body text and a `28px` Georgia title. Its header has `18px 25px` padding. A wrapping flex form with `12px` gaps contains namespace, resolver, concurrency, load, and trace-export controls. Inputs are `290px` wide with an `80vw` cap; the integrity-pin field requests `620px` within that cap. A full-width `5px` vermilion progress bar separates transport controls from the borderless `85vh` app iframe. Collapsible transport details hold the pin and a scrollable trace capped at `220px`. Focus uses a `3px` ring and `3px` offset.

The ready state explicitly promises no local fallback. Loading clears the iframe, disables Load, and reports manifest retrieval followed by completed chunk counts. Only verified, decompressed content enters the sandboxed iframe. Success reports document bytes, query count, and elapsed time. Failure preserves an actionable message and re-enables Load; trace export remains available. Status messages use a polite live region.

## Evidence boundary

`evidence/desktop.png` and `evidence/mobile.png` document fixture rendering, not successful live DNS deployment. Real DNS deployment is blocked. The design record captures the current implementation; it does not establish live resolver performance or publication success.
