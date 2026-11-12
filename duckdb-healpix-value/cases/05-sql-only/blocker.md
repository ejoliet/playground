Pure SQL conversion was implemented and measured. It assigns exact (RA=0,Dec=0)
to a different boundary cell from cdshealpix and astropy-healpix; preserved as xfail.
Native CLI loading remains unverified. A Python shim is not a CLI deployment test.
