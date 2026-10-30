#!/usr/bin/env python3
import csv
from datetime import datetime
from html import escape
from pathlib import Path
import sys

load_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'scripts/load-final.csv')
chaos_path = Path(sys.argv[2] if len(sys.argv) > 2 else 'scripts/chaos-final.csv')
out_path = Path(sys.argv[3] if len(sys.argv) > 3 else 'scripts/chaos-final.svg')
with load_path.open(newline='') as f:
    rows = list(csv.DictReader(f))
with chaos_path.open(newline='') as f:
    kills = list(csv.DictReader(f))
parse = datetime.fromisoformat
t0 = parse(rows[0]['timestamp']).timestamp()
t1 = parse(rows[-1]['timestamp']).timestamp()
width, height = 920, 340
left, right, top, bottom = 70, 850, 35, 275
x = lambda t: left + (t-t0)/(t1-t0)*(right-left)
max_ok = sum(r['status'] == '200' for r in rows)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', '<style>text{font:13px sans-serif;fill:#253044}.axis{stroke:#8b95a5;stroke-width:1}.kill{stroke:#e35050;stroke-width:1;opacity:.5}.ok{fill:none;stroke:#19a56b;stroke-width:3}.bad{fill:none;stroke:#cc3333;stroke-width:3}</style>']
for fraction in (0,.25,.5,.75,1):
    y = bottom-fraction*(bottom-top)
    svg += [f'<line class="axis" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" opacity=".25"/>', f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end">{round(fraction*max_ok)}</text>']
for kill in kills:
    kx = x(parse(kill['timestamp'].replace('Z','+00:00')).timestamp())
    svg.append(f'<line class="kill" x1="{kx:.1f}" y1="{top}" x2="{kx:.1f}" y2="{bottom}"/>')
points_ok, points_bad = [], []
ok = bad = 0
for row in rows:
    if row['status'] == '200': ok += 1
    else: bad += 1
    xx = x(parse(row['timestamp']).timestamp())
    points_ok.append(f'{xx:.1f},{bottom-ok/max_ok*(bottom-top):.1f}')
    points_bad.append(f'{xx:.1f},{bottom-bad/max_ok*(bottom-top):.1f}')
svg += [f'<polyline class="ok" points="{" ".join(points_ok)}"/>', f'<polyline class="bad" points="{" ".join(points_bad)}"/>', f'<text x="{left}" y="22">Service через DNS: {ok} успешных, {bad} ошибок; {len(kills)} удалений подов</text>', f'<text x="{left}" y="310">Начало {escape(rows[0]["timestamp"])}; красные линии — удаления, зелёная — успешные, красная — ошибки</text>', '</svg>']
out_path.write_text('\n'.join(svg))
