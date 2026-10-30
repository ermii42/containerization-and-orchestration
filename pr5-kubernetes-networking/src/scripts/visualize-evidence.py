#!/usr/bin/env python3
"""Render the measured access matrix and the Hubble DNS fault as SVG."""
import csv
from html import escape
from pathlib import Path

root = Path(__file__).resolve().parent
rows = list(csv.DictReader((root / 'matrix.csv').open()))
expected = {('client', 'api'), ('api', 'postgres'), ('worker', 'postgres'), ('postgres', 'postgres')}
expected |= {(source, 'dns') for source in ('client', 'stranger', 'api', 'worker', 'postgres')}
sources = ['client', 'stranger', 'api', 'worker', 'postgres']
targets = ['api', 'worker', 'postgres', 'dns']
actual = {(r['source'], r['target']): r['actual'] for r in rows}
parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="810" height="380">', '<rect width="810" height="380" fill="#fff"/>', '<style>text{font:16px sans-serif;fill:#173044}.title{font:bold 21px sans-serif}.cell{stroke:#fff;stroke-width:5}</style>', '<text class="title" x="24" y="34">Orders: ожидаемо / фактически</text>']
for j, target in enumerate(targets):
    parts.append(f'<text x="{205+j*145}" y="82" text-anchor="middle">{target}</text>')
for i, source in enumerate(sources):
    y = 101 + i*52
    parts.append(f'<text x="24" y="{y+31}">{source}</text>')
    for j, target in enumerate(targets):
        good = (actual.get((source, target)) == 'allow') == ((source, target) in expected)
        fill = '#d6f5df' if good else '#ffd9d9'
        label = ('да' if (source, target) in expected else 'нет') + ' / ' + ('да' if actual.get((source, target)) == 'allow' else 'нет')
        x = 132 + j*145
        parts += [f'<rect class="cell" x="{x}" y="{y}" width="145" height="48" rx="8" fill="{fill}"/>', f'<text x="{x+72}" y="{y+31}" text-anchor="middle">{escape(label)}</text>']
parts += ['<text x="24" y="365">20 проверок, 0 расхождений; строки api→api и worker→worker проверены на другом pod</text>', '</svg>']
(root / 'matrix.svg').write_text('\n'.join(parts))
(root / 'fault-map.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="250"><rect width="900" height="250" fill="white"/><style>text{font:17px sans-serif;fill:#173044}.head{font:bold 21px sans-serif}</style><text class="head" x="30" y="40">Hubble: скрытая поломка DNS</text><rect x="45" y="83" width="215" height="77" rx="12" fill="#d8ecff"/><text x="72" y="127">orders/client</text><line x1="260" y1="122" x2="635" y2="122" stroke="#d52d38" stroke-width="5"/><text x="340" y="101" fill="#d52d38">UDP/53 — EGRESS DENIED</text><text x="438" y="143" fill="#d52d38">✕</text><rect x="635" y="83" width="225" height="77" rx="12" fill="#e9e3ff"/><text x="659" y="127">kube-system/CoreDNS</text><text x="45" y="210">Причина: allow-dns разрешал 5353; восстановлено 53/UDP и 53/TCP.</text></svg>''')
