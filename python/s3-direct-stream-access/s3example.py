import io
import logging

import asdf
import boto3
from botocore import UNSIGNED
from botocore.config import Config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class S3RangeReader(io.RawIOBase):
    """Seekable read-only file object backed by S3 Range GETs — never fetches the full file."""

    def __init__(self, bucket, key, client=None, block_size=8 * 1024 * 1024):
        self.bucket = bucket
        self.key = key
        self.client = client or boto3.client("s3")
        self.block_size = block_size
        self.pos = 0
        self.bytes_fetched = 0

        head = self.client.head_object(Bucket=bucket, Key=key)
        self.size = head["ContentLength"]
        log.info("S3 file size: %d bytes (%.1f MB)", self.size, self.size / 1e6)

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if self.pos < 0:
            raise ValueError("Negative seek position")
        return self.pos

    def read(self, size=-1):
        if self.pos >= self.size:
            return b""
        if size is None or size < 0:
            size = min(self.block_size, self.size - self.pos)
        end = min(self.pos + size, self.size) - 1
        range_header = f"bytes={self.pos}-{end}"
        log.debug("Range GET %s", range_header)
        obj = self.client.get_object(Bucket=self.bucket, Key=self.key, Range=range_header)
        data = obj["Body"].read()
        self.pos += len(data)
        self.bytes_fetched += len(data)
        return data


bucket = "stpubdata"
key = (
    "roman/nexus/soc_simulations/r00342/l2/"
    "r0034201001001001001_0001_wfi01_f087_cal.asdf"
)

s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

with S3RangeReader(bucket, key, client=s3) as reader:
    with asdf.open(
        reader,
        uri=f"s3://{bucket}/{key}",
        lazy_load=True,
        lazy_tree=True,
        memmap=False,
        validate_checksums=False,
        ignore_missing_extensions=True,
    ) as af:
        meta = af["roman"]["meta"]
        inst = meta["instrument"]
        exp = meta["exposure"]

        print("detector:", inst.get("detector"))
        print("optical_element:", inst.get("optical_element") or inst.get("filter"))
        print("exposure_time:", exp.get("exposure_time"))
        print("start_time:", exp.get("start_time"))

        # Accessing af["roman"]["data"] here would trigger a full array fetch — skipped intentionally.

    pct = 100 * reader.bytes_fetched / reader.size
    print(f"\nbytes fetched: {reader.bytes_fetched:,} / {reader.size:,} ({pct:.2f}%) — metadata only, no array data downloaded")
