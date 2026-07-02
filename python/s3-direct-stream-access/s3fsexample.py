import logging

import asdf
import s3fs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class _CountingFile:
    """Thin wrapper to track bytes read from any file-like object."""
    def __init__(self, f):
        self._f = f
        self.bytes_fetched = 0

    def read(self, size=-1):
        data = self._f.read(size)
        self.bytes_fetched += len(data)
        return data

    def __getattr__(self, name):
        return getattr(self._f, name)


asdf_uri = (
    "s3://stpubdata/roman/nexus/soc_simulations/r00342/l2/"
    "r0034201001001001001_0001_wfi01_f087_cal.asdf"
)

fs = s3fs.S3FileSystem(anon=True, default_fill_cache=False, default_cache_type="readahead")

file_size = fs.info(asdf_uri)["size"]
log.info("S3 file size: %d bytes (%.1f MB)", file_size, file_size / 1e6)

with fs.open(asdf_uri, "rb", block_size=8 * 1024 * 1024, fill_cache=False) as raw:
    reader = _CountingFile(raw)
    with asdf.open(
        reader,
        uri=asdf_uri,
        lazy_load=True,
        lazy_tree=True,
        memmap=False,
        validate_checksums=False,
        ignore_missing_extensions=True,
    ) as af:
        meta = af["roman"]["meta"]
        inst = meta["instrument"]
        exp = meta["exposure"]

        print("telescope:", meta.get("telescope"))
        print("origin:", meta.get("origin"))
        print("detector:", inst.get("detector"))
        print("optical_element:", inst.get("optical_element"))
        print("filter:", inst.get("filter"))
        print("exposure_time:", exp.get("exposure_time"))
        print("start_time:", exp.get("start_time"))

        # Accessing af["roman"]["data"] here would trigger a full array fetch — skipped intentionally.
        print("data node (lazy, not fetched):", type(af["roman"]["data"]))

    pct = 100 * reader.bytes_fetched / file_size
    print(f"\nbytes fetched: {reader.bytes_fetched:,} / {file_size:,} ({pct:.2f}%) — metadata only, no array data downloaded")
