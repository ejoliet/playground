#!/usr/bin/env bash
set -euo pipefail
export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_EC2_METADATA_DISABLED=true AWS_PAGER='' AWS_MAX_ATTEMPTS=1
for prefix in gaia galex hst jwst k2 kepler mast panstarrs roman sdss tess; do
  echo "PREFIX $prefix/"
  aws s3api list-objects-v2 --bucket stpubdata --prefix "$prefix/" --delimiter / --max-keys 30 --no-paginate --no-sign-request --region us-east-1
  echo "SAMPLE OBJECTS $prefix/"
  aws s3api list-objects-v2 --bucket stpubdata --prefix "$prefix/" --max-keys 3 --no-paginate --no-sign-request --region us-east-1
 done
