def test_serializer(serializer):
    # Create GaiaObject and serialize
    obj = GaiaObject(45.67, -12.34, 3.14)
    serializer.serialize(obj.to_dict())

    # Deserialize object and verify
    data = serializer.deserialize()
    obj2 = GaiaObject.from_dict(data)
    assert obj.ra == obj2.ra
    assert obj.dec == obj2.dec
    assert obj.parallax == obj2.parallax


def test_file_serializer():
    serializer = FileSerializer('test_data.json')
    test_serializer(serializer)


def test_db_serializer():
    serializer = DBSerializer('test_data.db')
    test_serializer(serializer)

