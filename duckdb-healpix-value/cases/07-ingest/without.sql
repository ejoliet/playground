-- Python registers Arrow table indexed(id,pix,ra,dec); see without.py.
COPY (SELECT * FROM indexed ORDER BY pix) TO 'tmp/index.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
