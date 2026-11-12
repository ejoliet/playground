WITH intervals AS MATERIALIZED (
            SELECT id AS other_id,ra,"dec",unnest(moc_ranges(moc_from_cone(ra,"dec",1./3600,12))) AS x FROM other),
            r AS (SELECT other_id,ra,"dec",unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
            candidates AS MATERIALIZED (
            SELECT a.id,r.other_id,a.ra AS ara,a."dec" AS adec,r.ra AS bra,r."dec" AS bdec
            FROM cat a JOIN r ON (a._healpix_29 >> 34)=r.bucket)
            SELECT id,other_id FROM candidates WHERE sky_in_cone(ara,adec,bra,bdec,1./3600);
