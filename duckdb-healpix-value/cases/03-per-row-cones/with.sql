WITH intervals AS MATERIALIZED (SELECT wid,ra,"dec",radius,unnest(moc_ranges(moc_from_cone(ra,"dec",radius,12))) AS x FROM watch),
        r AS (SELECT wid,ra,"dec",radius,unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
        candidates AS MATERIALIZED (SELECT wid,id,c.ra AS ara,c."dec" AS adec,r.ra AS bra,r."dec" AS bdec,r.radius FROM cat c JOIN r ON (c._healpix_29 >> 34)=r.bucket)
        SELECT wid,id FROM candidates WHERE sky_in_cone(ara,adec,bra,bdec,radius);
