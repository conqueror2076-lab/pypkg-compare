#!/usr/bin/env python3
"""
Otonom programatik SEO sitesi: PyPI paket istatistikleri ve karsilastirmalari.

Her calistiginda:
  1. En cok indirilen PyPI paketlerinin listesini ceker (tek istek).
  2. Her paket icin PyPI JSON API'sinden meta veriyi ceker.
  3. Gunluk snapshot'i data/snapshots/ altina yazar (git = veritabani).
  4. site/ altina statik HTML uretir: paket sayfalari, "A vs B" sayfalari,
     konu sayfalari, ana sayfa, sitemap.xml, robots.txt.

Sadece standart kutuphane kullanir. Calistirma:  python build.py
Ortam degiskenleri: SITE_URL (kanonik adres), TOP_N (paket sayisi, varsayilan 300)
"""
import datetime as dt
import html
import itertools
import json
import os
import re
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SNAP = DATA / "snapshots"
SITE = ROOT / "site"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

BASE = os.environ.get("SITE_URL", "").rstrip("/")
TOP_N = int(os.environ.get("TOP_N", CFG.get("top_n", 300)))
PAIRS_PER_TOPIC = int(CFG.get("pairs_per_topic", 8))  # konudaki ilk N paket eslestirilir
TODAY = dt.date.today().isoformat()
TOP_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
# Karsilastirma icin anlam tasimayan, cok genis siniflandirmalar
GENERIC = {"Software Development", "Software Development :: Libraries", "Utilities", "Internet", "System",
           "Software Development :: Libraries :: Python Modules",
           "Software Development :: Libraries :: Application Frameworks"}
UA = {"User-Agent": f"{CFG['site_name']} static builder"}
esc = html.escape


# ---------------------------------------------------------------- veri
def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def top_packages():
    """[(ad, aylik_indirme)] dondurur. Liste cekilemezse seeds.txt'e duser."""
    try:
        rows = get_json(TOP_URL)["rows"][:TOP_N]
        return [(r["project"], int(r["download_count"])) for r in rows]
    except Exception as e:  # ag hatasi: sistemi durdurma, tohum listeyle devam et
        print(f"UYARI: top liste alinamadi ({e}); seeds.txt kullaniliyor", file=sys.stderr)
        names = [s.strip() for s in (ROOT / "seeds.txt").read_text().split() if s.strip()]
        return [(n, 0) for n in names[:TOP_N]]


def fetch_meta(name):
    try:
        j = get_json(f"https://pypi.org/pypi/{name}/json")
    except Exception as e:
        print(f"atlandi: {name} ({e})", file=sys.stderr)
        return None
    info = j["info"]
    files = j.get("urls") or []
    uploaded = max((f["upload_time_iso_8601"][:10] for f in files), default="")
    releases = j.get("releases") or {}
    first = min(
        (f["upload_time_iso_8601"][:10] for fs in releases.values() for f in fs),
        default="",
    )
    topics = sorted(
        {c.split(" :: ")[1] for c in info.get("classifiers") or [] if c.startswith("Topic :: ")}
    )
    lic = (info.get("license_expression") or "").strip()
    if not lic:
        lic = next(
            (c.split(" :: ")[-1] for c in info.get("classifiers") or [] if c.startswith("License ::")),
            (info.get("license") or "").strip().split("\n")[0][:40],
        )
    urls = info.get("project_urls") or {}
    repo = next((u for u in urls.values() if re.search(r"github\.com|gitlab\.com", u or "")), "")
    return {
        "name": info["name"],
        "slug": re.sub(r"[-_.]+", "-", info["name"]).lower(),
        "summary": (info.get("summary") or "").strip(),
        "version": info.get("version") or "",
        "released": uploaded,
        "first_release": first,
        "n_releases": len(releases),
        "license": lic or "Not specified",
        "python": info.get("requires_python") or "Not specified",
        "deps": len(info.get("requires_dist") or []),
        "topics": topics,
        "tags": sorted({c[9:] for c in info.get("classifiers") or [] if c.startswith("Topic :: ")} - GENERIC),
        "keywords": sorted({k.strip().lower() for k in re.split(r"[,\s]+", info.get("keywords") or "") if len(k.strip()) > 2}
                           - {"python", "python3"}),
        "repo": repo,
        "home": info.get("home_page") or urls.get("Homepage") or "",
    }


def load_history():
    """{tarih: {slug: indirme}} - eski snapshot'lar."""
    out = {}
    for p in sorted(SNAP.glob("*.json")):
        out[p.stem] = json.loads(p.read_text())
    return out


def past_value(history, slug, days):
    """~days gun onceki degeri dondurur (yoksa None)."""
    target = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    older = [d for d in history if d <= target]
    if not older:
        return None
    return history[max(older)].get(slug)


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--mut:#6b675f;--line:#e4e0d6;--acc:#1f5f4a;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#141412;--fg:#ecebe6;--mut:#9a968c;--line:#2c2b27;--acc:#7fd1b0;--card:#1b1b18}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,sans-serif}
main,header,footer{max-width:860px;margin:auto;padding:16px 20px}
header a{font-weight:700;color:var(--fg);text-decoration:none}a{color:var(--acc)}
h1{font-size:1.9rem;line-height:1.2;margin:.4em 0}h2{font-size:1.2rem;margin-top:2em}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:600;color:var(--mut);width:30%}td.n{font-variant-numeric:tabular-nums}
code{background:var(--card);border:1px solid var(--line);padding:2px 6px;border-radius:4px}
.mut{color:var(--mut);font-size:.9rem}.up{color:#1a7f4b}.down{color:#b3402e}
ul.cols{columns:2;padding-left:1.1em}.box{border:1px solid var(--line);background:var(--card);padding:12px 16px;margin:1.5em 0}
footer{color:var(--mut);font-size:.85rem;border-top:1px solid var(--line);margin-top:3em}
"""


def page(path, title, desc, body):
    url = f"{BASE}/{path}"
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}"><style>{CSS}</style>{CFG.get('head_html', '')}</head><body>
<header><a href="{BASE}/">{esc(CFG['site_name'])}</a></header><main>{body}{affiliate_box()}</main>
<footer>Data from the public PyPI API and the top-pypi-packages dataset. Updated {TODAY}.
{esc(CFG.get('disclosure', ''))}</footer></body></html>"""
    out = SITE / path / "index.html" if not path.endswith(".html") else SITE / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return url


def affiliate_box():
    links = CFG.get("affiliate_links") or []
    if not links:
        return ""
    items = "".join(
        f'<li><a rel="sponsored nofollow" href="{esc(l["url"])}">{esc(l["text"])}</a></li>' for l in links
    )
    return f'<div class="box"><b>{esc(CFG.get("affiliate_title", "Recommended"))}</b><ul>{items}</ul></div>'


def fmt(n):
    return f"{n:,}" if n else "n/a"


def trend(now, before):
    if not now or not before:
        return '<span class="mut">collecting history</span>'
    pct = (now - before) / before * 100
    cls = "up" if pct >= 0 else "down"
    return f'<span class="{cls}">{pct:+.1f}%</span>'


def link(p):
    return f'<a href="{BASE}/p/{p["slug"]}/">{esc(p["name"])}</a>'


def vs_slug(a, b):
    return f'{a["slug"]}-vs-{b["slug"]}'


def render_package(p, rivals, hist):
    rows = [
        ("Monthly downloads", f'{fmt(p["downloads"])} (rank #{p["rank"]} of tracked packages)'),
        ("30-day change", trend(p["downloads"], past_value(hist, p["slug"], 30))),
        ("Latest version", f'{esc(p["version"])} <span class="mut">released {p["released"] or "n/a"}</span>'),
        ("First release", p["first_release"] or "n/a"),
        ("Total releases", str(p["n_releases"])),
        ("License", esc(p["license"])),
        ("Python requirement", esc(p["python"])),
        ("Declared dependencies", str(p["deps"])),
    ]
    table = "".join(f"<tr><th>{k}</th><td class=n>{v}</td></tr>" for k, v in rows)
    ext = "".join(
        f'<li><a rel="nofollow" href="{esc(u)}">{t}</a></li>'
        for t, u in (("Source repository", p["repo"]), ("Homepage", p["home"]),
                     ("PyPI page", f'https://pypi.org/project/{p["name"]}/')) if u
    )
    comp = "".join(
        f'<li><a href="{BASE}/compare/{vs_slug(*sorted((p, r), key=lambda x: x["rank"]))}/">'
        f'{esc(p["name"])} vs {esc(r["name"])}</a></li>' for r in rivals
    )
    topics = ", ".join(f'<a href="{BASE}/topic/{slugify(t)}/">{esc(t)}</a>' for t in p["topics"]) or "n/a"
    body = f"""<h1>{esc(p['name'])}: downloads, version and license</h1>
<p>{esc(p['summary'])}</p><p><code>pip install {esc(p['name'])}</code></p>
<table>{table}</table><p class="mut">Topics: {topics}</p>
{f'<h2>Compare {esc(p["name"])} with alternatives</h2><ul class="cols">{comp}</ul>' if comp else ''}
<h2>Links</h2><ul>{ext}</ul>"""
    return page(f'p/{p["slug"]}/', f'{p["name"]} PyPI stats: downloads, latest version, license',
                f'{p["name"]} has {fmt(p["downloads"])} monthly downloads. Latest version {p["version"]}, '
                f'license {p["license"]}. {p["summary"]}'[:158], body)


def render_vs(a, b, hist):
    def row(label, f):
        return f"<tr><th>{label}</th><td class=n>{f(a)}</td><td class=n>{f(b)}</td></tr>"

    table = "".join([
        row("Monthly downloads", lambda p: fmt(p["downloads"])),
        row("30-day change", lambda p: trend(p["downloads"], past_value(hist, p["slug"], 30))),
        row("Latest version", lambda p: esc(p["version"])),
        row("Last release", lambda p: p["released"] or "n/a"),
        row("First release", lambda p: p["first_release"] or "n/a"),
        row("Total releases", lambda p: str(p["n_releases"])),
        row("License", lambda p: esc(p["license"])),
        row("Python requirement", lambda p: esc(p["python"])),
        row("Declared dependencies", lambda p: str(p["deps"])),
    ])
    facts = []
    if a["downloads"] and b["downloads"]:
        hi, lo = (a, b) if a["downloads"] >= b["downloads"] else (b, a)
        facts.append(f'{esc(hi["name"])} is downloaded {hi["downloads"] / lo["downloads"]:.1f}x as often as '
                     f'{esc(lo["name"])} over the last 30 days.')
    if a["released"] and b["released"] and a["released"] != b["released"]:
        new = a if a["released"] > b["released"] else b
        facts.append(f'{esc(new["name"])} shipped a release more recently ({new["released"]}).')
    if a["first_release"] and b["first_release"]:
        old = a if a["first_release"] < b["first_release"] else b
        facts.append(f'{esc(old["name"])} is the older project (first release {old["first_release"]}).')
    if a["deps"] != b["deps"]:
        light = a if a["deps"] < b["deps"] else b
        facts.append(f'{esc(light["name"])} declares fewer dependencies ({light["deps"]}).')
    if a["license"] != b["license"]:
        facts.append(f'Licenses differ: {esc(a["license"])} vs {esc(b["license"])}.')
    shared = sorted(set(a["topics"]) & set(b["topics"]))
    body = f"""<h1>{esc(a['name'])} vs {esc(b['name'])}</h1>
<p class="mut">Side-by-side PyPI data, refreshed daily. Shared topics: {esc(', '.join(shared)) or 'n/a'}.</p>
<table><tr><th></th><th>{link(a)}</th><th>{link(b)}</th></tr>{table}</table>
<h2>What the numbers say</h2><ul>{''.join(f'<li>{f}</li>' for f in facts)}</ul>
<p><b>{esc(a['name'])}:</b> {esc(a['summary'])}<br><b>{esc(b['name'])}:</b> {esc(b['summary'])}</p>"""
    return page(f"compare/{vs_slug(a, b)}/", f'{a["name"]} vs {b["name"]}: downloads, releases, license compared',
                f'{a["name"]} ({fmt(a["downloads"])}/mo) vs {b["name"]} ({fmt(b["downloads"])}/mo): '
                f'versions, release activity, licenses and dependencies side by side.'[:158], body)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------- ana akis
def main():
    top = top_packages()
    with ThreadPoolExecutor(8) as ex:
        metas = list(ex.map(fetch_meta, [n for n, _ in top]))
    pkgs = []
    for (name, dl), m in zip(top, metas):
        if m:
            m["downloads"] = dl
            pkgs.append(m)
    if len(pkgs) < max(5, len(top) // 2):
        sys.exit("HATA: cok az paket cekildi; eski site korunuyor, cikiliyor.")
    for i, p in enumerate(pkgs, 1):
        p["rank"] = i
    hist = load_history()

    # snapshot (git'e commit edilir -> zamanla benzersiz trend verisi birikir)
    if any(p["downloads"] for p in pkgs):
        SNAP.mkdir(parents=True, exist_ok=True)
        (SNAP / f"{TODAY}.json").write_text(json.dumps({p["slug"]: p["downloads"] for p in pkgs}))
    DATA.mkdir(exist_ok=True)
    (DATA / "latest.json").write_text(json.dumps(pkgs, indent=1))

    # konu gruplari ve eslesmeler
    topics = {}
    for p in pkgs:
        for t in p["topics"]:
            topics.setdefault(t, []).append(p)
    # Yalnizca gercekten benzer paketler eslestirilir (ortak ozel konu ya da 2 ortak anahtar kelime)
    pairs, rivals = {}, {p["slug"]: [] for p in pkgs}
    for a, b in itertools.combinations(pkgs, 2):
        kw = len(set(a["keywords"]) & set(b["keywords"]))
        cat = len(set(a["tags"]) & set(b["tags"]))
        if (kw >= 2 or cat >= 1) and len(rivals[a["slug"]]) < PAIRS_PER_TOPIC \
                and len(rivals[b["slug"]]) < PAIRS_PER_TOPIC:
            pairs[vs_slug(a, b)] = (a, b)
            rivals[a["slug"]].append(b)
            rivals[b["slug"]].append(a)

    if SITE.exists():
        shutil.rmtree(SITE)
    urls = []
    for p in pkgs:
        urls.append(render_package(p, rivals[p["slug"]][:12], hist))
    for a, b in pairs.values():
        urls.append(render_vs(a, b, hist))
    for t, members in sorted(topics.items()):
        if len(members) < 3:
            continue
        rows = "".join(f"<tr><td class=n>#{p['rank']}</td><td>{link(p)}</td><td class=n>{fmt(p['downloads'])}</td>"
                       f"<td>{esc(p['summary'][:90])}</td></tr>" for p in members)
        urls.append(page(f"topic/{slugify(t)}/", f"Most downloaded Python packages for {t}",
                         f"The {len(members)} most downloaded PyPI packages tagged {t}, ranked by monthly downloads.",
                         f"<h1>Most downloaded Python packages: {esc(t)}</h1><table>"
                         f"<tr><th>Rank</th><th>Package</th><th>Monthly</th><th>Summary</th></tr>{rows}</table>"))
    tl = "".join(f'<li><a href="{BASE}/topic/{slugify(t)}/">{esc(t)}</a> <span class="mut">({len(m)})</span></li>'
                 for t, m in sorted(topics.items()) if len(m) >= 3)
    pl = "".join(f"<tr><td class=n>#{p['rank']}</td><td>{link(p)}</td><td class=n>{fmt(p['downloads'])}</td>"
                 f"<td class=n>{trend(p['downloads'], past_value(hist, p['slug'], 30))}</td></tr>" for p in pkgs)
    urls.append(page("", f"{CFG['site_name']}: PyPI package stats and comparisons", CFG["tagline"],
                     f"<h1>{esc(CFG['tagline'])}</h1><h2>Browse by topic</h2><ul class='cols'>{tl}</ul>"
                     f"<h2>Top packages</h2><table><tr><th>Rank</th><th>Package</th><th>Monthly downloads</th>"
                     f"<th>30-day change</th></tr>{pl}</table>"))

    sm = "".join(f"<url><loc>{esc(u)}</loc><lastmod>{TODAY}</lastmod></url>" for u in urls)
    (SITE / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    (SITE / ".nojekyll").write_text("")
    print(f"tamam: {len(pkgs)} paket, {len(pairs)} karsilastirma, {len(urls)} sayfa")


if __name__ == "__main__":
    main()
