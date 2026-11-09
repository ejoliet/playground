import os
with open('output.txt', 'w') as f:
    f.write(os.environ['VALUE'])
