# Measured HTTP replay, cold 256 KiB cache

Median seconds at 100 ms injected RTT, 50 MiB/s per-request transfer delay. Three repeats; see summary.csv for min/max and all RTTs.

| Workload | None | Cache | Fixed | Adaptive | Stride |
|---|---:|---:|---:|---:|---:|
| fits_random | 1.821 | 1.813 | 1.730 | 1.817 | 1.819 |
| fits_rows | 1.813 | 1.816 | 0.306 | 0.506 | 0.506 |
| parquet_columns | 0.917 | 0.917 | 0.917 | 0.919 | 1.122 |
| parquet_prebuffer | 0.515 | 0.518 | 0.515 | 0.516 | 0.618 |
| phase_change | 3.223 | 3.232 | 1.731 | 1.918 | 1.913 |
| random | 3.231 | 3.236 | 3.264 | 3.234 | 3.221 |
| sequential | 3.233 | 3.233 | 0.204 | 0.406 | 0.406 |
| sqlite_random | 3.232 | 2.626 | 2.958 | 2.621 | 2.623 |
| sqlite_scan | 2.022 | 2.015 | 0.306 | 0.707 | 0.710 |
| stride | 3.225 | 3.231 | 3.270 | 3.230 | 3.334 |
| zip_cluster | 2.729 | 2.729 | 1.932 | 2.034 | 2.035 |
| zip_metadata | 2.424 | 0.306 | 0.303 | 0.304 | 0.303 |
| zip_random | 2.726 | 2.729 | 1.934 | 2.733 | 2.729 |

All outputs were verified byte-for-byte against the immutable fixture during replay.

# fsspec at 100 ms RTT

Wall time includes draining background fetches. Three repeats; 192 KiB resident cache plus a 64 KiB background-result allowance. Block-cache uses the same resident allowance.

| Workload | Think/read (ms) | Block median (s) | Background median (s) | Block requests | Background requests |
|---|---:|---:|---:|---:|---:|
| sequential | 0 | 0.207 | 0.311 | 2 | 3 |
| sequential | 20 | 0.853 | 0.835 | 2 | 4 |
| random | 0 | 3.324 | 3.635 | 32 | 48 |
| random | 20 | 3.962 | 4.350 | 32 | 51 |
| fits_rows | 0 | 0.312 | 0.311 | 3 | 3 |
| fits_rows | 20 | 0.674 | 0.551 | 3 | 4 |
| zip_cluster | 0 | 1.034 | 1.039 | 10 | 10 |
| zip_cluster | 20 | 1.581 | 1.199 | 10 | 11 |
| sqlite_random | 0 | 2.998 | 3.119 | 29 | 41 |
| sqlite_random | 20 | 3.644 | 3.749 | 29 | 45 |
