"""Render evidence charts as standalone SVG without extra dependencies."""
import csv
from pathlib import Path

ROOT = Path(__file__).parent

def chart(source, target, title):
    rows = list(csv.DictReader((ROOT / source).open()))
    width, height = 740, 350
    left, top, plot_w, plot_h = 70, 55, 610, 235
    times = [int(r['unix_time']) for r in rows]
    span = max(1, times[-1] - times[0])
    x = lambda i: left + (times[i] - times[0]) / span * plot_w
    y = lambda value: top + plot_h * (1 - value / 100)
    weight = [(x(i), y(float(r['weight_after']))) for i, r in enumerate(rows)]
    errors = [(x(i), y(min(100, float(r['error_rate']) * 100))) for i, r in enumerate(rows)]
    def line(points, color):
        path = ' '.join(f'{a:.1f},{b:.1f}' for a, b in points)
        dots = ''.join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{color}"/>' for a, b in points)
        return f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="3"/>{dots}'
    ticks = ''.join(f'<line x1="{left}" x2="{left+plot_w}" y1="{y(t)}" y2="{y(t)}" stroke="#ddd"/><text x="{left-12}" y="{y(t)+4}" text-anchor="end" font-size="12">{t}%</text>' for t in (0, 25, 50, 75, 100))
    labels = ''.join(f'<text x="{x(i):.1f}" y="{top+plot_h+22}" text-anchor="middle" font-size="11">{times[i]-times[0]}s</text>' for i in range(len(rows)))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="{left}" y="30" font-size="19" font-family="sans-serif">{title}</text>
<g font-family="sans-serif" fill="#222">{ticks}{labels}
<line x1="{left}" x2="{left}" y1="{top}" y2="{top+plot_h}" stroke="#555"/>
<line x1="{left}" x2="{left+plot_w}" y1="{top+plot_h}" y2="{top+plot_h}" stroke="#555"/>
{line(weight, '#2563eb')}{line(errors, '#dc2626')}
<text x="{left}" y="330" fill="#2563eb" font-size="13">● v2 traffic weight</text>
<text x="{left+205}" y="330" fill="#dc2626" font-size="13">● v2 backend error rate</text>
</g></svg>'''
    (ROOT / target).write_text(svg)

chart('bad-release.csv', 'bad-release.svg', 'Bad v2: automatic rollback')
chart('good-release.csv', 'good-release.svg', 'Healthy v2: automatic promotion')

import json
r = json.loads((ROOT / 'reliability.json').read_text())
backend = r['backend_error_percent']
client = r['client_error_percent']
max_pct = 35
bars = []
for index, (label, value, count, total, color) in enumerate([
    ('Backend', backend, r['backend_500'], r['backend_total'], '#dc2626'),
    ('Meshed client', client, r['client_500'], r['client_total'], '#2563eb'),
]):
    y0 = 80 + index * 90
    w = 500 * value / max_pct
    bars.append(f'<text x="30" y="{y0+20}" font-size="15">{label}</text><rect x="170" y="{y0}" width="{w:.1f}" height="32" fill="{color}"/><text x="{185+w:.1f}" y="{y0+21}" font-size="14">{value:.2f}% ({int(count)}/{int(total)})</text>')
svg = '<svg xmlns="http://www.w3.org/2000/svg" width="850" height="300" viewBox="0 0 850 300"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#222"><text x="30" y="35" font-size="19">FLAKY v1: backend vs client failures</text>' + ''.join(bars) + f'<text x="30" y="275" font-size="13">Linkerd retry attempts: {int(r["mesh_retries"])}</text></g></svg>'
(ROOT / 'reliability.svg').write_text(svg)

split = '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="220" viewBox="0 0 700 220"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#222"><text x="25" y="35" font-size="19">Observed /version split (200 requests)</text><text x="25" y="90" font-size="15">v1</text><rect x="90" y="65" width="442.5" height="32" fill="#2563eb"/><text x="545" y="87" font-size="14">177 / 200 = 88.5%</text><text x="25" y="160" font-size="15">v2</text><rect x="90" y="135" width="57.5" height="32" fill="#16a34a"/><text x="160" y="157" font-size="14">23 / 200 = 11.5%</text></g></svg>'
(ROOT / 'traffic-split.svg').write_text(split)
