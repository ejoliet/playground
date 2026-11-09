import os
from pathlib import Path
os.mkdir('created')
with Path('created/a').open('wb') as f:
    f.write(b'abc\x00def')
with open('created/a', 'r+b') as f:
    f.seek(3)
    f.write(b'!')
    f.truncate(5)
    f.flush()
    print(f.tell())
    f.seek(0)
    print(f.read())
os.rename('created/a', 'created/b')
print(os.listdir('created'))
os.unlink('created/b')
