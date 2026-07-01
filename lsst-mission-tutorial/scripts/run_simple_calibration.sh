#!/usr/bin/env bash
set -euo pipefail

source /opt/lsst/software/stack/loadLSST.bash
setup lsst_distrib

cd /home/lsst/mnt/demo/pipelines_check-29.2.1
export PYTHONPATH="/home/lsst/mnt/python:${PYTHONPATH:-}"

pipetask run \
  -b DATA_REPO \
  -i demo_collection \
  -o my_mission/run1 \
  -p /home/lsst/mnt/pipelines/simple_calibration.yaml \
  -d "instrument='HSC'"

python /home/lsst/mnt/src/validate_custom_output.py
