WITH selected AS (
 SELECT id FROM cat WHERE "dec" BETWEEN -.5 AND .5
 AND sep(ra,"dec",0,0)<=.5
)
SELECT p.* FROM photometry p JOIN selected USING(id);
