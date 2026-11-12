WITH a AS MATERIALIZED (SELECT *,cos(radians("dec"))*cos(radians(ra)) AS x,cos(radians("dec"))*sin(radians(ra)) AS y,sin(radians("dec")) AS z FROM cat),
        b0 AS MATERIALIZED (SELECT *,cos(radians("dec"))*cos(radians(ra)) AS x,cos(radians("dec"))*sin(radians(ra)) AS y,sin(radians("dec")) AS z FROM other),
        b AS (SELECT *,unnest([floor("dec"*3600)::BIGINT-1,floor("dec"*3600)::BIGINT,floor("dec"*3600)::BIGINT+1]) AS bucket FROM b0)
        , candidates AS MATERIALIZED (SELECT a.id,b.id AS other_id,a.ra AS ara,a."dec" AS adec,b.ra AS bra,b."dec" AS bdec FROM a JOIN b ON floor(a."dec"*3600)::BIGINT=b.bucket
        AND abs(a.x-b.x)<=2*sin(radians(1./3600)/2)+1e-14
        AND abs(a.y-b.y)<=2*sin(radians(1./3600)/2)+1e-14
        AND abs(a.z-b.z)<=2*sin(radians(1./3600)/2)+1e-14) SELECT id,other_id FROM candidates WHERE sky_in_cone(ara,adec,bra,bdec,1./3600);
