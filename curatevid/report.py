"""Render the README benchmark section from a completed, verified local run."""
import csv
import json
import math
from pathlib import Path
import shutil
import sys

import pyarrow.parquet as pq

run = Path(sys.argv[1])
m = json.loads((run/'metrics.json').read_text())
rows = pq.read_table(run/'manifest.parquet').to_pylist()
for name in ['metrics.json','config.json','manifest.parquet','survivors.parquet']:
    shutil.copyfile(run/name, Path('reports')/name)
with open('reports/decisions.csv','w') as f:
    fields = ['clip_id','start','end','duration','status','reasons','black_fraction','blur_median','duplicate_of']
    writer = csv.DictWriter(f,fieldnames=fields)
    writer.writeheader()
    writer.writerows({k:r[k] for k in fields} for r in rows)
seconds = m['input_seconds']
rejected = sum(r['duration'] for r in rows if r['status']=='rejected')
quality = sum(r['duration'] for r in rows if r['status']=='rejected' and 'duplicate' not in r['reasons'])
lines = [
    'Measured on **2026-11-09** in the local execution workspace (a Linux VM/container, not a physical desktop). '
    'AMD EPYC 9V74 host, 5 visible logical CPUs with a **4-core cgroup quota**, 16 GiB memory limit, no GPU. '
    'Whisper `tiny.en`, int8, four threads, English, defaults otherwise. '
    'Wall time includes model loading from cache, SHA-256, visual analysis, full-source transcription, all surviving exports and Parquet writing. '
    'Dependency installation, model download, footage download and later verification are excluded.',
    '',
    '| Measurement | Result |', '|---|---:|',
    f'| Real input duration | {seconds/3600:.4f} hours ({seconds/60:.2f} minutes) |',
    f'| Wall time | {m["wall_seconds"]:.2f} seconds ({m["wall_seconds"]/60:.2f} minutes) |',
    f'| CPU time, parent + children | {m["cpu_seconds"]:.2f} seconds ({m["cpu_seconds"]/3600:.4f} core-hours) |',
    f'| Throughput | {seconds/m["wall_seconds"]:.2f}× real time |',
    f'| Peak sampled process-tree RSS | {m["peak_tree_rss_bytes"]/2**30:.3f} GiB |',
    f'| Candidates / exported clips | {m["candidate_count"]} / {m["kept_count"]} |',
    f'| Retained duration | {m["kept_seconds"]/60:.2f} minutes ({100*m["kept_seconds"]/seconds:.2f}%) |',
    f'| Rejected duration, union | {rejected/60:.2f} minutes ({100*rejected/seconds:.2f}%) |',
    f'| Quality gates only, union | {quality/60:.2f} minutes ({100*quality/seconds:.2f}%) |',
    f'| Input / exported clip bytes | {sum(s["input_bytes"] for s in m["sources"]):,} / {m["output_clip_bytes"]:,} |',
    '', '| Source | Minutes | Candidates | Kept | Analysis s | ASR s | Export/decisions s |',
    '|---|---:|---:|---:|---:|---:|---:|'
]
for source in m['sources']:
    group = [r for r in rows if r['source']==source['path']]
    title = 'His Girl Friday' if 'Friday' in source['path'] else 'Night of the Living Dead'
    lines.append(f'| {title} | {source["seconds"]/60:.2f} | {len(group)} | {sum(r["status"]=="kept" for r in group)} | {source["analysis_seconds"]:.2f} | {source["transcription_seconds"]:.2f} | {source["export_seconds"]:.2f} |')
lines += ['', '| Rejection reason | Candidates | Minutes | Input duration % |','|---|---:|---:|---:|']
for reason, value in m['rejection_seconds'].items():
    lines.append(f'| {reason} | {sum(reason in r["reasons"] for r in rows)} | {value/60:.2f} | {100*value/seconds:.2f}% |')
lines += ['', 'Reasons overlap for quality failures. Duplicate rejection runs only after quality passes. '
          'A zero count is an observed result, not proof a gate is unnecessary. '
          'The synthetic integration tests independently exercise black rejection and duplicate removal.', '',
          'The two concurrent footage downloads took 109.78 s and 139.70 s respectively. '
          'The model cache occupies about 75 MiB. An initial attempt failed after 61.5 s of first-film analysis '
          'and audio extraction because PyAV 19 rejected an argument used by Faster-Whisper. '
          'That attempt is excluded from the successful-run metrics and retained in `reports/failed-attempt.log`; '
          'its total wall/CPU cost was not instrumented to completion. PyAV 16 and an audio decoder regression test fixed it.', '',
          '**Local monetary cost:** no paid inference API was invoked. This environment exposes neither an electricity meter '
          'nor a local-compute invoice, so an actual dollar charge cannot be measured. '
          f'At an explicitly assumed average **50 W** system draw and **$0.20/kWh**, this {m["wall_seconds"]/3600:.4f}-hour '
          f'run would consume **{50*m["wall_seconds"]/3600000:.5f} kWh** and cost **${50*m["wall_seconds"]/3600000*.2:.5f}** in electricity. '
          f'At an alternative hypothetical rental rate of **$0.10/core-hour**, measured CPU time maps to **${m["cpu_seconds"]/3600*.1:.4f}**. '
          'These are separate illustrations, not billed amounts; neither includes hardware depreciation, idle capacity, '
          'downloads, setup, storage, the failed attempt or engineering time.', '',
          'Raw metrics, exact package versions, configuration, both Parquet manifests and a readable decisions CSV are in `reports/`. '
          'The exported clips remain in the ignored local run directory and can be regenerated from the checksummed source files.', '',
          '### Cloud API comparison', '',
          'Pricing retrieved **2026-11-09**, USD, on-demand stored-video processing; AWS region **us-east-1**. '
          'The AWS price-list snapshot is published 2026-09-11. '
          'These are estimates from published rates, not cloud execution results. '
          'Assume free allowances already exhausted and submit each full film once, rather than each output clip.', '',
          '| Service combination | Published rates | This corpus |', '|---|---|---:|']
minutes = seconds/60
google_minutes = sum(math.ceil(s['seconds']/60) for s in m['sources'])
lines += [
    f'| Google Video Intelligence shots + speech | $0.05 + $0.048/min; {google_minutes} rounded billable minutes | **${google_minutes*.098:.2f}** |',
    f'| AWS Rekognition shots + Transcribe batch | $0.05/min + $0.0001/sec ($0.006/min) | **${minutes*.056:.2f}** |',
    f'| AWS shots + technical cues + Transcribe batch | $0.05 + $0.05 + $0.006/min | **${minutes*.106:.2f}** |', '',
    'Google explicitly rounds partial minutes up, producing 89 + 96 = 185 minutes here. '
    'AWS rows use duration-proportional estimates; per-request rounding has negligible effect for two long files. '
    'The standard batch Transcribe rate above is taken from the current `USE1-TranscribeAudio` price-list SKU, '
    'not a historical $0.024/min rate. Free tiers or credits can reduce these numbers: the Google pricing page '
    'lists a roughly 1,000-minute monthly free band for each selected feature, so an otherwise unused allowance '
    'would cover this corpus’s selected API calls. AWS eligibility/credits depend on account terms and are not assumed.', '',
    '**No listed combination completes the same curation job by itself.** Google shot detection provides boundaries, '
    'and AWS technical cues add black-frame/credit-style signals. Neither price includes this tool’s blur gate, '
    'cross-clip perceptual deduplication, ffmpeg clip rendering or Parquet assembly. '
    'Those still require compute and orchestration. Upload/storage, requests, export/transcoding, egress and taxes '
    'are excluded, so these figures are API subtotals, not claimed end-to-end cloud totals. '
    'The local and hosted ASR models also have different quality characteristics.', '',
    'Sources: [Google Video Intelligence pricing](https://cloud.google.com/video-intelligence/pricing), '
    '[AWS Rekognition pricing](https://aws.amazon.com/rekognition/pricing/), '
    '[AWS Transcribe pricing](https://aws.amazon.com/transcribe/pricing/). '
    'Exact AWS SKUs, price dimensions, dates, source endpoints and Google excerpts are preserved in '
    '[`reports/pricing-evidence.json`](reports/pricing-evidence.json).'
]
path = Path('README.md')
text = path.read_text()
start = text.index('<!-- RESULTS -->')
end = text.index('\n## Limits and validation', start)
path.write_text(text[:start]+'<!-- RESULTS -->\n\n'+'\n'.join(lines)+'\n'+text[end:])
