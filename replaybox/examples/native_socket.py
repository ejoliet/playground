import ctypes
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.socket(2, 1, 0)
print('blocked' if fd == -1 and ctypes.get_errno() == 1 else 'allowed')
if fd >= 0:
    libc.close(fd)
