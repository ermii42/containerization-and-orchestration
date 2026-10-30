#!/usr/bin/env bash
set -euo pipefail
namespace=${1:-orders}
duration=${2:-90}
interval=${3:-5}
out=${4:-chaos.csv}
printf 'timestamp,pod,ip,node\n' > "$out"
end=$((SECONDS + duration))
while (( SECONDS < end )); do
  mapfile -t ready_api < <(kubectl -n "$namespace" get pods -l app=api --no-headers | awk '$2=="1/1" && $3=="Running" {print $1}')
  mapfile -t ready_worker < <(kubectl -n "$namespace" get pods -l app=worker --no-headers | awk '$2=="1/1" && $3=="Running" {print $1}')
  pods=("${ready_worker[@]}")
  if (( ${#ready_api[@]} >= 3 )); then
    pods+=("${ready_api[@]}")
  fi
  if (( ${#pods[@]} > 0 )); then
    pod=${pods[RANDOM % ${#pods[@]}]}
    read -r ip node < <(kubectl -n "$namespace" get pod "$pod" -o jsonpath='{.status.podIP}{" "}{.spec.nodeName}{"\n"}')
    printf '%s,%s,%s,%s\n' "$(date -u +%FT%TZ)" "$pod" "$ip" "$node" | tee -a "$out"
    kubectl -n "$namespace" delete pod "$pod" --wait=false >/dev/null
  fi
  sleep "$interval"
done
