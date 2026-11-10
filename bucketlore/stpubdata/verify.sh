#!/usr/bin/env bash
# Rerun every snippet and save the current attempt's real output.
set -uo pipefail
cd "$(dirname "$0")"
export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null
export AWS_EC2_METADATA_DISABLED=true AWS_PAGER='' AWS_MAX_ATTEMPTS=1
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE
failed=0
for snippet in snippets/[0-9][0-9]-*.sh; do
  printf '\nRunning %s\n' "$snippet"
  if bash "$snippet" > "${snippet%.sh}.out" 2>&1; then
    cat "${snippet%.sh}.out"
    printf 'PASS %s\n' "$snippet"
  else
    code=$?
    cat "${snippet%.sh}.out"
    printf 'FAIL %s (exit %s)\n' "$snippet" "$code" >&2
    failed=1
  fi
done
exit "$failed"
