-- Python registers Arrow table indexed(id,pix); see without.py.
COPY (SELECT * FROM indexed ORDER BY pix) TO 'tmp/index.parquet' (FORMAT PARQUET);
