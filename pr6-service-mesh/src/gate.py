"""Prometheus-driven Linkerd HTTPRoute canary gate, run on the VM."""
import argparse
import csv
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

PROM = os.getenv('PROM_URL', 'http://127.0.0.1:9090/api/v1/query')
ROUTE = ['kubectl', '-n', 'orders', 'get', 'httproute', 'api-split', '-o', 'json']


def query(expr):
    url = PROM + '?' + urllib.parse.urlencode({'query': expr})
    data = json.load(urllib.request.urlopen(url, timeout=5))
    results = data['data']['result']
    return float(results[0]['value'][1]) if results else 0.0


def current_weight():
    route = json.loads(subprocess.check_output(ROUTE))
    return route['spec']['rules'][0]['backendRefs'][1]['weight']


def set_weight(weight):
    patch = [
        {'op': 'replace', 'path': '/spec/rules/0/backendRefs/0/weight', 'value': 100 - weight},
        {'op': 'replace', 'path': '/spec/rules/0/backendRefs/1/weight', 'value': weight},
    ]
    subprocess.run(['kubectl', '-n', 'orders', 'patch', 'httproute', 'api-split', '--type=json', '-p', json.dumps(patch)], check=True, stdout=subprocess.DEVNULL)


parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--seconds', type=int, default=180)
args = parser.parse_args()
selector = 'version="v2",service="api-v2",path="/order"'
total_q = 'sum(increase(http_requests_total{' + selector + '}[1m]))'
errors_q = 'sum(increase(http_requests_total{' + selector + ',status=~"5.."}[1m]))'
latency_q = 'histogram_quantile(0.95,sum by (le) (rate(http_request_duration_seconds_bucket{' + selector + '}[1m])))'
with open(args.output, 'w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['unix_time', 'weight_before', 'requests_1m', 'errors_1m', 'error_rate', 'p95_s', 'weight_after', 'decision'])
    until = time.monotonic() + args.seconds
    while time.monotonic() < until:
        before = current_weight()
        total = query(total_q)
        errors = query(errors_q)
        p95 = query(latency_q)
        rate = min(1.0, errors / total) if total else 0
        after = before
        decision = 'wait'
        if total >= 10:
            if rate > .05:
                after = 0
                decision = 'rollback'
            elif p95 <= .5:
                after = min(100, before + 20)
                decision = 'advance'
        if after != before:
            set_weight(after)
        row = [round(time.time()), before, round(total, 2), round(errors, 2), round(rate, 4), round(p95, 4), after, decision]
        writer.writerow(row)
        stream.flush()
        print(','.join(map(str, row)), flush=True)
        if after in (0, 100):
            break
        time.sleep(15)
