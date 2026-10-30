#!/usr/bin/env python3
import csv
import datetime
import sys
import time
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else 'http://api.orders.svc.cluster.local/orders'
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 90
writer = csv.writer(sys.stdout)
writer.writerow(['timestamp', 'status', 'latency_ms', 'error'])
end = time.monotonic() + duration
while time.monotonic() < end:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            response.read()
            status, error = response.status, ''
    except Exception as exc:
        status, error = 0, str(exc).replace(',', ';')
    writer.writerow([now, status, round((time.monotonic() - start) * 1000, 1), error])
    sys.stdout.flush()
    time.sleep(0.5)
