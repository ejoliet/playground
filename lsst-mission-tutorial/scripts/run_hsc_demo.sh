#!/usr/bin/env bash
set -euo pipefail

source /opt/lsst/software/stack/loadLSST.bash
setup lsst_distrib

mkdir -p /home/lsst/mnt/demo
cd /home/lsst/mnt/demo

if [[ ! -d pipelines_check-29.2.1 ]]; then
  curl -L https://github.com/lsst/pipelines_check/archive/29.2.1.tar.gz | tar xvzf -
fi

cd pipelines_check-29.2.1
setup -r .
./bin/run_demo.sh

butler query-collections DATA_REPO
butler query-datasets DATA_REPO calexp --collections demo_collection
