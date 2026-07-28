#!/usr/bin/env python3
"""
Generate the theme-aware hero banner: dark.svg + light.svg.

Left panel  : a Floyd-Steinberg dithered portrait, emitted as SVG pixel runs and
              revealed band-by-band on load.
Right panel : a SYSTEM.INFO spec sheet with dotted leaders, typed in row by row.

Usage:
    python .github/scripts/generate_banner.py <photo> [outdir]
    python .github/scripts/generate_banner.py me.jpg .

Content comes from profile.json. Requires Pillow.
"""
import json, sys, os, html, math, io, base64
from PIL import Image, ImageOps

# ---------------- themes ----------------
THEMES = {
    # sampled from the codeiish.ir key art: near-black navy ground, electric
    # blue glow, cyan edge light, warm skin highlight
    "dark": {
        "OUTER":  "#00060D", "BG_TOP": "#000911", "BG_BOT": "#04121F",
        "BAR":    "#02101C", "PANEL":  "#000911",
        "PRIMARY": "#3B9EFF", "PRIMARY_DEEP": "#0550D6",
        "ACCENT":  "#6FD3F2", "WARM": "#B9765E",
        "TEXT":   "#E8F4FF", "MUTED": "#8FA9C0", "DIM": "#4A6076",
        "HAIR":   "rgba(255,255,255,0.10)",
        "LEADER": "rgba(143,169,192,0.30)",
        "PANEL_STROKE": "rgba(59,158,255,0.30)",
        "PILL_BG": "#06243F", "PILL_TX": "#9BD4FF",
        "INK":    "#6FD3F2",
    },
    "light": {
        "OUTER":  "#FFFFFF", "BG_TOP": "#F7FAFD", "BG_BOT": "#EDF3F9",
        "BAR":    "#E8F0F7", "PANEL":  "#FFFFFF",
        "PRIMARY": "#0B62C4", "PRIMARY_DEEP": "#063E86",
        "ACCENT":  "#1E88B0", "WARM": "#A0563C",
        "TEXT":   "#041019", "MUTED": "#4A6076", "DIM": "#8FA9C0",
        "HAIR":   "rgba(0,0,0,0.10)",
        "LEADER": "rgba(74,96,118,0.35)",
        "PANEL_STROKE": "rgba(11,98,196,0.28)",
        "PILL_BG": "#E1F0FF", "PILL_TX": "#06427E",
        "INK":    "#1E88B0",
    },
}

# ---------------- layout ----------------
W, H       = 1180, 610
BAR_H      = 46
PAD        = 36
ART_W      = 400
ART_H      = 492
ART_X, ART_Y = PAD, 84
COL_X      = 470            # right column left edge
COL_W      = 655            # dotted-leader run width
ROW_CHARS  = 79             # every leader row padded to this many chars
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

# dithered portrait: source grid (before scaling into the panel) and tone controls
GRID_W   = 380
BANDS    = 14               # reveal bands
ZOOM     = 1.30             # >1 crops tighter on the subject
GAMMA    = 2.4              # >1 crushes midtones, keeping only real highlights
VIGNETTE = 0.85             # radial falloff strength; drops the busy background
GAIN     = 0.95             # overall ink density


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------- portrait ----------------
def _prepare(photo_path, grid_w, zoom, mode="L"):
    """Crop the photo to the panel aspect ratio, zoom in, resize to the grid."""
    im = Image.open(photo_path)
    im = ImageOps.exif_transpose(im)
    im = im.convert(mode)
    if mode == "L":
        im = ImageOps.autocontrast(im, cutoff=2)

    target_ar = ART_W / ART_H
    w, h = im.size
    cw, ch = (int(h * target_ar), h) if w / h > target_ar else (w, int(w / target_ar))
    cw, ch = int(cw / zoom), int(ch / zoom)
    left = (w - cw) // 2
    top = int((h - ch) * 0.18)
    im = im.crop((left, top, left + cw, top + ch))

    grid_h = int(round(grid_w / target_ar))
    return im.resize((grid_w, grid_h), Image.LANCZOS), grid_h


def _density_mask(gray, grid_w, grid_h, gamma, vignette, gain):
    """1-bit mask: ink on the bright, central part of the frame."""
    src = gray.load()
    dens = Image.new("L", (grid_w, grid_h))
    dp = dens.load()
    cx, cy = grid_w / 2, grid_h * 0.42
    rmax = math.hypot(grid_w / 2, grid_h / 2)
    for y in range(grid_h):
        for x in range(grid_w):
            r = math.hypot(x - cx, y - cy) / rmax
            fall = max(0.0, 1.0 - vignette * r * r)
            v = (src[x, y] / 255.0) ** gamma * fall * gain
            dp[x, y] = 255 - min(255, int(v * 255))
    return dens.convert("1")


def color_dither_runs(photo_path, grid_w=GRID_W, zoom=ZOOM, gamma=GAMMA,
                      vignette=VIGNETTE, gain=GAIN, colors=28):
    """
    Stipple the portrait but keep the photo's own colours.

    Structure comes from the same brightness/vignette mask as the mono version;
    each surviving pixel is then painted with its quantised source colour, and
    runs are grouped per colour so the SVG stays a couple of dozen paths.

    Returns (runs_by_hex, w, h).
    """
    rgb, grid_h = _prepare(photo_path, grid_w, zoom, mode="RGB")
    gray = ImageOps.autocontrast(rgb.convert("L"), cutoff=2)
    mask = _density_mask(gray, grid_w, grid_h, gamma, vignette, gain).load()

    pal = rgb.quantize(colors=colors, method=Image.MEDIANCUT).convert("RGB").load()

    out = {}
    for y in range(grid_h):
        x = 0
        while x < grid_w:
            if mask[x, y] == 0:                      # ink
                col = pal[x, y]
                start = x
                while x < grid_w and mask[x, y] == 0 and pal[x, y] == col:
                    x += 1
                out.setdefault("#%02X%02X%02X" % col, []).append((start, y, x - start))
            else:
                x += 1
    return out, grid_w, grid_h


def photo_b64(photo_path, zoom=ZOOM, quality=82):
    """The photo itself, cropped to the panel and embedded as a JPEG data URI."""
    rgb, _ = _prepare(photo_path, ART_W * 2, zoom, mode="RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def dither_runs(photo_path, grid_w=GRID_W, zoom=ZOOM, gamma=GAMMA,
                vignette=VIGNETTE, gain=GAIN):
    """
    1-bit dither the photo into SVG-ready pixel runs.

    Ink lands on the *bright, central* part of the frame: brightness is weighted
    by a radial falloff so the busy background drops out, then the map is
    inverted so highlights (the subject) become the drawn pixels.

    Returns (runs, w, h) where each run is (x, y, length).
    """
    im = Image.open(photo_path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("L")
    im = ImageOps.autocontrast(im, cutoff=2)

    # crop to the panel aspect ratio, biased to the upper body, then zoom in
    target_ar = ART_W / ART_H
    w, h = im.size
    cw, ch = (int(h * target_ar), h) if w / h > target_ar else (w, int(w / target_ar))
    cw, ch = int(cw / zoom), int(ch / zoom)
    left = (w - cw) // 2
    top = int((h - ch) * 0.18)
    im = im.crop((left, top, left + cw, top + ch))

    grid_h = int(round(grid_w / target_ar))
    im = im.resize((grid_w, grid_h), Image.LANCZOS)

    # density map: brightness^gamma * radial falloff, scaled by gain
    src = im.load()
    dens = Image.new("L", (grid_w, grid_h))
    dp = dens.load()
    cx, cy = grid_w / 2, grid_h * 0.42        # focus a little above centre
    rmax = math.hypot(grid_w / 2, grid_h / 2)
    for y in range(grid_h):
        for x in range(grid_w):
            r = math.hypot(x - cx, y - cy) / rmax
            fall = max(0.0, 1.0 - vignette * r * r)
            v = (src[x, y] / 255.0) ** gamma * fall * gain
            dp[x, y] = 255 - min(255, int(v * 255))   # invert: bright -> ink

    bw = dens.convert("1")                    # Floyd-Steinberg by default
    px = bw.load()

    runs = []
    for y in range(grid_h):
        x = 0
        while x < grid_w:
            if px[x, y] == 0:                 # ink
                start = x
                while x < grid_w and px[x, y] == 0:
                    x += 1
                runs.append((start, y, x - start))
            else:
                x += 1
    return runs, grid_w, grid_h


def portrait_color_svg(runs_by_color, gw, gh):
    """Colour stipple: one path per quantised colour, revealed together."""
    sx, sy = ART_W / gw, ART_H / gh
    out = [f'<g clip-path="url(#artClip)" transform="translate({ART_X},{ART_Y}) '
           f'scale({sx:.4f},{sy:.4f})" shape-rendering="crispEdges">',
           '<g opacity="0"><animate attributeName="opacity" values="0;1" dur="1.1s" '
           'begin="0.25s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines=".4 0 .2 1"/>']
    for col, runs in sorted(runs_by_color.items(), key=lambda kv: -len(kv[1])):
        d = "".join(f"M{x} {y}h{n}v1h-{n}z" for x, y, n in runs)
        out.append(f'<path fill="{col}" d="{d}"/>')
    out.append('</g></g>')
    return "".join(out)


def portrait_photo_svg(href, t):
    """The photo itself, with a faint scanline overlay to keep the CRT feel."""
    return (
        f'<g clip-path="url(#artClip)">'
        f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="1.1s" begin="0.25s" '
        f'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines=".4 0 .2 1"/>'
        f'<image x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" href="{href}" '
        f'preserveAspectRatio="xMidYMid slice"/>'
        f'<rect x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" fill="url(#scan)" opacity="0.22"/>'
        f'</g></g>'
    )


def portrait_svg(runs, gw, gh, t):
    """Band-by-band reveal of the dithered portrait, clipped to the panel."""
    sx = ART_W / gw
    sy = ART_H / gh
    out = [f'<g clip-path="url(#artClip)" transform="translate({ART_X},{ART_Y}) '
           f'scale({sx:.4f},{sy:.4f})" fill="url(#inkGrad)" shape-rendering="crispEdges">']
    band = max(1, gh // BANDS)
    for b in range(0, gh, band):
        chunk = [r for r in runs if b <= r[1] < b + band]
        if not chunk:
            continue
        d = "".join(f"M{x} {y}h{n}v1h-{n}z" for x, y, n in chunk)
        begin = 0.20 + (b / band) * 0.06
        out.append(f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.9s" '
                   f'begin="{begin:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" '
                   f'keySplines=".4 0 .2 1"/><path d="{d}"/></g>')
    out.append('</g>')
    return "".join(out)


# ---------------- right column ----------------
def leader_row(label, value, y, delay, t):
    """One dotted-leader spec line, padded to a fixed character count."""
    dots = max(3, ROW_CHARS - len(label) - len(value) - 2)
    return (
        f'<g opacity="0">'
        f'<animate attributeName="opacity" from="0" to="1" dur="0.4s" begin="{delay:.2f}s" fill="freeze"/>'
        f'<animateTransform attributeName="transform" type="translate" values="-8 0;0 0" '
        f'dur="0.4s" begin="{delay:.2f}s" fill="freeze"/>'
        f'<text x="{COL_X}" y="{y}" font-size="14" textLength="{COL_W}" '
        f'lengthAdjust="spacingAndGlyphs" xml:space="preserve">'
        f'<tspan fill="{t["PRIMARY"]}">{esc(label)} </tspan>'
        f'<tspan fill="{t["LEADER"]}">{"." * dots}</tspan>'
        f'<tspan fill="{t["TEXT"]}" font-weight="600"> {esc(value)}</tspan>'
        f'</text></g>'
    )


def build(cfg, art, theme):
    """`art` is the ready-made portrait markup for the left panel."""
    t = THEMES[theme]
    s = []
    a = s.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="{FONT}" role="img" aria-label="{esc(cfg["name"])} - {esc(cfg["title_cmd"])}">')

    # ---- defs ----
    a('<defs>')
    a(f'<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
      f'<stop offset="0" stop-color="{t["PRIMARY_DEEP"]}"><animate attributeName="stop-color" '
      f'values="{t["PRIMARY_DEEP"]};{t["PRIMARY"]};{t["ACCENT"]};{t["PRIMARY_DEEP"]}" dur="10s" repeatCount="indefinite"/></stop>'
      f'<stop offset="0.5" stop-color="{t["PRIMARY"]}"><animate attributeName="stop-color" '
      f'values="{t["PRIMARY"]};{t["ACCENT"]};{t["PRIMARY_DEEP"]};{t["PRIMARY"]}" dur="10s" repeatCount="indefinite"/></stop>'
      f'<stop offset="1" stop-color="{t["ACCENT"]}"><animate attributeName="stop-color" '
      f'values="{t["ACCENT"]};{t["PRIMARY_DEEP"]};{t["PRIMARY"]};{t["ACCENT"]}" dur="10s" repeatCount="indefinite"/></stop>'
      f'</linearGradient>')
    a(f'<linearGradient id="inkGrad" x1="0" y1="0" x2="0" y2="{ART_H}" gradientUnits="userSpaceOnUse">'
      f'<stop offset="0" stop-color="{t["ACCENT"]}"/>'
      f'<stop offset="0.42" stop-color="{t["PRIMARY"]}"/>'
      f'<stop offset="1" stop-color="{t["WARM"]}"/>'
      f'<animateTransform attributeName="gradientTransform" type="translate" '
      f'values="0 -120; 0 120; 0 -120" dur="9s" repeatCount="indefinite"/></linearGradient>')
    a(f'<linearGradient id="panelGrad" x1="0" y1="0" x2="0" y2="1">'
      f'<stop offset="0" stop-color="{t["BG_TOP"]}"/><stop offset="1" stop-color="{t["BG_BOT"]}"/></linearGradient>')
    a('<filter id="glow3" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3"/></filter>')
    a('<filter id="txtGlow" x="-30%" y="-30%" width="160%" height="160%">'
      '<feGaussianBlur stdDeviation="0.9" result="b"/><feMerge>'
      '<feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    a(f'<clipPath id="winClip"><rect x="2" y="2" width="{W-4}" height="{H-4}" rx="18"/></clipPath>')
    a(f'<clipPath id="artClip"><rect x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" rx="10"/></clipPath>')
    a(f'<pattern id="scan" width="1" height="3" patternUnits="userSpaceOnUse">'
      f'<rect width="1" height="1" fill="{t["BG_TOP"]}"/></pattern>')
    a('</defs>')

    # ---- window chrome ----
    a(f'<rect x="2" y="2" width="{W-4}" height="{H-4}" rx="18" fill="{t["OUTER"]}"/>')
    a('<g clip-path="url(#winClip)">')
    a(f'<rect x="2" y="2" width="{W-4}" height="{H-4}" fill="url(#panelGrad)"/>')
    a(f'<rect x="2" y="2" width="{W-4}" height="{BAR_H}" fill="{t["BAR"]}"/>')
    a(f'<line x1="2" y1="{BAR_H+2}" x2="{W-2}" y2="{BAR_H+2}" stroke="{t["HAIR"]}"/>')
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        a(f'<circle cx="{30 + i*20}" cy="25" r="5.5" fill="{col}"/>')
    a(f'<text x="{W//2}" y="29" text-anchor="middle" font-size="12" fill="{t["MUTED"]}">'
      f'{esc(cfg["email"])} - % {esc(cfg["title_cmd"])}</text>')

    # ---- left: portrait panel ----
    a(f'<text x="{PAD+2}" y="74" font-size="10" letter-spacing="3" fill="{t["DIM"]}">VISUAL.MAP</text>')
    a(f'<rect x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" rx="10" fill="none" '
      f'stroke="{t["PRIMARY"]}" stroke-width="2" opacity="0.45" filter="url(#glow3)"/>')
    a(f'<rect x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" rx="10" fill="{t["PANEL"]}" '
      f'stroke="{t["PANEL_STROKE"]}"/>')
    a(art)
    # corner brackets
    x2, y2 = ART_X + ART_W, ART_Y + ART_H
    for d in (f'M {ART_X+14} {ART_Y} L {ART_X} {ART_Y} L {ART_X} {ART_Y+14}',
              f'M {x2-14} {ART_Y} L {x2} {ART_Y} L {x2} {ART_Y+14}',
              f'M {ART_X+14} {y2} L {ART_X} {y2} L {ART_X} {y2-14}',
              f'M {x2-14} {y2} L {x2} {y2} L {x2} {y2-14}'):
        a(f'<path d="{d}" fill="none" stroke="{t["PRIMARY"]}" stroke-width="2" opacity="0.8"/>')

    # ---- right: SYSTEM.INFO ----
    a(f'<text x="{COL_X}" y="106" font-size="13" letter-spacing="2" fill="{t["PRIMARY"]}" '
      f'filter="url(#txtGlow)">SYSTEM.INFO</text>')
    a(f'<line x1="{COL_X+96}" y1="102" x2="{COL_X+591}" y2="102" stroke="{t["HAIR"]}"/>')
    a(f'<text x="{W-55}" y="106" text-anchor="end" font-size="12" fill="{t["PRIMARY"]}" font-weight="700">'
      f'<tspan>&#9679;</tspan> LIVE<animate attributeName="opacity" values="1;0.25;1" '
      f'dur="1.6s" repeatCount="indefinite"/></text>')

    # email pill
    a(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.5s" begin="0.6s" fill="freeze"/>'
      f'<rect x="{COL_X}" y="122" width="245" height="20" rx="4" fill="{t["PILL_BG"]}"/>'
      f'<text x="{COL_X+9}" y="136" font-size="14" font-weight="700" fill="{t["PILL_TX"]}">{esc(cfg["email"])}</text>'
      f'<line x1="{COL_X+255}" y1="130" x2="{W-55}" y2="130" stroke="{t["HAIR"]}"/></g>')

    # spec rows
    y, delay = 162, 0.90
    for label, value in cfg["rows"]:
        a(leader_row(label, value, y, delay, t))
        y += 23
        delay += 0.12

    # contact block
    y += 12
    sep = "- Contact " + "-" * (ROW_CHARS - 10)
    a(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.4s" '
      f'begin="{delay:.2f}s" fill="freeze"/>'
      f'<text x="{COL_X}" y="{y}" font-size="14" textLength="{COL_W}" lengthAdjust="spacingAndGlyphs" '
      f'xml:space="preserve" fill="{t["DIM"]}">{esc(sep)}</text></g>')
    y += 24
    delay += 0.12
    for label, value in cfg["contact"]:
        a(leader_row(label, value, y, delay, t))
        y += 23
        delay += 0.12

    # footer
    a(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.6s" '
      f'begin="{delay+0.3:.2f}s" fill="freeze"/>'
      f'<text x="{COL_X}" y="{H-28}" font-size="13" fill="{t["ACCENT"]}">'
      f'&#9656; {esc(cfg["footer"])} &#8595; '
      f'<tspan fill="{t["PRIMARY"]}">&#9608;<animate attributeName="opacity" values="1;0;1" '
      f'dur="1.2s" repeatCount="indefinite"/></tspan></text></g>')

    # animated accent underline along the bottom edge
    a(f'<rect x="2" y="{H-6}" width="{W-4}" height="3" fill="url(#accent)" opacity="0.85"/>')
    a('</g></svg>')
    return "".join(s)


STYLES = ("photo", "color-stipple", "stipple")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(f"usage: generate_banner.py <photo> [out.svg] [{'|'.join(STYLES)}]")
    photo = sys.argv[1]
    out   = sys.argv[2] if len(sys.argv) > 2 else "dark.svg"
    style = sys.argv[3] if len(sys.argv) > 3 else "photo"
    if style not in STYLES:
        sys.exit(f"unknown style {style!r}; pick one of {', '.join(STYLES)}")

    with open("profile.json", encoding="utf-8") as f:
        cfg = json.load(f)

    if style == "photo":
        art = portrait_photo_svg(photo_b64(photo), THEMES["dark"])
        detail = "embedded jpeg"
    elif style == "color-stipple":
        by_col, gw, gh = color_dither_runs(photo)
        art = portrait_color_svg(by_col, gw, gh)
        detail = f"{len(by_col)} colours, {sum(len(v) for v in by_col.values())} runs"
    else:
        runs, gw, gh = dither_runs(photo)
        art = portrait_svg(runs, gw, gh, THEMES["dark"])
        detail = f"{len(runs)} runs"

    svg = build(cfg, art, "dark")
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out}: style={style}, {detail}, {len(svg)//1024}KB")
