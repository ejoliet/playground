import logging

import asdf
import fsspec
import s3fs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# asdf.open resolves s3:// URIs via fsspec + s3fs automatically.
# Set anon=True globally for public buckets (no AWS credentials needed).
fsspec.config.conf["s3"] = {"anon": True}

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

print("\nNote: bytes fetched not tracked here (asdf owns the file handle).")
print("Use s3example.py or s3fsexample.py for precise bytes-fetched accounting.")
