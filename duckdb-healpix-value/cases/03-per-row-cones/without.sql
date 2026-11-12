WITH c AS MATERIALIZED (SELECT *,cos(radians("dec"))*cos(radians(ra)) AS x,cos(radians("dec"))*sin(radians(ra)) AS y FROM cat),
            w0 AS MATERIALIZED (SELECT *,cos(radians("dec"))*cos(radians(ra)) AS x,cos(radians("dec"))*sin(radians(ra)) AS y,2*sin(radians(radius)/2)+1e-14 AS chord FROM watch),
            w AS (SELECT *,unnest(range(floor(("dec"-radius)*1000)::BIGINT,floor(("dec"+radius)*1000)::BIGINT+1)) AS bucket FROM w0)
            , candidates AS MATERIALIZED (SELECT wid,id,c.ra AS cra,c."dec" AS cdec,w.ra AS wra,w."dec" AS wdec,w.radius AS radius FROM c JOIN w ON floor(c."dec"*1000)::BIGINT=w.bucket AND c."dec" BETWEEN w."dec"-w.radius AND w."dec"+w.radius
            AND abs(c.x-w.x)<=w.chord AND abs(c.y-w.y)<=w.chord) SELECT wid,id FROM candidates WHERE sep(cra,cdec,wra,wdec)<=radius;
