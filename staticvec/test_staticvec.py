import http.client
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import faiss
import numpy as np
from client import RangeReader, StaticIndex
from format import build, parse_header
from server import make_server, RangeHandler

class StaticvecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faiss.omp_set_num_threads(1)
        cls.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        cls.x = np.random.default_rng(8).normal(size=(400, 8)).astype('float32')
        cls.path = Path(cls.tmp.name)/'tiny.svx'
        build(cls.path, cls.x, 8)
        cls.server = make_server(cls.tmp.name)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/tiny.svx'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_all_buckets_equals_exact_and_bytes(self):
        index = StaticIndex(self.url)
        try:
            for query in self.x[::37]:
                ids, stats = index.search(query, probes=8)
                expected = np.argsort(((self.x-query)**2).sum(axis=1))[:10]
                np.testing.assert_array_equal(ids, expected)
                self.assertEqual(stats['bytes'], self.path.stat().st_size-index.startup['bytes'])
                self.assertEqual(stats['requests'], 1)
            self.assertEqual(index.startup['requests'], 2)
        finally:
            index.close()

    def test_partial_fetch_and_invalid_query(self):
        index = StaticIndex(self.url)
        try:
            _, stats = index.search(self.x[0], probes=1)
            self.assertLess(stats['bytes'], self.path.stat().st_size//2)
            self.assertEqual(stats['bytes'], stats['vectors']*(4+8*4))
            for query in [np.zeros(7), np.full(8, np.nan)]:
                with self.assertRaises(ValueError):
                    index.search(query)
            with self.assertRaises(ValueError):
                index.search(self.x[0], probes=0)
        finally:
            index.close()

    def test_ranges_and_bad_header(self):
        reader = RangeReader(self.url)
        try:
            raw = self.path.read_bytes()
            for start, end in [(0,0), (63, 77), (len(raw)-1, len(raw)-1)]:
                self.assertEqual(reader.get(start,end), raw[start:end+1])
            with self.assertRaises(ValueError):
                reader.get(len(raw),len(raw))
            with self.assertRaises(ValueError):
                parse_header(b'X'*64)
        finally:
            reader.close()
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('GET', '/tiny.svx', headers={'Range': 'bytes=0-2,5-7'})
        response = conn.getresponse()
        self.assertEqual(response.status, 416)
        response.read()
        conn.close()

    def test_server_ignoring_range_is_rejected(self):
        class IgnoreRange(RangeHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(IgnoreRange, directory=self.tmp.name))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaisesRegex(ValueError, 'Range not honored'):
                StaticIndex(f'http://127.0.0.1:{server.server_port}/tiny.svx')
        finally:
            server.shutdown()
            server.server_close()

    def test_corrupt_directory_is_rejected(self):
        from format import parse_header, HEADER_SIZE
        raw = bytearray(self.path.read_bytes())
        h = parse_header(raw[:HEADER_SIZE])
        raw[h['directory']:h['directory']+8] = bytes(8)
        (Path(self.tmp.name)/'corrupt.svx').write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Invalid bucket directory'):
            StaticIndex(self.url.replace('tiny.svx', 'corrupt.svx'))

    def test_duplicate_embeddings_have_tie_aware_recall(self):
        from benchmark import recall, tie_recall
        vectors = np.zeros((20, 8), dtype=np.float32)
        truth, returned = np.arange(10), np.arange(10, 20)
        self.assertEqual(recall(returned, truth), 0.0)
        self.assertEqual(tie_recall(returned, vectors[0], vectors, 0.0), 1.0)

if __name__ == '__main__':
    unittest.main()
