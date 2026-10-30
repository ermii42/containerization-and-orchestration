#!/usr/bin/env python3
"""Apply one random network fault via values.yaml; --restore restores the backup."""
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
chart = root / 'order-service/orders-chart'
values = chart / 'values.yaml'
backup = Path('/tmp/pr5-orders-values-before-fault.yaml')
state = Path('/tmp/pr5-orders-fault.json')
if sys.argv[1:] == ['--restore']:
    if not backup.exists():
        raise SystemExit('No saved values to restore')
    values.write_bytes(backup.read_bytes())
    state.unlink(missing_ok=True)
    backup.unlink()
    subprocess.run(['helm', 'upgrade', 'orders', str(chart), '-n', 'orders'], check=True)
    print('Restored values and Helm release')
    raise SystemExit(0)
if backup.exists():
    raise SystemExit('Fault already active; restore it first')
original = values.read_text()
head, marker, tail = original.partition('# --- networking ---')
if not marker:
    raise SystemExit('networkPolicy section not found')
faults = [
    ('dns-port', r'(?m)^(  dnsPort: )53$', '5353'),
    ('postgres-port', r'(?m)^(  postgresPort: )5432$', '5433'),
    ('api-port', r'(?m)^(  apiPort: )8000$', '8002'),
    ('client-label', r'(?m)^(    role: )client$', 'stranger'),
]
name, pattern, replacement = secrets.choice(faults)
changed, count = re.subn(pattern, lambda m: m.group(1) + replacement, tail, count=1)
if count != 1:
    raise SystemExit('Expected value was not found')
backup.write_text(original)
values.write_text(head + marker + changed)
state.write_text(json.dumps({'fault': name}) + '\n')
subprocess.run(['helm', 'upgrade', 'orders', str(chart), '-n', 'orders'], check=True)
print('A hidden network fault was applied through values.yaml')
