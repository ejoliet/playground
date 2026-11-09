from pathlib import Path
import argparse
import subprocess

import numpy as np
import pyarrow.parquet as pq
import pytest

from curatevid import duplicate, intersect_segments, phash, quality, main


def test_quality_and_duplicate():
    args = argparse.Namespace(min_seconds=1, black_fraction=.8, blur_threshold=35)
    assert set(quality([(True, 0, 0)]*8, 2, args)[0]) == {'black', 'blurry'}
    assert quality([], 2, args)[0] == ['no_frames']
    assert duplicate([1,2,3], 10, [('kept',10,[1,2,3])], 0) == 'kept'
    assert duplicate([1,2,3], 20, [('kept',10,[1,2,3])], 6) is None
    assert duplicate([1,2,255], 10, [('kept',10,[1,2,3])], 2) is None
    assert quality([(False, 200, 1)]*8, .5, args)[0] == ['too_short']


def test_transcript_boundaries():
    segments = [{'start': 1., 'end': 4., 'text': 'hello'}, {'start': 5., 'end': 6., 'text':'next'}]
    assert intersect_segments(segments, 2, 5) == [{'start':0, 'end':2., 'text':'hello'}]


def test_hash_brightness_invariance():
    rng = np.random.default_rng(1)
    gray = rng.integers(20, 180, (180,320), dtype=np.uint8)
    assert (phash(gray) ^ phash(gray+20)).bit_count() <= 2


def test_end_to_end(tmp_path, monkeypatch):
    video = tmp_path/'test.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=16:duration=3',
                    '-f','lavfi','-i','color=black:size=320x180:rate=16:duration=3',
                    '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map','[v]',
                    '-c:v','libx264','-threads','1',str(video)], check=True)
    out = tmp_path/'out'
    monkeypatch.setattr('sys.argv', ['curatevid', str(video), '-o',str(out),'--no-transcribe','--threads','1'])
    main()
    rows = pq.read_table(out/'manifest.parquet').to_pylist()
    assert any('black' in r['reasons'] for r in rows)
    assert any(r['status']=='kept' for r in rows)
    assert sum(r['duration'] for r in rows) == pytest.approx(6)
    for r in rows:
        assert r['transcription_status']=='no_audio'
        if r['status']=='kept':
            assert (out/r['clip_path']).is_file()
    assert (out/'metrics.json').is_file()
    with pytest.raises(SystemExit):
        main()  # Existing output is never overwritten.


def test_duplicate_across_sources_and_empty_survivors(tmp_path, monkeypatch):
    import shutil
    first = tmp_path/'a.mp4'
    second = tmp_path/'b.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=16:duration=2',
                    '-c:v','libx264','-threads','1',str(first)],check=True)
    shutil.copyfile(first, second)
    third = tmp_path/'c.mp4'
    subprocess.run(['ffmpeg','-v','error','-i',str(first),'-vf','eq=brightness=0.02',
                    '-c:v','libx264','-threads','1',str(third)],check=True)
    out = tmp_path/'duplicates'
    monkeypatch.setattr('sys.argv',['curatevid',str(first),str(second),str(third),'-o',str(out),
                                   '--no-transcribe','--threads','1'])
    main()
    rows = pq.read_table(out/'manifest.parquet').to_pylist()
    assert len(rows)==3
    assert rows[2]['reasons']==['duplicate']
    assert rows[0]['status']=='kept'
    assert rows[1]['reasons']==['duplicate']
    assert rows[1]['duplicate_of']==rows[0]['clip_id']
    assert rows[1]['clip_id']!=rows[0]['clip_id']
    rejected = tmp_path/'rejected'
    monkeypatch.setattr('sys.argv',['curatevid',str(first),'-o',str(rejected),
                                   '--no-transcribe','--min-seconds','3','--threads','1'])
    main()
    table = pq.read_table(rejected/'survivors.parquet')
    assert table.num_rows==0
    assert table.schema.field('start').type == __import__('pyarrow').float64()
