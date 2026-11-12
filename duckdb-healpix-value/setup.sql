SET disabled_optimizers='cte_filter_pusher';
CREATE MACRO sep(a,b,c,d) AS degrees(atan2(sqrt(pow(cos(radians(d))*sin(radians(c-a)),2)+pow(cos(radians(b))*sin(radians(d))-sin(radians(b))*cos(radians(d))*cos(radians(c-a)),2)),sin(radians(b))*sin(radians(d))+cos(radians(b))*cos(radians(d))*cos(radians(c-a))));
