import logging

import asdf
import fsspec
import s3fs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# asdf.open resolves s3:// URIs via fsspec + s3fs automatically.
# Set anon=True globally for public buckets (no AWS credentials needed).
# default_fill_cache=False + cache_type "none" are critical: with the default
# readahead cache, every small seek+read (asdf walks each block header) pulls
# a full 5 MB block, ballooning the fetch to ~50% of the file.
fsspec.config.conf["s3"] = {
    "anon": True,
    "default_fill_cache": False,
    "default_cache_type": "none",
}

# Patch s3fs at the network-fetch layer (not read()) so the counter reflects
# actual S3 Range GET bytes, regardless of how asdf/fsspec buffer or cache reads.
_bytes_fetched = {"total": 0}
_orig_fetch_range = s3fs.S3File._fetch_range


def _counting_fetch_range(self, start, end):
    data = _orig_fetch_range(self, start, end)
    _bytes_fetched["total"] += len(data)
    return data


s3fs.S3File._fetch_range = _counting_fetch_range

asdf_uri = (
    "s3://stpubdata/roman/nexus/soc_simulations/r00342/l2/"
    "r0034201001001001001_0001_wfi01_f087_cal.asdf"
)

# Report file size upfront so we can appreciate what was NOT downloaded.
fs = s3fs.S3FileSystem(anon=True)
file_size = fs.info(asdf_uri)["size"]
log.info("S3 file size: %d bytes (%.1f MB)", file_size, file_size / 1e6)

# No custom wrapper needed — asdf opens the S3 URI directly via fsspec.
# lazy_load=True + lazy_tree=True -> only the ASDF header/tree is fetched;
# array blocks remain on S3 until explicitly accessed.
with asdf.open(
    asdf_uri,
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
    print("exposure_time:", exp.get("exposure_time"))
    print("start_time:", exp.get("start_time"))

    # Proof of lazy loading: data node exists as a proxy object, not a loaded array.
    data_node = af["roman"]["data"]
    print("data node type:", type(data_node).__name__, "← not downloaded")

    # Accessing data_node[:] here would trigger a full array fetch — skipped intentionally.

fetched = _bytes_fetched["total"]
pct = 100 * fetched / file_size
print(f"\nbytes fetched: {fetched:,} / {file_size:,} ({pct:.2f}%) — metadata only, no array data downloaded")
