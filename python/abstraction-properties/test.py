class DBSerializer2(Serializer):
    def __init__(self, dbname):
        self.dbname = dbname

    def serialize(self, obj):
        conn = sqlite3.connect(self.dbname)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS data (id INTEGER PRIMARY KEY, data TEXT)')
        c.execute('INSERT INTO data VALUES (?, ?)', (1, json.dumps(obj)))
        conn.commit()
        conn.close()

    def deserialize(self):
        conn = sqlite3.connect(self.dbname)
        c = conn.cursor()
        c.execute('SELECT data FROM data WHERE id = 1')
        data = c.fetchone()[0]
        conn.close()
        return json.loads(data)


def test_serializer(serializer):
    # Create GaiaObject and serialize
    obj = GaiaObject(45.67, -12.34)
    serializer.serialize(obj.to_dict())

    # Deserialize object and verify
    data = serializer.deserialize()
    print(data)
    obj2 = GaiaObject.from_dict(data)
    assert obj.ra == obj2.ra
    assert obj.dec == obj2.dec


def test_file_serializer():
    serializer = FileSerializer('test_data.json')
    test_serializer(serializer)


def test_db_serializer():
    serializer = DBSerializer2('test_data.db')
    test_serializer(serializer)

test_file_serializer()
test_db_serializer()
