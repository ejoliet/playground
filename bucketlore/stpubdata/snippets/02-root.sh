#!/usr/bin/env bash
set -euo pipefail
export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_EC2_METADATA_DISABLED=true AWS_PAGER='' AWS_MAX_ATTEMPTS=1
aws s3api list-objects-v2 --bucket stpubdata --delimiter / --max-keys 100 --no-paginate --no-sign-request --region us-east-1 --cli-connect-timeout 10 --cli-read-timeout 20
