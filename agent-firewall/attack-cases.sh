#!/usr/bin/env bash
# Reproducible probes, not an LLM agent. Run after start-demo.sh, from this folder.
set -uo pipefail
export PATH="$PWD/.local/bin:$PATH"
export KUBECONFIG="$PWD/.local/agent.kubeconfig"
probe() {
  echo "+ kubectl $*"
  kubectl --request-timeout=20s "$@"
  echo "exit=$?"
}
probe delete namespace production-demo --wait=false
probe scale deployment storefront --replicas=0
probe patch role reader --type=merge -p '{"rules":[{"apiGroups":["*"],"resources":["*"],"verbs":["*"]}]}'
probe scale deployment storefront --replicas=3
probe patch configmap settings --type=merge -p '{"data":{"auth_enabled":"false"}}'
probe get namespace production-demo
probe get deployment storefront -o jsonpath='{.spec.replicas}'
probe get role reader -o jsonpath='{.rules}'
probe get configmap settings -o jsonpath='{.data}'
