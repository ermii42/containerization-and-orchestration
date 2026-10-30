#!/usr/bin/env python3
import socket
import sys

source = sys.argv[1]
api_peer = sys.argv[2] if len(sys.argv) > 2 else 'api.orders.svc.cluster.local'
worker_peer = sys.argv[3] if len(sys.argv) > 3 else 'worker.orders.svc.cluster.local'
targets = [
    ('api', api_peer if source == 'api' else 'api.orders.svc.cluster.local', 8000 if source == 'api' else 80),
    ('worker', worker_peer if source == 'worker' else 'worker.orders.svc.cluster.local', 8001),
    ('postgres', 'orders-postgres-rw.orders.svc.cluster.local', 5432),
]
for name, host, port in targets:
    try:
        with socket.create_connection((host, port), timeout=2):
            result = 'allow'
    except OSError as exc:
        result = 'deny'
        print(f'{source},{name},{result},{type(exc).__name__}: {exc}')
        continue
    print(f'{source},{name},{result},')
try:
    socket.getaddrinfo('api.orders.svc.cluster.local', 80)
    print(f'{source},dns,allow,')
except OSError as exc:
    print(f'{source},dns,deny,{exc}')
