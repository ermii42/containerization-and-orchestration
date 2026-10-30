"""Simple repeatable POST /order benchmark; run on the VM."""
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
latencies = []
statuses = {}
for i in range(n):
    request = urllib.request.Request(url + '/order', data=json.dumps({'payload': {'bench': i}}).encode(), headers={'Content-Type': 'application/json'})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    latencies.append((time.perf_counter() - start) * 1000)
    statuses[status] = statuses.get(status, 0) + 1
latencies.sort()
print(json.dumps({'count': n, 'statuses': statuses, 'p50_ms': round(statistics.median(latencies), 2), 'p95_ms': round(latencies[int(n * .95) - 1], 2), 'mean_ms': round(statistics.mean(latencies), 2)}))
