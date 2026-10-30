"""Measure backend and meshed client failures over the same requests."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
BASE = ['kubectl', '-n', 'orders', 'exec', 'deployment/mesh-client', '-c', 'client', '--']

def fetch(url):
    return subprocess.check_output(BASE + ['curl', '-sS', url], text=True)

def backend():
    text = fetch('http://api-v1.orders.svc.cluster.local/metrics')
    counts = {}
    for line in text.splitlines():
        if line.startswith('http_requests_total{') and 'path="/order"' in line and 'version="v1"' in line:
            status = re.search(r'status="(\d+)"', line).group(1)
            counts[status] = float(line.rsplit(' ', 1)[1])
    return counts

def retries():
    text = fetch('http://localhost:4191/metrics')
    return sum(float(line.rsplit(' ', 1)[1]) for line in text.splitlines() if line.startswith('outbound_http_route_retry_requests_total{') and 'parent_name="api-v1"' in line)

before, retry_before = backend(), retries()
cmd = "for i in $(seq 1 300); do curl -sS -o /dev/null -w '%{http_code}\\n' -H 'Content-Type: application/json' -d '{\"payload\":{\"test\":\"flaky\"}}' http://api-v1.orders.svc.cluster.local/order; done"
statuses = subprocess.check_output(BASE + ['sh', '-c', cmd], text=True).splitlines()
after, retry_after = backend(), retries()
backend_total = sum(after.values()) - sum(before.values())
backend_500 = after.get('500', 0) - before.get('500', 0)
client_500 = statuses.count('500')
result = {'client_total': len(statuses), 'client_500': client_500, 'backend_total': backend_total, 'backend_500': backend_500, 'mesh_retries': retry_after - retry_before, 'backend_error_percent': round(100*backend_500/backend_total, 2), 'client_error_percent': round(100*client_500/len(statuses), 2)}
(ROOT / 'reliability.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
