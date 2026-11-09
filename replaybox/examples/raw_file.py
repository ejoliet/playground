import os
fd = os.open('input.txt', os.O_RDONLY)
print(os.read(fd, 100).decode())
os.close(fd)
