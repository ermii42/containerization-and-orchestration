#!/usr/bin/env bash
set -euo pipefail
namespace=${1:-orders}
out=${2:-scripts/matrix.csv}
api_peer=$(kubectl -n "$namespace" get pod -l app=api -o jsonpath='{.items[1].status.podIP}')
worker_peer=$(kubectl -n "$namespace" get pod -l app=worker -o jsonpath='{.items[1].status.podIP}')
printf 'source,target,actual,detail\n' > "$out"
for source in client stranger api worker postgres; do
  case "$source" in
    api|worker) pod=$(kubectl -n "$namespace" get pod -l app="$source" -o jsonpath='{.items[0].metadata.name}') ;;
    postgres) pod=orders-postgres-1 ;;
    *) pod="$source" ;;
  esac
  kubectl -n "$namespace" exec -i "$pod" -- python3 - "$source" "$api_peer" "$worker_peer" < scripts/matrix-probe.py >> "$out"
done
cat "$out"
