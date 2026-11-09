# curatevid

A local, CPU-only video curation CLI built on **ffmpeg, PySceneDetect and Faster-Whisper**. It exports H.264/AAC clips, a typed Parquet manifest of every candidate and its decision, and a survivors-only Parquet manifest. No video or audio is sent to an inference API. The first model download requires internet; `--offline` prevents model downloads during processing.

## Install and run

Python 3.10+ on Linux, with `ffmpeg` and `ffprobe` on PATH:

```bash
cd curatevid
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
curatevid /path/to/one.mp4 /path/to/two.mp4 -o runs/my-run
```

The default transcription model is `base`, CPU int8, four threads. A smaller model makes exploratory runs faster:

```bash
curatevid input.mp4 -o runs/fast --model tiny.en --language en
# Once the model is cached, the same job needs no network:
curatevid input.mp4 -o runs/offline --model tiny.en --language en --offline
```

Use `--model /path/to/ctranslate2-model --offline` for an explicitly provisioned model, or `--no-transcribe` for visual curation only. `--help` lists all thresholds. Inputs are processed in sorted absolute-path order; first acceptable duplicate wins. An existing output directory is refused rather than silently mixing runs. Failed runs retain `FAILED.json`, completed `audit.jsonl` entries and partial artifacts; restart into a new directory. Automatic resume is not implemented.

## Decisions and outputs

1. Probe and SHA-256 each source. Build a 320-pixel-wide, 8-fps visual proxy with ffmpeg; original media remains untouched.
2. Use PySceneDetect's `ContentDetector` at threshold 18, minimum two analysis frames. Split scenes longer than 60 seconds into equal chunks. Decisions use source-relative seconds; proxy boundary resolution is 125 ms.
3. Decode the proxy once. For every frame, measure grayscale Laplacian variance and whether at least 95% of pixels are below luminance 24. Reject candidates shorter than 1 second, those with at least 80% black frames, those with median Laplacian variance below 35, or those with no decoded samples. Multiple quality reasons can apply to one candidate.
4. For candidates passing quality, compare three 63-bit DCT perceptual hashes at the 20%, 50%, and 80% temporal quantiles against previously accepted clips, across all sources in this invocation. Require all three Hamming distances ≤6 and durations within 15%. Record the retained clip's ID in `duplicate_of`. Rejected clips never become deduplication representatives.
5. Transcribe each complete source audio track once with local Whisper, VAD, beam size 1 and conditioning on previous text disabled. Intersect segment timestamps with each candidate and convert to clip-relative seconds. A sentence spanning a cut appears in both clips; this is segment alignment, not word alignment. Silent/no-audio and explicitly disabled transcription are distinguishable in the manifest.
6. Re-encode surviving clips from the original video with libx264 CRF 23 and AAC. Accurate decode-and-encode seeking avoids keyframe-only cuts. Rename completed clip files into place; only then append an audit record. Write Parquet and metrics after all inputs succeed.

| File | Purpose |
|---|---|
| `manifest.parquet` | Every candidate: source/hash, start/end/duration, kept/rejected, reasons, duplicate target, quality scores, hashes, output path, transcript and nested timestamped segments |
| `survivors.parquet` | Same schema, only exported survivors; retains its schema even when empty |
| `audit.jsonl` | Incremental decision log for inspection after a failed run |
| `*.transcript.json` | Complete source-level transcription segments |
| `config.json` | Effective command settings and input paths |
| `metrics.json` | Wall and CPU time, sampled process-tree RSS, per-source stage timings, bytes, retention and rejection totals, versions |

`clip_path` is relative to the run folder. `start`/`end` are source timestamps; nested segment timestamps are clip-relative. Quality reasons overlap, so **sum of per-reason durations is not the union of rejected footage**. Use `status == 'rejected'` for the union. Accepted rows have `reasons = ['passed']`.

```python
import pyarrow.parquet as pq
rows = pq.read_table('runs/my-run/manifest.parquet').to_pylist()
rejected_seconds = sum(r['duration'] for r in rows if r['status'] == 'rejected')
```

## Reproduce the real-footage benchmark

```bash
python benchmark.py                 # Downloads and verifies ~802 MB; no looping or synthetic padding
curatevid data/MoviePowderPresentsHisGirlFriday_512kb.mp4 \
  data/NightOfTheLivingDead_512kb.mp4 \
  -o runs/benchmark --model tiny.en --language en --threads 4 --offline
python verify_run.py runs/benchmark
python -m pytest -q
```

Download `tiny.en` once before using `--offline` (the first example invocation will do this), or run the benchmark without `--offline` for initial setup. The measured execution used `runs/benchmark-v2` after the dependency failure documented below. `reports/environment.txt` records the exact installed environment and `reports/model.json` records the model revision and file hashes; `av>=15,<17` avoids the observed Faster-Whisper/PyAV 19 incompatibility.

The corpus comprises two complete, distinct films, selected as legally reusable US public-domain footage: **His Girl Friday (1940)** and the original **Night of the Living Dead (1968)**. The former's Internet Archive item explicitly carries a public-domain dedication. The latter entered the US public domain because its original release omitted the required copyright notice; the selected file is an older original-film upload, not a modern restoration. These are US status claims, not a determination for every jurisdiction. A [separate Archive item for the same original film](https://archive.org/details/NightOfTheLivingDead_201508) explicitly applies the Public Domain Mark; its metadata is preserved in `reports/rights-evidence.json`. The downloaded Night item itself has no license URL; that limitation is recorded rather than inventing a license. Source URLs, byte sizes, archive MD5 checks, SHA-256 hashes and rights rationale are in [`reports/sources.json`](reports/sources.json). `benchmark.py` verifies the downloaded files against the Archive's published MD5 values. Footage, models, environment and generated clips are excluded from git.

## Measured results

<!-- RESULTS -->

Measured on **2026-11-09** in the local execution workspace (a Linux VM/container, not a physical desktop). AMD EPYC 9V74 host, 5 visible logical CPUs with a **4-core cgroup quota**, 16 GiB memory limit, no GPU. Whisper `tiny.en`, int8, four threads, English, defaults otherwise. Wall time includes model loading from cache, SHA-256, visual analysis, full-source transcription, all surviving exports and Parquet writing. Dependency installation, model download, footage download and later verification are excluded.

| Measurement | Result |
|---|---:|
| Real input duration | 3.0658 hours (183.95 minutes) |
| Wall time | 761.31 seconds (12.69 minutes) |
| CPU time, parent + children | 1648.41 seconds (0.4579 core-hours) |
| Throughput | 14.50× real time |
| Peak sampled process-tree RSS | 4.333 GiB |
| Candidates / exported clips | 3025 / 1504 |
| Retained duration | 170.83 minutes (92.87%) |
| Rejected duration, union | 13.12 minutes (7.13%) |
| Quality gates only, union | 12.65 minutes (6.88%) |
| Input / exported clip bytes | 801,747,273 / 441,483,013 |

| Source | Minutes | Candidates | Kept | Analysis s | ASR s | Export/decisions s |
|---|---:|---:|---:|---:|---:|---:|
| His Girl Friday | 88.20 | 244 | 232 | 61.46 | 185.44 | 135.81 |
| Night of the Living Dead | 95.75 | 2781 | 1272 | 67.93 | 62.13 | 248.06 |

| Rejection reason | Candidates | Minutes | Input duration % |
|---|---:|---:|---:|
| too_short | 1503 | 12.38 | 6.73% |
| no_frames | 0 | 0.00 | 0.00% |
| black | 3 | 0.05 | 0.02% |
| blurry | 20 | 0.35 | 0.19% |
| duplicate | 10 | 0.47 | 0.25% |

Reasons overlap for quality failures. Duplicate rejection runs only after quality passes. A zero count is an observed result, not proof a gate is unnecessary. The synthetic integration tests independently exercise black rejection and duplicate removal.

The two concurrent footage downloads took 109.78 s and 139.70 s respectively. The model cache occupies about 75 MiB. An initial attempt failed after 61.5 s of first-film analysis and audio extraction because PyAV 19 rejected an argument used by Faster-Whisper. That attempt is excluded from the successful-run metrics and retained in `reports/failed-attempt.log`; its total wall/CPU cost was not instrumented to completion. PyAV 16 and an audio decoder regression test fixed it.

**Local monetary cost:** no paid inference API was invoked. This environment exposes neither an electricity meter nor a local-compute invoice, so an actual dollar charge cannot be measured. At an explicitly assumed average **50 W** system draw and **$0.20/kWh**, this 0.2115-hour run would consume **0.01057 kWh** and cost **$0.00211** in electricity. At an alternative hypothetical rental rate of **$0.10/core-hour**, measured CPU time maps to **$0.0458**. These are separate illustrations, not billed amounts; neither includes hardware depreciation, idle capacity, downloads, setup, storage, the failed attempt or engineering time.

Raw metrics, exact package versions, configuration, both Parquet manifests and a readable decisions CSV are in `reports/`. The exported clips remain in the ignored local run directory and can be regenerated from the checksummed source files.

### Cloud API comparison

Pricing retrieved **2026-11-09**, USD, on-demand stored-video processing; AWS region **us-east-1**. The AWS price-list snapshot is published 2026-09-11. These are estimates from published rates, not cloud execution results. Assume free allowances already exhausted and submit each full film once, rather than each output clip.

| Service combination | Published rates | This corpus |
|---|---|---:|
| Google Video Intelligence shots + speech | $0.05 + $0.048/min; 185 rounded billable minutes | **$18.13** |
| AWS Rekognition shots + Transcribe batch | $0.05/min + $0.0001/sec ($0.006/min) | **$10.30** |
| AWS shots + technical cues + Transcribe batch | $0.05 + $0.05 + $0.006/min | **$19.50** |

Google explicitly rounds partial minutes up, producing 89 + 96 = 185 minutes here. AWS rows use duration-proportional estimates; per-request rounding has negligible effect for two long files. The standard batch Transcribe rate above is taken from the current `USE1-TranscribeAudio` price-list SKU, not a historical $0.024/min rate. Free tiers or credits can reduce these numbers: the Google pricing page lists a roughly 1,000-minute monthly free band for each selected feature, so an otherwise unused allowance would cover this corpus’s selected API calls. AWS eligibility/credits depend on account terms and are not assumed.

**No listed combination completes the same curation job by itself.** Google shot detection provides boundaries, and AWS technical cues add black-frame/credit-style signals. Neither price includes this tool’s blur gate, cross-clip perceptual deduplication, ffmpeg clip rendering or Parquet assembly. Those still require compute and orchestration. Upload/storage, requests, export/transcoding, egress and taxes are excluded, so these figures are API subtotals, not claimed end-to-end cloud totals. The local and hosted ASR models also have different quality characteristics.

Sources: [Google Video Intelligence pricing](https://cloud.google.com/video-intelligence/pricing), [AWS Rekognition pricing](https://aws.amazon.com/rekognition/pricing/), [AWS Transcribe pricing](https://aws.amazon.com/transcribe/pricing/). Exact AWS SKUs, price dimensions, dates, source endpoints and Google excerpts are preserved in [`reports/pricing-evidence.json`](reports/pricing-evidence.json).

## Limits and validation

This is a reproducible engineering benchmark, not a labeled quality or ASR accuracy study. Both films are 320×240, low-bitrate, monochrome archival material. Their retention rate does not predict results on modern camera footage, sports, screen recordings or animation. Thresholds need calibration on the intended training domain. The second film produced 2,781 candidates versus 244 in the first under the same scene threshold; short-segment rejection therefore reflects detector behavior as well as source editing, and is not a ground-truth defect rate. In particular:

- Blur and black checks describe the 320-pixel proxy. Film grain can inflate sharpness; deliberate darkness and artistic defocus may be falsely rejected. Letterboxing is included in the pixel statistics. Frames between 8-fps samples are not evaluated.
- Three-frame perceptual hashes are a conservative heuristic, not semantic deduplication. Crops, overlays, timing changes, subclips and different edits can evade it; visually similar shots can collide. The index is a linear scan, quadratic in accepted clip count, intended for local batches rather than million-clip corpora.
- `tiny.en` was chosen for CPU turnaround, not accuracy. No reference transcript or WER measurement exists for this run. In the observed output, the opening 0.91–113.02 s segment of His Girl Friday contains only “I’ll show you the first time,” illustrating suspect alignment/recognition over an opening sequence. Music, noisy dialogue and silence can yield recognition errors or hallucinations despite VAD. Transcripts should be reviewed before training use.
- Source audio is transcribed before visual rejection/export, so compute is spent on rejected footage too. This preserves context and makes transcription comparable to full-source cloud billing.
- Input sorting and recorded configuration make decisions repeatable within the pinned environment, but byte-identical codec/model results across hardware and versions are not promised. VFR material is normalized only for analysis; the benchmark uses ordinary movie files. Extremely short flashes, HDR/color handling, damaged media, audio offsets and exotic containers need additional corpus testing.
- RSS is sampled at 200 ms and sums processes, so it can miss brief peaks and double-count shared memory. CPU time includes waited-for child processes; energy and hardware ownership cost are not directly measured.

The completed benchmark passed verification of all **1,504 exported clips** and all **3,025 manifest rows**; the largest clip-duration deviation was **0.033 seconds**. All **six tests passed**. See [`reports/verification.json`](reports/verification.json).

Tests exercise black/blur/short/no-frame gates, temporal hash comparisons, brightness robustness, transcript intersections, audio decoding, actual ffmpeg scene/export behavior, exact and brightness-shifted duplicate rejection across sources, unique candidate IDs, empty typed output and refusal to overwrite runs. `verify_run.py` checks manifest coverage, IDs, transcript bounds, every exported clip's duration, and duplicate targets. See [`reports/tests.txt`](reports/tests.txt) and the benchmark verification evidence.
