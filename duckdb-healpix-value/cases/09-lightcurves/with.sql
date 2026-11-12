WITH selected AS (WITH intervals AS (SELECT unnest(moc_ranges(moc_from_cone(0.,0.,.5,12))) AS x),
        pixels AS (SELECT unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
        candidates AS MATERIALIZED (SELECT cat.* FROM cat SEMI JOIN pixels ON (_healpix_29 >> 34)=bucket)
        SELECT id FROM candidates WHERE sky_in_cone(ra,"dec",0.,0.,.5)) SELECT p.id,p.epoch,p.flux FROM read_parquet('data/phot-1000000.parquet') p JOIN selected USING(id);
