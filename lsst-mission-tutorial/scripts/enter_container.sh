#!/usr/bin/env bash
set -euo pipefail

IMAGE="lsstsqre/centos:7-stack-lsst_distrib-v29_2_1"
WORKDIR="/home/lsst/mnt"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

docker run -it \
  --platform linux/amd64 \
  -v "${ROOT_DIR}:${WORKDIR}" \
  "${IMAGE}"
