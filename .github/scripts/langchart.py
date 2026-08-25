#!/usr/bin/env python3
"""Genera un donut chart SVG con la distribuzione dei linguaggi su GitHub.

I servizi pubblici che offrono questa card girano su istanze Vercel gratuite
che si esauriscono (402/503) e in qualche caso restituiscono dati sbagliati.
Qui i byte per linguaggio arrivano direttamente dalle API GitHub e l'SVG
viene committato nel repo, cosi' la card non dipende da nessun servizio
esterno a runtime.
"""

import json
import math
import os
import urllib.request
from collections import Counter

USER = os.environ.get("GH_USER", "Elmond0")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("OUT", "profile/languages.svg")

# Colori ufficiali GitHub (linguist). Per tutto il resto si pesca da FALLBACK.
COLORS = {
    "C": "#555555",
    "C++": "#f34b7d",
    "Makefile": "#427819",
    "Shell": "#89e051",
    "Python": "#3572A5",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Dockerfile": "#384d54",
    "Assembly": "#6E4C13",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Roff": "#ecdebe",
}
FALLBACK = ["#58a6ff", "#3fb950", "#d29922", "#f85149", "#a371f7", "#db61a2"]

MAX_SLICES = 6


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "langchart"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    totals = Counter()
    page = 1
    while True:
        repos = get(
            f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}"
        )
        if not repos:
            break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            try:
                for lang, size in get(repo["languages_url"]).items():
                    totals[lang] += size
            except Exception:
                # Un repo che non risponde non deve far fallire tutta la card.
                continue
        if len(repos) < 100:
            break
        page += 1
    return totals


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build(totals):
    total = sum(totals.values())
    if not total:
        raise SystemExit("nessun linguaggio rilevato")

    ranked = totals.most_common()
    slices = ranked[:MAX_SLICES]
    rest = sum(v for _, v in ranked[MAX_SLICES:])
    if rest:
        slices.append(("Other", rest))

    cx, cy, r, stroke = 100, 100, 62, 30
    circumference = 2 * math.pi * r

    arcs, legend = [], []
    offset = 0.0
    spare = list(FALLBACK)

    for i, (lang, size) in enumerate(slices):
        share = size / total
        color = COLORS.get(lang) or spare[i % len(spare)]
        dash = share * circumference
        # Un filo di gap fra gli spicchi, ma mai piu' della fetta stessa.
        gap = min(2.0, dash / 3)
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" '
            f'stroke-dasharray="{dash - gap:.2f} {circumference - dash + gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        y = 48 + i * 26
        legend.append(
            f'<circle cx="212" cy="{y - 4}" r="6" fill="{color}"/>'
            f'<text class="lang" x="228" y="{y}">{esc(lang)}</text>'
            f'<text class="pct" x="384" y="{y}" text-anchor="end">{share * 100:.1f}%</text>'
        )
        offset += dash

    height = max(200, 48 + len(slices) * 26 + 20)
    newline = "\n  "

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="{height}" viewBox="0 0 400 {height}" role="img" aria-label="Language distribution">
  <style>
    .lang {{ font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #24292f; }}
    .pct  {{ font: 400 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #57606a; }}
    @media (prefers-color-scheme: dark) {{
      .lang {{ fill: #c9d1d9; }}
      .pct  {{ fill: #8b949e; }}
    }}
  </style>
  {newline.join(arcs)}
  {newline.join(legend)}
</svg>
"""


def main():
    svg = build(collect())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"scritto {OUT}")


if __name__ == "__main__":
    main()
