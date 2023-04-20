import json
from typing import Dict, Type
from abc import ABC, abstractmethod
import sqlite3

class Serializer(ABC):
    @abstractmethod
    def serialize(self, obj):
        pass

    @abstractmethod
    def deserialize(self, data):
        pass

class FileSerializer(Serializer):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def serialize(self, obj):
        with open(self.file_path, 'w') as f:
            json.dump(obj.__dict__, f)

    def deserialize(self):
        with open(self.file_path, 'r') as f:
            data = json.load(f)
        return data

class DBSerializer(Serializer):
    def __init__(self, table_name: str, connection: sqlite3.Connection):
        self.table_name = table_name
        self.connection = connection

        cursor = self.connection.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {self.table_name} (data BLOB)")

    def serialize(self, obj):
        cursor = self.connection.cursor()
        cursor.execute(f"INSERT INTO {self.table_name} VALUES (?)", (json.dumps(obj.__dict__),))
        self.connection.commit()

    def deserialize(self):
        cursor = self.connection.cursor()
        cursor.execute(f"SELECT data FROM {self.table_name} ORDER BY ROWID DESC LIMIT 1")
        data = cursor.fetchone()[0]
        return json.loads(data)

class SerializerFactory:
    @staticmethod
    def create_serializer(serializer_type: str, config: Dict) -> Serializer:
        if serializer_type == "file":
            return FileSerializer(config["file_path"])
        elif serializer_type == "db":
            connection = sqlite3.connect(config["db_path"])
            return DBSerializer(config["table_name"], connection)
        else:
            raise ValueError(f"Unsupported serializer type: {serializer_type}")

class GaiaObject:
    def __init__(self, ra: float, dec: float):
        self.ra = ra
        self.dec = dec

if __name__ == '__main__':
    with open('config.json', 'r') as f:
        config = json.load(f)

    serializer_type = config["serializer_type"]
    serializer_config = config[serializer_type]

    serializer = SerializerFactory.create_serializer(serializer_type, serializer_config)

    gaia_obj = GaiaObject(86.5, 32.2)
    serializer.serialize(gaia_obj)

    deserialized_obj = serializer.deserialize()
    print(deserialized_obj)

