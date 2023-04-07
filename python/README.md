# environment

use Dockerfile to run a python container

then

`dr run -it --rm -v $PWD:/root/python 850f8694d221 /bin/bash`


To run postgres locally
`docker run --name postgresql -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -p 5432:5432 -v $data:/var/lib/postgresql/data -d postgres`
