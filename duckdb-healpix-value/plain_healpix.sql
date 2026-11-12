-- Vectorized SQL-only NESTED pixels on valid ICRS coordinates, no Python UDF.
CREATE MACRO spread16(v) AS ((v | (v << 16)) & 281470681808895);
CREATE MACRO spread8(v) AS ((v | (v << 8)) & 71777214294589695);
CREATE MACRO spread4(v) AS ((v | (v << 4)) & 1085102592571150095);
CREATE MACRO spread2(v) AS ((v | (v << 2)) & 3689348814741910323);
CREATE MACRO spread1(v) AS ((v | (v << 1)) & 6148914691236517205);
CREATE MACRO spread_bits(v) AS spread1(spread2(spread4(spread8(spread16(v)))));
CREATE MACRO plain_pixels(source,ord) AS TABLE (
 WITH a AS (SELECT id, (1::BIGINT << ord) AS ns, sin(radians("dec")) AS z, ra/90 AS tt FROM query_table(source)),
 b AS (SELECT *,abs(z) AS za,least(3,floor(tt))::BIGINT AS ntt FROM a),
 c AS (SELECT *, floor(ns*(.5+tt-.75*z))::BIGINT AS ep,
 floor(ns*(.5+tt+.75*z))::BIGINT AS em,
 ns*sqrt(3*(1-za)) AS tmp FROM b),
 d AS (SELECT *,least(ns-1,floor((tt-ntt)*tmp))::BIGINT AS pp,
 least(ns-1,floor((1-tt+ntt)*tmp))::BIGINT AS pm,
 ep >> ord AS fp,em >> ord AS fm FROM c),
 e AS (SELECT id,ns,
 CASE WHEN za<=2./3 THEN CASE WHEN fp=fm THEN fp | 4 WHEN fp<fm THEN fp ELSE fm+8 END ELSE CASE WHEN z>=0 THEN ntt ELSE ntt+8 END END AS face,
 CASE WHEN za<=2./3 THEN em & (ns-1) WHEN z>=0 THEN ns-pm-1 ELSE pp END AS ix,
 CASE WHEN za<=2./3 THEN ns-(ep & (ns-1))-1 WHEN z>=0 THEN ns-pp-1 ELSE pm END AS iy FROM d)
 SELECT id, face*ns*ns + spread_bits(ix) + (spread_bits(iy) << 1) AS pix FROM e
);
