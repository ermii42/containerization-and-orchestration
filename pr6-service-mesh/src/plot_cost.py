"""Draw the controlled API benchmark comparison from the saved measurements."""

import json
from pathlib import Path


root = Path(__file__).resolve().parent
baseline = json.loads((root / "ab-baseline.json").read_text())
mesh = json.loads((root / "ab-mesh.json").read_text())
resources = json.loads((root / "ab-resources.json").read_text())

rows = [
    ("p50 latency", "ms", baseline["p50_ms"], mesh["p50_ms"], 2),
    ("p95 latency", "ms", baseline["p95_ms"], mesh["p95_ms"], 2),
    (
        "Memory: API + proxy",
        "MiB",
        (resources["baseline"]["api_memory_bytes"] + resources["baseline"]["proxy_memory_bytes"]) / 2**20,
        (resources["mesh"]["api_memory_bytes"] + resources["mesh"]["proxy_memory_bytes"]) / 2**20,
        2,
    ),
    (
        "CPU: API + proxy",
        "m",
        1000 * (resources["baseline"]["api_cpu_cores"] + resources["baseline"]["proxy_cpu_cores"]),
        1000 * (resources["mesh"]["api_cpu_cores"] + resources["mesh"]["proxy_cpu_cores"]),
        1,
    ),
]

parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="720" viewBox="0 0 1100 720">',
    '<rect width="1100" height="720" fill="#fff"/>',
    '<style>text{font-family:Arial,sans-serif;fill:#1d2733} .title{font-size:28px;font-weight:700} .subtitle{font-size:16px;fill:#536372} .name{font-size:18px;font-weight:700} .value{font-size:16px} .delta{font-size:15px;fill:#536372}</style>',
    '<text x="55" y="52" class="title">Cost of Linkerd sidecar</text>',
    '<text x="55" y="82" class="subtitle">API v1 · 1000 sequential POST /order · same NodePort</text>',
    '<rect x="750" y="39" width="16" height="16" rx="3" fill="#377eb8"/><text x="776" y="53" class="value">No mesh</text>',
    '<rect x="900" y="39" width="16" height="16" rx="3" fill="#e6863b"/><text x="926" y="53" class="value">With mesh</text>',
]

for index, (name, unit, before, after, digits) in enumerate(rows):
    y = 122 + index * 145
    scale = 690 / (max(before, after) * 1.12)
    delta = (after / before - 1) * 100
    fmt = f"{{:.{digits}f}}"
    parts += [
        f'<text x="55" y="{y}" class="name">{name}</text>',
        f'<text x="550" y="{y}" class="delta">Change {delta:+.1f}%</text>',
        f'<rect x="55" y="{y+18}" width="{before*scale:.1f}" height="35" rx="5" fill="#377eb8"/>',
        f'<rect x="55" y="{y+59}" width="{after*scale:.1f}" height="35" rx="5" fill="#e6863b"/>',
        f'<text x="{70+before*scale:.1f}" y="{y+43}" class="value">{fmt.format(before)} {unit}</text>',
        f'<text x="{70+after*scale:.1f}" y="{y+84}" class="value">{fmt.format(after)} {unit}</text>',
    ]

parts += [
    '<text x="55" y="700" class="subtitle">One run per state; CPU is a one-minute Prometheus rate at benchmark end.</text>',
    '</svg>',
]
(root / "mesh-cost.svg").write_text("\n".join(parts) + "\n")
