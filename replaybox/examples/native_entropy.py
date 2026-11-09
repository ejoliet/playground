import ctypes
buf = ctypes.create_string_buffer(16)
libc = ctypes.CDLL(None)
assert libc.getrandom(buf, 16, 0) == 16
print(buf.raw.hex())
