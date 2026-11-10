# stpubdata: an evidence-backed field guide

Observed 2026-11-10. `s3://stpubdata/` is a heterogeneous astronomical-data bucket: the inspected samples include Gaia/PS1 catalogs, JWST NIRCam image products, and GALEX aspect data. This characterization comes from collection metadata and actual file schemas, not just directory names. [Catalog commands/output](snippets/07-catalogs.sh) · [catalog evidence](snippets/07-catalogs.out) · [FITS commands](snippets/08-fits-recipes.sh) · [FITS evidence](snippets/08-fits-recipes.out).

## Start today

Run from the repository root. Setup uses **uv and a local `stpubdata/.venv`**, with no global library installation. AWS CLI must be available; it was already installed in this environment. [Environment script](snippets/01-environment.sh), [output](snippets/01-environment.out); [dependency script](snippets/04-install-duckdb.sh), [output](snippets/04-install-duckdb.out).

```bash
bash stpubdata/snippets/01-environment.sh
bash stpubdata/snippets/04-install-duckdb.sh
bash stpubdata/snippets/07-catalogs.sh      # recipe 1 + Gaia schema discovery
bash stpubdata/snippets/08-fits-recipes.sh  # recipes 2 and 3
```

Both recipe scripts use anonymous AWS CLI HEAD/Range requests, inspect metadata before full reads, and clean temporary data automatically. DuckDB runs on local bytes, so it needs no remote extension or AWS secret. [07](snippets/07-catalogs.sh), [08](snippets/08-fits-recipes.sh).

## Layout and formats

The complete top-level delimiter listing returned these 11 prefixes. The second level below is also complete at the time of inspection; object examples are only lexical samples. [Root command](snippets/02-root.sh), [output](snippets/02-root.out); [layout command](snippets/05-layout.sh), [output](snippets/05-layout.out).

| Prefix | Observed next level | Sample suffix/product |
|---|---|---|
| `gaia/` | `gaia_dr3/` | HATS properties, Parquet |
| `galex/` | `GR6/`, `GR7/`, `gap/`, `public/` | pipeline text, `.fits.gz` |
| `hst/` | `grizli-v1/`, `public/` | `.png` previews |
| `jwst/` | `public/` | `.fits` |
| `k2/` | `public/` | FFI README and `.fits` |
| `kepler/` | `public/` | FFI README and `.fits` |
| `mast/` | `hlsp/`, `public/`, `skybackgrounds/` | JADES bundle `.zip` |
| `panstarrs/` | `ps1/` | HATS properties, Parquet |
| `roman/` | `crds/`, `nexus/` | CRDS configuration |
| `sdss/` | `public/` | HATS collection properties |
| `tess/` | `public/` | engineering `.xml`, `.tsc` |

Suffixes above are listing evidence, not a promise that all files in a prefix share a format. Actual magic/footer parsing confirmed Parquet, FITS and gzip-compressed FITS in the selected samples. [07 output](snippets/07-catalogs.out), [08 output](snippets/08-fits-recipes.out).

Catalog keys use paths such as `gaia/gaia_dr3/public/hats/gaia/dataset/Norder=2/Dir=0/Npix=0.parquet`. The inspected PS1 partition uses `Norder=10/Dir=8760000/Npix=8765439.parquet`. Treat these as partition selectors; do not assume a single flat table or scan the entire prefix to get a few records. Gaia collection metadata names a primary table, margin tables and indexes. [07 command](snippets/07-catalogs.sh), [output](snippets/07-catalogs.out).

## How big?

**Measured lower bound: 2,231,586,201,121 bytes (2.23 decimal TB), across 10,475 listed objects. The complete bucket total is unknown.** The method takes at most the first 1,000 objects under each of the 11 prefixes and sums S3 `Size`. Ten pages were truncated. This is a lexical sample, not a random sample; extrapolating a whole-bucket point estimate would be unjustified. [Size command](snippets/06-size-sample.sh), [output](snippets/06-size-sample.out).

`sdss/` was fully listed: **475 objects, 91,616,567,239 bytes (91.6 GB)**. For perspective, just the first 1,000 TESS objects total 784.5 GB and the first 1,000 Pan-STARRS objects 626.0 GB. These are stored object sizes, including zero-byte markers, not decompressed table sizes. [06 output](snippets/06-size-sample.out).

## Schemas you can use

These are **sample-file schemas**, not a claim of uniformity across a mission. Full columns/types and row-group counts are saved in [catalog evidence](snippets/07-catalogs.out); HDUs, dimensions and FITS table column formats are in [FITS evidence](snippets/08-fits-recipes.out).

| Sample | Useful fields / structure |
|---|---|
| Gaia Parquet | `source_id`: INT64; `ra`, `dec`, `parallax`, `pmra`: DOUBLE; `phot_g_mean_mag`: FLOAT; `phot_variable_flag`: UTF8; `has_rvs`: BOOLEAN. Fields are optional. |
| PS1 detection Parquet | `objID`, `detectID`: BIGINT; `ra`, `dec`, `obsTime`, `psfFlux`, `psfFluxErr`: DOUBLE; `filterID`: SMALLINT. Nullable fields. |
| JWST FITS | Empty primary data; `INSTRUME=NIRCam-A`. `RESULT_PHASE`: 128×128 float32; `RESULT_PSF`: 270×270 float32; `PUPIL_MASK`: 128×128 int16; repeated `RAW_PSF` and calculation HDUs. |
| GALEX FITS.gz | `Aspect data`: 1,689 rows, 12 columns. `t`, `ra`, `dec`, `roll`, `roll_rad`, `X`, `Y`, `Z`, `xdot`, `ydot`, `zdot`: FITS `1D`; `status_flag`: `1J`. Column units are absent in this sample. |

The Gaia object is 326,735,363 bytes, but its footer is only 150,021 bytes and reports four row groups containing 726,621 rows. The script builds a temporary sparse file containing only its header/footer for metadata inspection; that sparse file must **not** be used for row queries. [07 script](snippets/07-catalogs.sh), [output](snippets/07-catalogs.out).

## Three proven recipes

### 1. Pull a catalog detection with SQL

Run `bash stpubdata/snippets/07-catalogs.sh`. After HEAD and footer inspection, it reads the complete **17,516-byte** PS1 partition and runs:

```sql
SELECT objID, detectID, ra, dec, obsTime, filterID, psfFlux
FROM detections WHERE psfFlux > 0 LIMIT 5;
```

Result: one detection, `objID=65140731493746935`, `ra=73.14948092`, `dec=-35.71104505`, `psfFlux=1.37127e-05`. The partition contains one row; this demonstrates extraction, not a representative survey sample. [Executable recipe](snippets/07-catalogs.sh), [real result](snippets/07-catalogs.out).

### 2. Inspect and summarize a JWST image product

Run `bash stpubdata/snippets/08-fits-recipes.sh`. Its first input is `jwst/public/O2022030903/O2022030903-NRCA3_FULL-1.fits` (3,576,960 bytes). It checks the first FITS header block, loads the bounded object with Astropy, lists HDUs, and computes finite counts and image statistics. `RESULT_PHASE` has 16,384 finite pixels, range −4.416810 to 4.591748; `RESULT_PSF` is 270×270. These are the selected product's arrays, not an assertion that every JWST object is a calibrated sky image. [Executable recipe](snippets/08-fits-recipes.sh), [real result](snippets/08-fits-recipes.out).

### 3. Extract a pointing history from compressed FITS

The same script's second input is `galex/GR6/pipe/01-vsn/03000-MISDR1_24278_0266/d/00-visits/0001-img/07-try/MISDR1_24278_0266_0001-asp.fits.gz` (119,996 bytes). It checks gzip magic, opens the table with Astropy, prints its schema and first row, and calculates column ranges. All 1,689 rows have `status_flag=0`; `ra` spans 146.030272–146.064944, `dec` spans 1.179911–1.204546. The script deliberately does not infer missing time/angle units. [Executable recipe](snippets/08-fits-recipes.sh), [real result](snippets/08-fits-recipes.out).

## Verification, budget and gotchas

```bash
bash stpubdata/verify.sh
```

All eight snippets passed in the final run. The verifier saves fresh `.out` files, continues after errors, and exits nonzero if any snippet fails. It does not require outputs to remain byte-identical as the bucket evolves. [Verifier](verify.sh), [recorded transcript](snippets/verify.out).

- A successful catalog run transfers 179,314 object bytes; both FITS recipes together transfer 3,702,716. The large Gaia object is never downloaded in full. Listings are bounded separately; the size-sample output records their JSON lengths. [07 output](snippets/07-catalogs.out), [08 output](snippets/08-fits-recipes.out), [06 output](snippets/06-size-sample.out).
- Anonymous listing, HEAD and ranged GET all worked on the tested paths. This does not establish access to every object. Each CLI S3 request includes `--no-sign-request`. [02 script](snippets/02-root.sh), [07 script](snippets/07-catalogs.sh), [08 script](snippets/08-fits-recipes.sh).
- Empty directory-marker objects are present. Some individual objects exceed this project's entire 200 MB budget: the sampled Kepler/K2 FFIs are 407,894,400 bytes each. Do not recursively copy these prefixes for exploration. [Layout evidence](snippets/05-layout.out).
- Initial restricted-tool DNS failures and a corrected DuckDB view-binding error are recorded in [notes.md](notes.md). Network-enabled execution resolved connectivity; the successful network probe is recorded in [03 output](snippets/03-network.out). No observed error was evidence of S3 `AccessDenied`.
- Keep `.venv/` and `.uv-cache/` local and uncommitted. Recipes delete temporary objects. Bucket text is printed as data and never executed. [Setup](snippets/01-environment.sh), [dependencies](snippets/04-install-duckdb.sh), [recipes](snippets/07-catalogs.sh).
