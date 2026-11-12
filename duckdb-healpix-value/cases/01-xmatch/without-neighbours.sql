WITH candidates AS MATERIALIZED (
            SELECT a.id,b.other_id,a.ra AS ara,a."dec" AS adec,b.bra,b.bdec FROM cat a JOIN neighbours b ON (a._healpix_29 >> 34)=b.bucket)
            SELECT id,other_id FROM candidates WHERE sep(ara,adec,bra,bdec)<=1./3600;
