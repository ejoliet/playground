WITH r AS (SELECT rid,unnest(moc_ranges(moc)) AS x FROM regions)
SELECT rid,count(*) FROM cat JOIN r ON _healpix_29>=x.lo AND _healpix_29<x.hi GROUP BY rid;
