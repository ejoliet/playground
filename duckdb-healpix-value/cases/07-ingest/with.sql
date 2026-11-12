COPY (SELECT id,ra,"dec",hpx_ang2pix(12,ra,"dec") AS pix FROM cat ORDER BY pix)
TO 'tmp/index.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
