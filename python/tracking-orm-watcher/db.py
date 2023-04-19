import sqlite3

class SQLiteTracking:
    def __init__(self, db_file):
        self.db_file = db_file

    def update_tracking(self, filename, status, retry):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("UPDATE pipeline_tracking SET status = ?, retry = ? WHERE filename = ?", (status, retry, filename))
        conn.commit()
        conn.close()

# to use:
#tracking = SQLiteTracking('path/to/database.db')
#tracking.update_tracking('example.csv', 'done', 0, 1)
