"""Local video curation. All timestamps are seconds on the source timeline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import threading
import time

import cv2
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import psutil
from scenedetect import ContentDetector, SceneManager, open_video

SCHEMA = pa.schema([
    ('clip_id', pa.string()), ('source', pa.string()), ('source_sha256', pa.string()),
    ('start', pa.float64()), ('end', pa.float64()), ('duration', pa.float64()),
    ('status', pa.string()), ('reasons', pa.list_(pa.string())),
    ('duplicate_of', pa.string()), ('black_fraction', pa.float64()),
    ('blur_median', pa.float64()), ('sample_count', pa.int64()),
    ('phashes', pa.list_(pa.string())), ('clip_path', pa.string()),
    ('transcript', pa.string()), ('transcription_status', pa.string()),
    ('segments', pa.list_(pa.struct([('start', pa.float64()), ('end', pa.float64()),
                                   ('text', pa.string())]))),
])


def command(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[-4000:]}")
    return result.stdout


def probe(path):
    info = json.loads(command(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                               '-of', 'json', path]))
    if not any(s['codec_type'] == 'video' for s in info['streams']):
        raise ValueError(f'No video stream: {path}')
    duration = float(info['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f'Invalid duration: {path}')
    return duration, any(s['codec_type'] == 'audio' for s in info['streams'])


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def phash(gray):
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8].flatten()[1:]
    return sum(int(bit) << i for i, bit in enumerate(low > np.median(low)))


def duplicate(hashes, duration, accepted, threshold):
    for old_id, old_duration, old_hashes in accepted:
        if abs(duration - old_duration) / max(duration, old_duration) <= 0.15:
            if all((a ^ b).bit_count() <= threshold for a, b in zip(hashes, old_hashes)):
                return old_id
    return None


def boundaries(proxy, duration, threshold, max_seconds):
    video = open_video(str(proxy))
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=2))
    manager.detect_scenes(video=video)
    cuts = sorted(set([0.0, duration] + [a.seconds for a, _ in manager.get_scene_list()
                                      if 0 < a.seconds < duration]))
    result = []
    for start, end in zip(cuts, cuts[1:]):
        count = max(1, math.ceil((end - start) / max_seconds))
        result.extend((start + i * (end-start)/count, start + (i+1)*(end-start)/count)
                      for i in range(count))
    return result


def measure(proxy, spans, fps):
    """Decode once; score every proxy frame, hash three temporal quantiles."""
    cap = cv2.VideoCapture(str(proxy))
    samples = [[] for _ in spans]
    index = frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            at = frame_index / fps
            frame_index += 1
            while index + 1 < len(spans) and at >= spans[index][1]:
                index += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            black = float(np.mean(gray < 24)) >= 0.95
            blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            samples[index].append((black, blur, phash(gray)))
    finally:
        cap.release()
    return samples


def quality(samples, duration, args):
    reasons = []
    if duration < args.min_seconds:
        reasons.append('too_short')
    if not samples:
        return reasons + ['no_frames'], None, None, []
    black = float(np.mean([s[0] for s in samples]))
    blur = float(np.median([s[1] for s in samples]))
    hashes = [samples[min(len(samples)-1, int(q*len(samples)))][2] for q in (0.2, 0.5, 0.8)]
    if black >= args.black_fraction:
        reasons.append('black')
    if blur < args.blur_threshold:
        reasons.append('blurry')
    return reasons, black, blur, hashes


def intersect_segments(segments, start, end):
    return [{'start': max(s['start'], start)-start, 'end': min(s['end'], end)-start,
             'text': s['text']} for s in segments if s['end'] > start and s['start'] < end]


class Monitor:
    def __init__(self):
        self.peak = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.watch, daemon=True)

    def watch(self):
        process = psutil.Process()
        while not self.stop.is_set():
            total = 0
            for p in [process] + process.children(recursive=True):
                try:
                    total += p.memory_info().rss
                except psutil.Error:
                    pass
            self.peak = max(self.peak, total)
            self.stop.wait(0.2)


def cpu_seconds():
    return sum(r.ru_utime + r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)])


def run(args):
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise ValueError(f'Required executable not found: {binary}')
    inputs = sorted(set(Path(p).resolve(strict=True) for p in args.inputs))
    if any(not p.is_file() for p in inputs):
        raise ValueError('Inputs must be regular files')
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier run.
    (out / 'clips').mkdir()
    scratch = out / 'work'
    scratch.mkdir()
    configuration = vars(args).copy()
    configuration['inputs'] = [str(p) for p in inputs]
    (out / 'config.json').write_text(json.dumps(configuration, indent=2))
    monitor = Monitor()
    monitor.thread.start()
    began, cpu_start = time.perf_counter(), cpu_seconds()
    rows, accepted, sources = [], [], []
    model = None
    try:
        if not args.no_transcribe:
            from faster_whisper import WhisperModel
            model = WhisperModel(args.model, device='cpu', compute_type='int8',
                                 cpu_threads=args.threads, download_root=args.model_cache,
                                 local_files_only=args.offline)
        for source_number, path in enumerate(inputs):
            source_start = time.perf_counter()
            duration, has_audio = probe(path)
            digest = sha256(path)
            proxy = scratch / 'proxy.mp4'
            command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', args.threads,
                     '-i', path, '-an', '-vf', f'scale=320:-2,fps={args.analysis_fps}',
                     '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
                     '-threads', args.threads, proxy])
            spans = boundaries(proxy, duration, args.scene_threshold, args.max_seconds)
            samples = measure(proxy, spans, args.analysis_fps)
            analysis_seconds = time.perf_counter() - source_start
            print(f'{path.name}: {len(spans)} candidates, analysis {analysis_seconds:.1f}s', flush=True)
            transcript_start = time.perf_counter()
            segments = []
            if model and has_audio:
                audio = scratch / 'audio.wav'
                command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', path, '-vn',
                         '-ac', '1', '-ar', '16000', audio])
                iterator, _ = model.transcribe(str(audio), beam_size=1, vad_filter=True,
                                               language=args.language, condition_on_previous_text=False)
                segments = [{'start': s.start, 'end': s.end, 'text': s.text.strip()} for s in iterator]
                audio.unlink()
            transcription_seconds = time.perf_counter() - transcript_start
            (out / f'{digest[:16]}.transcript.json').write_text(json.dumps(segments, indent=2))
            export_start = time.perf_counter()
            for number, ((start, end), sample) in enumerate(zip(spans, samples)):
                clip_id = f'{digest[:16]}-{source_number:03d}-{number:06d}'
                reasons, black, blur, hashes = quality(sample, end-start, args)
                duplicate_of = None
                if not reasons:
                    duplicate_of = duplicate(hashes, end-start, accepted, args.hash_distance)
                    if duplicate_of:
                        reasons.append('duplicate')
                relative = None
                if not reasons:
                    relative = f'clips/{clip_id}.mp4'
                    temporary = out / 'clips' / f'{clip_id}.partial.mp4'
                    command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', start,
                             '-threads', args.threads, '-i', path, '-t', end-start,
                             '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264',
                             '-preset', 'veryfast', '-crf', args.crf, '-threads', args.threads,
                             '-c:a', 'aac', '-movflags', '+faststart', temporary])
                    temporary.rename(out / relative)
                    accepted.append((clip_id, end-start, hashes))
                aligned = intersect_segments(segments, start, end)
                row = dict(clip_id=clip_id, source=str(path), source_sha256=digest,
                           start=start, end=end, duration=end-start,
                           status='rejected' if reasons else 'kept', reasons=reasons or ['passed'],
                           duplicate_of=duplicate_of, black_fraction=black, blur_median=blur,
                           sample_count=len(sample), phashes=[f'{h:016x}' for h in hashes],
                           clip_path=relative, transcript=' '.join(s['text'] for s in aligned),
                           transcription_status=('no_audio' if not has_audio else
                                                 'disabled' if not model else 'completed'), segments=aligned)
                rows.append(row)
                with (out / 'audit.jsonl').open('a') as audit:
                    audit.write(json.dumps(row) + '\n')
            sources.append(dict(path=str(path), sha256=digest, seconds=duration,
                                input_bytes=path.stat().st_size, candidates=len(spans),
                                analysis_seconds=analysis_seconds,
                                transcription_seconds=transcription_seconds,
                                export_seconds=time.perf_counter()-export_start))
            print(f'{path.name}: complete in {time.perf_counter()-source_start:.1f}s', flush=True)
        table = pa.Table.from_pylist(rows, schema=SCHEMA)
        pq.write_table(table, out / 'manifest.parquet', compression='zstd')
        pq.write_table(pa.Table.from_pylist([r for r in rows if r['status']=='kept'], schema=SCHEMA),
                       out / 'survivors.parquet', compression='zstd')
        elapsed, cpu = time.perf_counter()-began, cpu_seconds()-cpu_start
        report = dict(wall_seconds=elapsed, cpu_seconds=cpu, sources=sources,
                      peak_tree_rss_bytes=monitor.peak, rss_sampling_seconds=0.2,
                      input_seconds=sum(s['seconds'] for s in sources),
                      kept_seconds=sum(r['duration'] for r in rows if r['status']=='kept'),
                      candidate_count=len(rows), kept_count=len(accepted),
                      rejection_seconds={reason: sum(r['duration'] for r in rows if reason in r['reasons'])
                                         for reason in ('too_short','no_frames','black','blurry','duplicate')},
                      output_clip_bytes=sum(p.stat().st_size for p in (out/'clips').glob('*.mp4')),
                      platform=platform.platform(), logical_cpus=os.cpu_count(),
                      versions={p: importlib.metadata.version(p) for p in
                                ('scenedetect','faster-whisper','pyarrow','numpy','ctranslate2')},
                      ffmpeg=command(['ffmpeg','-version']).splitlines()[0])
        (out / 'metrics.json').write_text(json.dumps(report, indent=2))
        shutil.rmtree(scratch)
        print(json.dumps(report, indent=2))
    except Exception as exc:
        (out / 'FAILED.json').write_text(json.dumps({'error': str(exc), 'completed_rows': len(rows)}))
        raise
    finally:
        monitor.stop.set()
        monitor.thread.join()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+')
    p.add_argument('-o', '--output', required=True, help='New output directory; existing paths refused')
    p.add_argument('--model', default='base', help='Whisper model name or local model directory')
    p.add_argument('--model-cache', default='.cache/models')
    p.add_argument('--offline', action='store_true', help='Require a pre-downloaded model')
    p.add_argument('--no-transcribe', action='store_true')
    p.add_argument('--language', default=None)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--analysis-fps', type=float, default=8)
    p.add_argument('--scene-threshold', type=float, default=18)
    p.add_argument('--min-seconds', type=float, default=1)
    p.add_argument('--max-seconds', type=float, default=60)
    p.add_argument('--black-fraction', type=float, default=0.8)
    p.add_argument('--blur-threshold', type=float, default=35)
    p.add_argument('--hash-distance', type=int, default=6)
    p.add_argument('--crf', type=int, default=23)
    return p


def main():
    p = parser()
    args = p.parse_args()
    if (args.threads < 1 or not 0 < args.analysis_fps <= 60 or
        not 0 < args.min_seconds <= args.max_seconds or not 0 < args.black_fraction <= 1 or
        not 0 <= args.hash_distance <= 63 or not 0 <= args.crf <= 51 or
        not math.isfinite(args.blur_threshold) or args.blur_threshold < 0 or
        not math.isfinite(args.max_seconds) or not 0 < args.scene_threshold <= 255):
        p.error('Invalid threshold, duration, frame rate, CRF, or thread count')
    try:
        run(args)
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(1, f'curatevid: {exc}\n')


if __name__ == '__main__':
    main()
