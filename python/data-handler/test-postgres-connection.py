import psycopg2
from urllib.parse import urlparse

conStr = "localhost://test:test@data_quality:5432"
p = urlparse(conStr)

pg_connection_dict = {
    'dbname': p.hostname,
    'user': p.username,
    'password': p.password,
    'port': p.port,
    'host': p.scheme
}

print(pg_connection_dict)
con = psycopg2.connect(**pg_connection_dict)
print(con)
