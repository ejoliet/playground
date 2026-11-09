import importlib.util
import struct
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('measure',Path(__file__).resolve().parents[1]/'scripts/measure.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class WireTest(unittest.TestCase):
    def test_multiple_strings_and_compressed_name(self):
        question=m.wire_query('test.example')[12:]
        rdata=b'\x03abc\x03def'
        packet=struct.pack('!6H',0,0x8180,1,1,0,0)+question+b'\xc0\x0c'+struct.pack('!HHIH',16,1,60,len(rdata))+rdata
        answer=m.wire_answer(packet)
        self.assertEqual(answer['Answer'][0]['data'],'abcdef')
        self.assertEqual(answer['Answer'][0]['strings'],2)
        self.assertEqual(answer['Answer'][0]['TTL'],60)

    def test_label_limit(self):
        m.wire_query('a'*63+'.example')
        with self.assertRaises(ValueError):m.wire_query('a'*64+'.example')

    def test_truncation_flag(self):
        answer=m.wire_answer(struct.pack('!6H',0,0x8382,0,0,0,0))
        self.assertTrue(answer['TC'])
        self.assertEqual(answer['Status'],2)


if __name__=='__main__':unittest.main()
