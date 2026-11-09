#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p .local
export PATH="$PWD/.local/bin:$PATH"
command -v kind
command -v kubectl
kind create cluster --name agent-firewall --image kindest/node:v1.34.0 --kubeconfig "$PWD/.local/admin.kubeconfig" --wait 90s
kubectl --kubeconfig .local/admin.kubeconfig apply -f fixtures.yaml
python3 - <<'PY'
import json, secrets
from pathlib import Path
agent, reviewer = secrets.token_hex(32), secrets.token_hex(32)
Path('.local/tokens.env').write_text(f'export AGENT_TOKEN={agent}\nexport REVIEWER_TOKEN={reviewer}\n')
config = {'apiVersion':'v1','kind':'Config','clusters':[{'name':'firewall','cluster':{'server':'http://127.0.0.1:8080'}}],
          'users':[{'name':'agent','user':{'token':agent}}],
          'contexts':[{'name':'firewall','context':{'cluster':'firewall','user':'agent','namespace':'production-demo'}}],
          'current-context':'firewall'}
Path('.local/agent.kubeconfig').write_text(json.dumps(config))
PY
source .local/tokens.env
kubectl --kubeconfig .local/admin.kubeconfig proxy --address 127.0.0.1 --port 8001 > .local/upstream.log 2>&1 &
upstream_pid=$!
trap 'kill "$upstream_pid" 2>/dev/null || true' EXIT
python3 firewall.py
