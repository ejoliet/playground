SELECT id FROM cat WHERE "dec" BETWEEN -.5 AND .5 AND s2_dwithin(point(ra,"dec"),point(0,0),radians(.5)*6371010);
