SELECT rid,count(*) FROM cat JOIN regions ON _healpix_29>=lo AND _healpix_29<hi GROUP BY rid;
