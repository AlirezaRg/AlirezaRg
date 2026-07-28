#!/usr/bin/env python3
"""
Generate the animated projects panel (projects.svg + projects-light.svg).

Reads merged.json (projects.json + live GitHub data, produced by fetch_data.py)
and lays the projects out as a 2-column grid of mini terminal cards. Add, remove
or reorder projects by editing projects.json — the README never changes.

Theme matches the banner: near-black navy ground, electric blue, cyan edge light,
warm highlight; mono type, dotted leaders, pulsing activity dots, animated donuts.
"""
import json, base64, os, sys, math, html
from datetime import datetime, timezone

# ---------------- themes ----------------
THEMES = {
    "dark": {
        "BG": "#000911", "PANEL": "#04121F", "PANEL_BAR": "#02101C",
        "PRIMARY": "#3B9EFF", "PRIMARY_DEEP": "#0550D6",
        "ACCENT": "#6FD3F2", "WARM": "#B9765E",
        "TEXT": "#E8F4FF", "MUTED": "#8FA9C0", "DIM": "#4A6076",
        "STROKE": "rgba(59,158,255,0.28)", "STROKE_HI": "rgba(59,158,255,0.55)",
        "STROKE_LO": "rgba(59,158,255,0.20)", "BARLINE": "rgba(255,255,255,0.08)",
        "RING_BG": "rgba(143,169,192,0.15)",
        "PILL_BG": "rgba(5,80,214,0.28)", "PILL_STROKE": "rgba(59,158,255,0.5)",
        "MONO_TX": "#E8F4FF",
    },
    "light": {
        "BG": "#F7FAFD", "PANEL": "#FFFFFF", "PANEL_BAR": "#EDF3F9",
        "PRIMARY": "#0B62C4", "PRIMARY_DEEP": "#063E86",
        "ACCENT": "#1E88B0", "WARM": "#A0563C",
        "TEXT": "#041019", "MUTED": "#4A6076", "DIM": "#8FA9C0",
        "STROKE": "rgba(11,98,196,0.30)", "STROKE_HI": "rgba(11,98,196,0.55)",
        "STROKE_LO": "rgba(11,98,196,0.20)", "BARLINE": "rgba(0,0,0,0.08)",
        "RING_BG": "rgba(74,96,118,0.20)",
        "PILL_BG": "rgba(11,98,196,0.12)", "PILL_STROKE": "rgba(11,98,196,0.4)",
        "MONO_TX": "#FFFFFF",
    },
}

# active palette — set by set_theme()
BG = PANEL = PANEL_BAR = PRIMARY = PRIMARY_DEEP = ACCENT = WARM = None
TEXT = MUTED = DIM = STROKE = STROKE_HI = STROKE_LO = BARLINE = None
RING_BG = PILL_BG = PILL_STROKE = MONO_TX = None
DONUT_COLORS = []


def set_theme(name):
    t = THEMES[name]
    g = globals()
    g.update(t)
    g["DONUT_COLORS"] = [t["PRIMARY"], t["ACCENT"], t["WARM"],
                         t["PRIMARY_DEEP"], "#7C8FA6", t["DIM"]]


set_theme("dark")

# ---------------- layout ----------------
W      = 1180
CARD_W = 578
CARD_H = 168
GAP    = 14
MARGIN = 5
FONT   = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


def esc(s):
    return html.escape(str(s), quote=True)


def rel_time(iso):
    if not iso:
        return "n/a"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        d = datetime.now(timezone.utc) - dt
        if d.days > 365: return f"{d.days // 365}y ago"
        if d.days > 30:  return f"{d.days // 30}mo ago"
        if d.days > 0:   return f"{d.days}d ago"
        h = d.seconds // 3600
        return f"{h}h ago" if h else "just now"
    except Exception:
        return "n/a"


def load_logo_b64(path):
    if not path:
        return None
    for base in ("logos", "."):
        p = os.path.join(base, path)
        if os.path.exists(p):
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            mime = {"png": "image/png", "svg": "image/svg+xml", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            with open(p, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    return None


def wrap_text(s, max_chars, max_lines=2):
    words = s.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and words and " ".join(lines).count(" ") + 1 < len(words):
        lines[-1] = lines[-1][:max_chars - 1].rstrip() + "…"
    return lines


def donut_segments(languages, cx, cy, r, begin):
    """Animated language donut: each segment draws itself in sequence."""
    total = sum(languages.values()) or 1
    entries = sorted(languages.items(), key=lambda kv: -kv[1])[:4]
    other = total - sum(v for _, v in entries)
    if other > 0:
        entries.append(("Other", other))
    C = 2 * math.pi * r
    out, legend = [], []
    offset, t = 0.0, begin
    for i, (lang, v) in enumerate(entries):
        frac = v / total
        seg = frac * C
        col = DONUT_COLORS[i % len(DONUT_COLORS)]
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="9" '
            f'stroke-dasharray="{seg:.2f} {C - seg:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.01s" begin="{t:.2f}s" fill="freeze"/>'
            f'<animate attributeName="stroke-dasharray" from="0 {C:.2f}" to="{seg:.2f} {C - seg:.2f}" '
            f'dur="0.6s" begin="{t:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" '
            f'keySplines="0.3 0 0.2 1"/></circle>')
        legend.append((lang, frac, col))
        offset += seg
        t += 0.18
    return "".join(out), legend


def card(p, x, y, idx):
    b = 0.25 + idx * 0.15                      # staggered entrance
    e = []
    a = e.append

    repo = (p.get("repo") or "").strip()
    repo = repo.replace("https://github.com/", "").replace("http://github.com/", "").rstrip("/")
    a(f'<a href="https://github.com/{esc(repo)}" target="_blank">')
    a(f'<g opacity="0" transform="translate({x},{y})">')
    a(f'<animate attributeName="opacity" from="0" to="1" dur="0.5s" begin="{b:.2f}s" fill="freeze"/>')

    # card shell — mini terminal window
    a(f'<rect width="{CARD_W}" height="{CARD_H}" rx="12" fill="{PANEL}" stroke="{STROKE}">'
      f'<animate attributeName="stroke" values="{STROKE_LO};{STROKE_HI};{STROKE_LO}" '
      f'dur="4.5s" begin="{b + idx * 0.7:.2f}s" repeatCount="indefinite"/></rect>')
    a(f'<rect width="{CARD_W}" height="30" rx="12" fill="{PANEL_BAR}"/>')
    a(f'<rect y="18" width="{CARD_W}" height="12" fill="{PANEL_BAR}"/>')
    a(f'<line x1="0" y1="30" x2="{CARD_W}" y2="30" stroke="{BARLINE}"/>')
    a(f'<text x="16" y="19" font-size="10" fill="{MUTED}">'
      f'<tspan fill="{PRIMARY}">&#8226;</tspan> {esc(repo)}</text>')

    # activity dot: pulses if pushed within 14 days
    days = 999
    try:
        dt = datetime.fromisoformat((p.get("pushed_at") or "").replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
    except Exception:
        pass
    if days <= 14:
        a(f'<circle cx="{CARD_W - 16}" cy="15" r="3.5" fill="{ACCENT}">'
          f'<animate attributeName="opacity" values="1;0.25;1" dur="1.8s" repeatCount="indefinite"/></circle>')
    else:
        a(f'<circle cx="{CARD_W - 16}" cy="15" r="3.5" fill="{DIM}"/>')

    # logo or monogram, gently floating
    float_anim = (f'<animateTransform attributeName="transform" type="translate" '
                  f'values="0 0; 0 -2.5; 0 0" dur="5s" begin="{b + idx * 0.5:.2f}s" '
                  f'repeatCount="indefinite" calcMode="spline" keyTimes="0;0.5;1" '
                  f'keySplines="0.4 0 0.6 1;0.4 0 0.6 1"/>')
    logo = p.get("_logo_b64")
    if logo:
        a(f'<g>{float_anim}<image x="16" y="44" width="40" height="40" href="{logo}" '
          f'preserveAspectRatio="xMidYMid meet"/></g>')
    else:
        initial = esc((p.get("name") or "?")[0].upper())
        a(f'<g>{float_anim}<rect x="16" y="44" width="40" height="40" rx="9" fill="{PRIMARY_DEEP}" opacity="0.9"/>'
          f'<text x="36" y="71" text-anchor="middle" font-size="20" font-weight="700" fill="{MONO_TX}">{initial}</text></g>')

    # name + blinking cursor
    a(f'<text x="68" y="61" font-size="17" font-weight="700" fill="{TEXT}">{esc(p.get("name", "unnamed"))}'
      f'<tspan fill="{PRIMARY}">_<animate attributeName="opacity" values="1;0;1" dur="1.2s" '
      f'begin="{b + 0.4:.2f}s" repeatCount="indefinite"/></tspan></text>')

    # description, wrapped
    for i, line in enumerate(wrap_text(p.get("description", ""), 52)):
        a(f'<text x="68" y="{80 + i * 16}" font-size="11" fill="{MUTED}">{esc(line)}</text>')

    # tag pills
    tx = 68
    for tag in (p.get("tags") or [])[:3]:
        tw = len(tag) * 6.6 + 14
        a(f'<rect x="{tx}" y="118" width="{tw:.0f}" height="17" rx="8.5" fill="{PILL_BG}" stroke="{PILL_STROKE}"/>')
        a(f'<text x="{tx + tw / 2:.0f}" y="130" text-anchor="middle" font-size="9.5" fill="{PRIMARY}">{esc(tag)}</text>')
        tx += tw + 7

    # bottom row: stars + last update
    a(f'<text x="68" y="155" font-size="11" fill="{MUTED}">'
      f'<tspan fill="{PRIMARY}">&#9733;</tspan> {p.get("stars", 0)}'
      f'<tspan fill="{DIM}" dx="14">updated {rel_time(p.get("pushed_at"))}</tspan></text>')

    # language donut
    langs = p.get("languages") or {}
    if langs:
        cx, cy, r = CARD_W - 58, CARD_H // 2 + 6, 27
        segs, legend = donut_segments(langs, cx, cy, r, b + 0.3)
        a(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{RING_BG}" stroke-width="9"/>')
        a(segs)
        a(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="11" font-weight="700" '
          f'fill="{TEXT}">{legend[0][1] * 100:.0f}%</text>')
        dot_x, ly = cx - r - 92, cy - 22
        for lang, frac, col in legend[:3]:
            a(f'<circle cx="{dot_x}" cy="{ly}" r="3.5" fill="{col}"/>')
            a(f'<text x="{dot_x + 9}" y="{ly + 4}" font-size="10" fill="{MUTED}">{esc(lang)} {frac * 100:.0f}%</text>')
            ly += 18

    a('</g></a>')
    return "".join(e)


def build(projects, theme):
    rows = math.ceil(len(projects) / 2)
    H = 56 + rows * (CARD_H + GAP) + MARGIN
    gid = f"acc_{theme}"
    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="{FONT}" role="img" aria-label="Projects">')
    a(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    a(f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
      f'<stop offset="0" stop-color="{PRIMARY_DEEP}"><animate attributeName="stop-color" '
      f'values="{PRIMARY_DEEP};{PRIMARY};{ACCENT};{PRIMARY_DEEP}" dur="10s" repeatCount="indefinite"/></stop>'
      f'<stop offset="1" stop-color="{ACCENT}"><animate attributeName="stop-color" '
      f'values="{ACCENT};{PRIMARY_DEEP};{PRIMARY};{ACCENT}" dur="10s" repeatCount="indefinite"/></stop>'
      f'</linearGradient></defs>')
    a(f'<text x="{MARGIN + 2}" y="18" font-size="11" letter-spacing="2" fill="{PRIMARY}">PROJECTS.LIST</text>')
    a(f'<text x="{MARGIN + 130}" y="18" font-size="10" fill="{DIM}">./projects.sh --all</text>')
    a(f'<line x1="{MARGIN}" y1="28" x2="{W - MARGIN}" y2="28" stroke="url(#{gid})" stroke-width="1.5" opacity="0.7"/>')
    for i, p in enumerate(projects):
        a(card(p, MARGIN + (i % 2) * (CARD_W + GAP + 4), 42 + (i // 2) * (CARD_H + GAP), i))
    a('</svg>')
    return "".join(s)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "merged.json"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    with open(src, encoding="utf-8") as f:
        projects = json.load(f)
    for p in projects:
        p["_logo_b64"] = load_logo_b64(p.get("logo"))
    for theme, fname in (("dark", "projects.svg"), ("light", "projects-light.svg")):
        set_theme(theme)
        svg = build(projects, theme)
        path = os.path.join(outdir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path}: {theme}, {len(projects)} projects, {len(svg) // 1024}KB")
