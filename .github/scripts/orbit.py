#!/usr/bin/env python3
"""Genera un SVG con i linguaggi che orbitano attorno a un nucleo.

Nasce come alternativa a stats.pphat.top/languages?type=card: quel servizio
ha un solo template non configurabile, mostra i nomi dei linguaggi invece
delle icone e tiene solo i primi due rinormalizzando le percentuali (per
questo profilo darebbe C 55 / C++ 45, perdendo Makefile).

Qui i byte per linguaggio arrivano dalle API GitHub e l'animazione usa
<animateMotion>, che i browser eseguono anche quando l'SVG e' dentro un
<img> (e' lo stesso meccanismo dello snake dei contributi).

Le icone devicon vengono inserite inline come <path>, non come <image>
con data URI: dentro un <img> il browser applica la "secure animated mode"
e un documento SVG annidato non e' garantito che venga disegnato, mentre
dei path nello stesso documento lo sono sempre.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

USER = os.environ.get("GH_USER", "Elmond0")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("ORBIT_OUT", "profile/orbit.svg")

DEVICON = "https://raw.githubusercontent.com/devicons/devicon/master/icons"
# Make non esiste in devicon. La voce "Make" di simple-icons NON va usata:
# la sua fonte e' make.com/press, cioe' la piattaforma di automazione, non
# GNU Make (stesso equivoco del logo CMake). Si usa l'icona makefile di
# material-icon-theme (MIT), che raffigura un terminale con ingranaggio.
MATERIAL = "https://raw.githubusercontent.com/material-extensions/vscode-material-icon-theme/main/icons"

# Linguaggio GitHub -> URL dell'icona. I linguaggi assenti da questa mappa
# ricadono sul cerchio colorato con l'iniziale.
ICONS = {
    "C": f"{DEVICON}/c/c-original.svg",
    "C++": f"{DEVICON}/cplusplus/cplusplus-original.svg",
    "Makefile": f"{MATERIAL}/makefile.svg",
    "Shell": f"{DEVICON}/bash/bash-original.svg",
    "Python": f"{DEVICON}/python/python-original.svg",
    "HTML": f"{DEVICON}/html5/html5-original.svg",
    "CSS": f"{DEVICON}/css3/css3-original.svg",
    "JavaScript": f"{DEVICON}/javascript/javascript-original.svg",
    "TypeScript": f"{DEVICON}/typescript/typescript-original.svg",
    "Dockerfile": f"{DEVICON}/docker/docker-original.svg",
    "Rust": f"{DEVICON}/rust/rust-original.svg",
    "Go": f"{DEVICON}/go/go-original.svg",
    "Java": f"{DEVICON}/java/java-original.svg",
}

# Colori ufficiali linguist, usati per il fallback e per le scie orbitali.
COLORS = {
    "C": "#555555",
    "C++": "#f34b7d",
    "Makefile": "#427819",
    "Shell": "#89e051",
    "Python": "#3572A5",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "JavaScript": "#f1e05a",
    "Roff": "#ecdebe",
}
FALLBACK_COLOR = "#58a6ff"

MAX_PLANETS = 4
W, H = 400, 300
CX, CY = 200, 150


def get(url, raw=False, attempts=6):
    """GET con backoff. Sul 403 da rate limit aspetta fino all'orario di
    reset dichiarato dall'header, invece di rinunciare: un errore transitorio
    non deve far saltare l'intero grafico."""
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": "orbit"})
        if TOKEN and "api.github.com" in url:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read() if raw else json.load(r)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 429):
                reset = exc.headers.get("x-ratelimit-reset")
                wait = 2 ** i
                if reset:
                    wait = max(0, int(reset) - int(time.time())) + 2
                wait = min(wait, 300)
                print(f"  {exc.code} su {url} -> attendo {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if 500 <= exc.code < 600:
                time.sleep(2 ** i)
                continue
            raise
        except Exception as exc:
            last = exc
            time.sleep(2 ** i)
    raise last


def collect():
    """Somma i byte per linguaggio su tutti i repo pubblici non fork.

    Un repo che non risponde NON viene saltato in silenzio: senza token
    l'API va in rate limit dopo poche chiamate e il risultato sarebbe una
    classifica plausibile ma falsa (era il difetto del servizio esterno che
    dava C++ 96% ignorando tutto il C). Meglio fallire e non aggiornare il
    file che pubblicare percentuali sbagliate.
    """
    totals = Counter()
    failed = []
    page = 1
    while True:
        repos = get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}")
        if not repos:
            break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            try:
                for lang, size in get(repo["languages_url"]).items():
                    totals[lang] += size
            except Exception as exc:
                failed.append(f"{repo['name']}: {exc}")
        if len(repos) < 100:
            break
        page += 1
    if failed:
        raise SystemExit("repo non leggibili, dati incompleti:\n  "
                         + "\n  ".join(failed))
    return totals


def icon_inline(lang, r):
    """Restituisce l'icona devicon come gruppo di path, centrata su (0,0)
    e riscalata a 2r pixel. None se il linguaggio non ha un'icona."""
    url = ICONS.get(lang)
    if not url:
        return None
    try:
        svg = get(url, raw=True).decode("utf-8")
    except Exception:
        return None

    box = re.search(r'viewBox="([-\d.\s]+)"', svg)
    if not box:
        return None
    x0, y0, w, h = (float(v) for v in box.group(1).split())

    inner = re.sub(r"^.*?<svg[^>]*>", "", svg, flags=re.S)
    inner = re.sub(r"</svg>\s*$", "", inner, flags=re.S).strip()

    # Gli id (gradienti, clip) vanno resi unici: piu' icone finiscono nello
    # stesso documento e due "id=a" si sovrascriverebbero a vicenda.
    slug = re.sub(r"\W", "", lang).lower()
    inner = re.sub(r'id="([^"]+)"', lambda m: f'id="{slug}-{m.group(1)}"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{slug}-{m.group(1)})", inner)

    scale = (2 * r) / max(w, h)
    return (f'<g transform="translate({-r},{-r}) scale({scale:.5f}) '
            f'translate({-x0},{-y0})">{inner}</g>')


def ellipse_path(rx, ry):
    """Path chiuso per animateMotion, partendo dal punto piu' a destra."""
    return (f"M {CX + rx},{CY} "
            f"A {rx},{ry} 0 1,1 {CX - rx},{CY} "
            f"A {rx},{ry} 0 1,1 {CX + rx},{CY} Z")


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(totals):
    total = sum(totals.values())
    if not total:
        raise SystemExit("nessun linguaggio rilevato")

    planets = totals.most_common(MAX_PLANETS)
    orbits, bodies = [], []

    for i, (lang, size) in enumerate(planets):
        share = size / total
        color = COLORS.get(lang, FALLBACK_COLOR)
        rx = 62 + i * 33
        ry = round(rx * 0.60, 1)
        # Il piu' usato sta piu' vicino al nucleo e gira piu' in fretta.
        dur = 16 + i * 7
        r_icon = 13 if share < 0.5 else 16

        orbits.append(
            f'<ellipse class="orbit" cx="{CX}" cy="{CY}" rx="{rx}" ry="{ry}"/>'
        )

        mark = icon_inline(lang, r_icon)
        if mark is None:
            # Nessuna icona devicon (es. Makefile): pallino colorato + iniziale.
            mark = (f'<circle r="{r_icon}" fill="{color}"/>'
                    f'<text class="ini" y="4" text-anchor="middle">'
                    f'{esc(lang[0])}</text>')

        bodies.append(
            f'<g>'
            f'<animateMotion dur="{dur}s" repeatCount="indefinite" '
            f'begin="-{i * dur / len(planets):.1f}s" '
            f'path="{ellipse_path(rx, ry)}"/>'
            f'{mark}'
            f'<text class="pct" y="{r_icon + 13}" text-anchor="middle">'
            f'{share * 100:.1f}%</text>'
            f'</g>'
        )

    nl = "\n  "
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Linguaggi in orbita: {esc(', '.join(f'{l} {s / total * 100:.1f}%' for l, s in planets))}">
  <defs>
    <radialGradient id="core">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.95"/>
      <stop offset="60%" stop-color="#1f6feb" stop-opacity="0.75"/>
      <stop offset="100%" stop-color="#1f6feb" stop-opacity="0.15"/>
    </radialGradient>
  </defs>
  <style>
    .orbit {{ fill: none; stroke: #d0d7de; stroke-width: 1; stroke-dasharray: 3 4; }}
    .pct {{ font: 600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #57606a; }}
    .ini {{ font: 700 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #ffffff; }}
    @media (prefers-color-scheme: dark) {{
      .orbit {{ stroke: #30363d; }}
      .pct {{ fill: #8b949e; }}
    }}
  </style>
  {nl.join(orbits)}
  <circle cx="{CX}" cy="{CY}" r="34" fill="url(#core)"/>
  <circle cx="{CX}" cy="{CY}" r="34" fill="none" stroke="#58a6ff" stroke-opacity="0.5"/>
  {nl.join(bodies)}
</svg>
"""


def main():
    svg = build(collect())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"scritto {OUT} ({len(svg)} byte)")


if __name__ == "__main__":
    main()
