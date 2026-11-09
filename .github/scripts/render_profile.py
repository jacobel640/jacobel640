#!/usr/bin/env python3
"""Render the profile README and every image it shows, in Material Design 3.

    GH_TOKEN=...  python .github/scripts/render_profile.py [variant ...]

Variants: "md3" (baseline Material 3, Tonal Spot scheme) and "expressive" (Material 3
Expressive: Expressive scheme, shape library, emphasized type). The first variant given is the
one README.md is written for; the default is VARIANT below.

Every block is rendered four times (desktop / mobile × dark / light) and the README switches
between them with <picture> media queries, so the page reflows on phones and follows the
viewer's GitHub theme. Images are plain SVG served from this repository, with a per-image subset
of Roboto Flex embedded (an SVG shown through <img> cannot load web fonts).

Repository data is cached in assets/live/repos.json, so a run whose token cannot read a private
repository still re-renders its card from the last data seen.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
from urllib.request import Request, urlopen

from fontTools import subset
from fontTools.ttLib import TTFont
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_expressive import SchemeExpressive
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

VARIANT = "expressive"
LOGIN = os.environ.get("PROFILE_LOGIN", "jacobel640")
SEED = 0xFF38BDF8
ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
LIVE = ASSETS / "live"

PORTFOLIO = "https://jacobelcharar.dev"
LINKEDIN = "https://www.linkedin.com/in/jacob-elcharar-b9ba3a3a1/"
EMAIL = "mailto:jacobel640@gmail.com"

# ── Content ──────────────────────────────────────────────────────────────────────────────
NAME = "Jacob Elcharar"
ROLE = ("Native Android Engineer", "Fullstack GenAI Builder")
PITCH = ("4 years of shipping real-world systems — from low-level Android OS internals "
         "to resilient event-driven cloud integrations.")
BADGES = ["Open to senior roles", "4 yrs in production"]

STACK = [
    ("Mobile / Native", "primary", [("Kotlin", "kotlin", ""), ("Android", "androidstudio", ""),
                                    ("Jetpack Compose", None, "JC"), ("Coroutines / Flow", None, "Co")]),
    ("Fullstack & Backend", "secondary", [("TypeScript", "ts", ""), ("Next.js", "nextjs", ""),
                                          ("Node.js", "nodejs", ""), ("PostgreSQL", "postgres", ""),
                                          ("Tailwind CSS", "tailwind", "")]),
    ("AI & Integrations", "tertiary", [("Python", "python", ""), ("OpenAI / GenAI", None, "AI"),
                                       ("Webhooks", None, "⇄"), ("WhatsApp Cloud API", None, "WA")]),
]

PROJECTS = [
    {"slug": "minim4you", "repo": "Minim4You-waba-wix", "title": "Minim4You", "role": "tertiary",
     "status": "Production client system",
     "pitch": "Automated retail ordering & messaging platform bridging Wix e-commerce with "
              "Meta's WhatsApp Business API.",
     "highlights": ["Resilient event-driven webhooks", "PostgreSQL state management",
                    "Automated customer confirmation pipelines"],
     "chips": ["Java", "Spring Boot", "WhatsApp API", "PostgreSQL", "Wix"],
     "links": [("Case study", f"{PORTFOLIO}/projects/minim4you-waba-wix/")]},
    {"slug": "files", "repo": "Files", "title": "Files", "role": "primary",
     "status": "Core native OS",
     "pitch": "High-performance, memory-safe file manager engineered for modern Android "
              "storage constraints.",
     "highlights": ["Scoped Storage & SAF mastery", "Async concurrency with Coroutines / Flow",
                    "Zero main-thread jank"],
     "chips": ["Kotlin", "Jetpack Compose", "Coroutines", "Android SDK"],
     "links": [("Case study", f"{PORTFOLIO}/projects/files/"),
               ("Repository", "https://github.com/jacobel640/Files-legacy")]},
    {"slug": "taskflow", "repo": "TaskFlow", "title": "TaskFlow", "role": "secondary",
     "status": "Open source",
     "pitch": "Offline-first Android task manager with Google sign-in and cloud backup, built on "
              "Clean Architecture and Jetpack Compose.",
     "highlights": ["Room as source of truth, synced to Firestore", "WorkManager reminders that survive reboots",
                    "Clean Architecture · MVVM · UDF"],
     "chips": ["Kotlin", "Jetpack Compose", "Room", "WorkManager", "Firestore"],
     "links": [("Case study", f"{PORTFOLIO}/projects/taskflow/"),
               ("Repository", "https://github.com/jacobel640/TaskFlow")]},
    {"slug": "gio-manetti", "repo": "gio-manetti", "title": "GIO MANETTI", "role": "inverse",
     "status": "Active build",
     "pitch": "Modern fullstack e-commerce and brand platform built for low-latency rendering.",
     "highlights": ["Next.js App Router", "Deterministic inventory handling",
                    "Clean component design system"],
     "chips": ["Next.js", "TypeScript", "Tailwind CSS", "Fullstack"],
     "links": [("Case study", f"{PORTFOLIO}/projects/gio-manetti/")]},
]

SECTIONS = [("01", "Tech stack"), ("02", "Featured systems"), ("03", "Live activity")]

# ── Color: Material dynamic color from one seed ─────────────────────────────────────────
ROLES = ["primary", "onPrimary", "primaryContainer", "onPrimaryContainer", "secondary", "onSecondary",
         "secondaryContainer", "onSecondaryContainer", "tertiary", "onTertiary", "tertiaryContainer",
         "onTertiaryContainer", "surface", "surfaceContainerLowest", "surfaceContainerLow",
         "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest", "onSurface",
         "onSurfaceVariant", "outline", "outlineVariant", "inverseSurface", "inverseOnSurface"]

# Expressive keeps the sky-blue seed for primary and surfaces, but takes its accent roles from
# their own seeds instead of the scheme's hue rotation (which lands on plum and pink).
ACCENT_SEEDS = {"secondary": 0xFFF59E0B,  # amber
                "tertiary": 0xFF10B981}   # emerald


def _roles(s, names) -> dict[str, str]:
    return {r: "#%06X" % (getattr(MaterialDynamicColors, r).get_argb(s) & 0xFFFFFF) for r in names}


@lru_cache(None)
def scheme(variant: str, dark: bool) -> dict[str, str]:
    seed = Hct.from_int(SEED)
    if variant != "expressive":
        return _roles(SchemeTonalSpot(seed, dark, 0.0, "2021"), ROLES)
    c = _roles(SchemeExpressive(seed, dark, 0.0, "2025"), ROLES)
    for role, accent_seed in ACCENT_SEEDS.items():
        src = _roles(SchemeExpressive(Hct.from_int(accent_seed), dark, 0.0, "2025"),
                     ["primary", "onPrimary", "primaryContainer", "onPrimaryContainer"])
        c[role], c[f"on{cap(role)}"] = src["primary"], src["onPrimary"]
        c[f"{role}Container"], c[f"on{cap(role)}Container"] = src["primaryContainer"], src["onPrimaryContainer"]
    return c


def cap(role: str) -> str:
    return role[0].upper() + role[1:]


def container(c: dict, role: str) -> tuple[str, str]:
    """(fill, ink) for a colored container role; "inverse" is the monochrome card."""
    if role == "inverse":
        return c["inverseSurface"], c["inverseOnSurface"]
    return c[f"{role}Container"], c[f"on{cap(role)}Container"]


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a: str, b: str, t: float) -> str:
    """Blend t of color a over color b: an opaque state-layer / tonal fill."""
    return "#%02X%02X%02X" % tuple(round(x * t + y * (1 - t)) for x, y in zip(_rgb(a), _rgb(b)))


def is_light(h: str) -> bool:
    r, g, b = (v / 255 for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45


# ── Type & shape tokens ─────────────────────────────────────────────────────────────────
WIDTH_FACTOR = {"body": .5, "medium": .52, "bold": .55, "display": .5, "emph": .66, "emph-title": .6}


class Style:
    def __init__(self, variant: str, dark: bool):
        self.variant, self.dark = variant, dark
        self.c = scheme(variant, dark)
        x = variant == "expressive"
        self.x = x
        self.display = "emph" if x else "display"
        self.title = "emph-title" if x else "medium"
        self.r_card = 32 if x else 16
        self.r_hero = 40 if x else 28
        self.r_chip = 12 if x else 8
        self.r_tile = 14 if x else 12
        self.btn_h = 56 if x else 44


# ── SVG assembly with embedded font subsets ─────────────────────────────────────────────
@lru_cache(None)
def font_face(key: str, chars: str) -> str:
    # Fixed timestamp so identical text yields identical bytes (no daily churn in the repo).
    font = TTFont(FONTS / f"RobotoFlex-{key}.ttf", recalcTimestamp=False)
    opts = subset.Options()
    opts.flavor = "woff"
    opts.hinting = False
    opts.layout_features = ["kern"]
    sub = subset.Subsetter(opts)
    sub.populate(text=chars or " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:RF-{key};src:url(data:font/woff;base64,{data}) format('woff')}}"


FALLBACK = "'Roboto Flex',Roboto,'Segoe UI',system-ui,-apple-system,Helvetica,Arial,sans-serif"
MOTION = """
.in{animation:in .6s cubic-bezier(.05,.7,.1,1) backwards}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .9s cubic-bezier(.34,1.56,.64,1) both}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}
.spin-r{transform-box:fill-box;transform-origin:center;animation:spin 55s linear infinite reverse}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.2s ease-in-out infinite}
.grow{transform-box:fill-box;transform-origin:left;animation:grow 1s cubic-bezier(.05,.7,.1,1) both}
@keyframes in{from{transform:translateY(6px)}to{transform:none}}
@keyframes pop{from{transform:scale(.82)}to{transform:scale(1)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.8)}}
@keyframes grow{from{transform:scaleX(.4)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;opacity:1!important;transform:none!important}}
"""


def svg(w: float, h: float, body: str, label: str) -> str:
    used = sorted(set(re.findall(r'class="[^"]*\bf-([a-z-]+)', body)))
    text = unescape("".join(re.findall(r">([^<>]+)<", body)))
    faces = "".join(font_face(k, "".join(sorted(set(text)))) for k in used)
    classes = "".join(f".f-{k}{{font-family:RF-{k},{FALLBACK}}}" for k in used)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{escape(label)}">'
            f"<style>{faces}{classes}{MOTION}</style>{body}</svg>\n")


def e(s: object) -> str:
    return escape(str(s), quote=True)


def tw(s: str, size: float, font: str) -> float:
    return len(s) * size * WIDTH_FACTOR[font]


def text(x, y, s, size, font, fill, anchor="start", extra="") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="f-{font}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" {extra}>{e(s)}</text>')


def wrap(s: str, size: float, font: str, max_w: float) -> list[str]:
    lines, line = [], ""
    for word in s.split():
        cand = f"{line} {word}".strip()
        if tw(cand, size, font) <= max_w or not line:
            line = cand
        else:
            lines.append(line)
            line = word
    return lines + [line]


# ── Shapes (Material 3 Expressive shape library, parametric) ────────────────────────────
def polar(cx, cy, r, lobes=0, amp=0.0, rot=0.0, n=200) -> str:
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = r * (1 + amp * math.cos(lobes * (t + rot)))
        pts.append(f"{cx + rr * math.cos(t):.1f},{cy + rr * math.sin(t):.1f}")
    return "M" + " L".join(pts) + "Z"


def squircle(cx, cy, r, n=120, p=4) -> str:
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        x = r * math.copysign(abs(c) ** (2 / p), c)
        y = r * math.copysign(abs(s) ** (2 / p), s)
        pts.append(f"{cx + x:.1f},{cy + y:.1f}")
    return "M" + " L".join(pts) + "Z"


SHAPES = [
    lambda cx, cy, r: polar(cx, cy, r * .92, 9, .08),      # cookie-9
    lambda cx, cy, r: squircle(cx, cy, r * .92),            # squircle
    lambda cx, cy, r: polar(cx, cy, r * .84, 4, .17, .785), # clover-4
    lambda cx, cy, r: polar(cx, cy, r * .93, 8, .06),       # sunny
    lambda cx, cy, r: polar(cx, cy, r * .88, 6, .12),       # flower-6
]


def shape(i: int, cx, cy, r) -> str:
    return SHAPES[i % len(SHAPES)](cx, cy, r)


# ── Shared pieces ───────────────────────────────────────────────────────────────────────
@lru_cache(None)
def icon_data(name: str, dark: bool) -> str:
    folder = "icons" if dark else "icons-light"
    raw = (ASSETS / "ui" / folder / f"{name}.svg").read_text(encoding="utf-8")
    raw = re.sub(r'<rect[^>]*width="256"[^>]*height="256"[^>]*/>', "", raw, count=1)
    return base64.b64encode(raw.encode()).decode()


def tile(st: Style, i: int, x, y, size, icon, mono, fill, ink) -> str:
    cx, cy, r = x + size / 2, y + size / 2, size / 2
    bg = (f'<path d="{shape(i, cx, cy, r)}" fill="{fill}"/>' if st.x
          else f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{st.r_tile}" fill="{fill}"/>')
    if icon:
        pad = size * .2
        fg = (f'<image x="{x + pad:.1f}" y="{y + pad:.1f}" width="{size - 2 * pad:.1f}" height="{size - 2 * pad:.1f}" '
              f'href="data:image/svg+xml;base64,{icon_data(icon, not is_light(fill))}"/>')
    else:
        fg = text(cx, cy + size * .15, mono, round(size * .36), "bold", ink, "middle")
    return bg + fg


def chip(st: Style, x, y, label, fill, ink, stroke=None, size=13, h=32) -> tuple[str, float]:
    w = tw(label, size, "medium") + 28
    s = f' stroke="{stroke}"' if stroke else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{st.r_chip if not st.x else h / 2}" fill="{fill}"{s}/>'
            + text(x + w / 2, y + h / 2 + size * .36, label, size, "medium", ink, "middle")), w


def chip_flow(st: Style, chips, x, y, max_x, fill, ink, stroke=None, size=13, h=32, gap=8, center=False):
    rows, row, cx = [], [], 0.0
    for label in chips:
        w = tw(label, size, "medium") + 28
        if row and cx + w > max_x - x:
            rows.append((row, cx - gap))
            row, cx = [], 0.0
        row.append(label)
        cx += w + gap
    rows.append((row, cx - gap))
    out, cy = [], y
    for labels, width in rows:
        cx = x + ((max_x - x) - width) / 2 if center else x
        for label in labels:
            svg_, w = chip(st, cx, cy, label, fill, ink, stroke, size, h)
            out.append(svg_)
            cx += w + gap
        cy += h + gap
    return "".join(out), cy - gap


def segmented_bar(st: Style, langs, x, y, w, h=8, gap=4, colors=None) -> str:
    colors = colors or [st.c["primary"], st.c["tertiary"], st.c["secondary"], st.c["outline"], st.c["outlineVariant"]]
    usable = w - gap * (len(langs) - 1)
    out, cx = [], x
    for i, (_, share) in enumerate(langs):
        sw = max(usable * share, h)
        out.append(f'<rect class="grow" style="animation-delay:{.1 * i:.1f}s" x="{cx:.1f}" y="{y}" width="{sw:.1f}" height="{h}" rx="{h / 2}" fill="{colors[i % len(colors)]}"/>')
        cx += sw + gap
    return "".join(out)


def legend(st: Style, langs, x, y, size=12, colors=None, ink=None) -> str:
    colors = colors or [st.c["primary"], st.c["tertiary"], st.c["secondary"], st.c["outline"], st.c["outlineVariant"]]
    out, cx = [], x
    for i, (name, share) in enumerate(langs):
        label = f"{name} {share * 100:.0f}%"
        out.append(f'<circle cx="{cx + 5}" cy="{y - size * .35:.1f}" r="5" fill="{colors[i % len(colors)]}"/>'
                   + text(cx + 15, y, label, size, "body", ink or st.c["onSurfaceVariant"]))
        cx += tw(label, size, "body") + 34
    return "".join(out)


# ── Blocks ──────────────────────────────────────────────────────────────────────────────
def hero(st: Style, mobile: bool) -> str:
    c, W = st.c, (400 if mobile else 880)
    if st.x:
        bg, ink, sub = c["primaryContainer"], c["onPrimaryContainer"], c["onPrimaryContainer"]
    else:
        bg, ink, sub = c["surfaceContainerHigh"], c["onSurface"], c["onSurfaceVariant"]
    accent = c["primary"] if not st.x else c["onPrimaryContainer"]
    out = []
    if mobile:
        av = 104
        ax, ay = W / 2 - av / 2, 36
        y = ay + av + 58
        name_size = 40 if not st.x else 38
        out.append(text(W / 2, y, NAME, name_size, st.display, ink, "middle", 'letter-spacing="-.5"'))
        y += 34
        for line in ROLE:
            out.append(text(W / 2, y, line, 18, st.title, accent, "middle"))
            y += 26
        y += 12
        for line in wrap(PITCH, 15, "body", W - 64):
            out.append(text(W / 2, y, line, 15, "body", sub, "middle"))
            y += 22
        y += 10
        chips_svg, y = chip_flow(st, BADGES, 24, y, W - 24, *badge_colors(st), center=True)
        out.append(chips_svg)
        H = y + 36
    else:
        av = 136
        ax, ay = 44, 44
        tx = ax + av + 40
        y = 78
        out.append(text(tx, y, "jacobelcharar.dev", 14, "medium", sub, extra='letter-spacing=".4"'))
        y += 62
        out.append(text(tx, y, NAME, 58 if not st.x else 56, st.display, ink, extra='letter-spacing="-1"'))
        y += 38
        out.append(text(tx, y, f"{ROLE[0]}  ·  {ROLE[1]}", 21, st.title, accent))
        y += 34
        for line in wrap(PITCH, 16, "body", W - tx - 44):
            out.append(text(tx, y, line, 16, "body", sub))
            y += 24
        y += 10
        chips_svg, y = chip_flow(st, BADGES, tx, y, W - 44, *badge_colors(st))
        out.append(chips_svg)
        H = max(y + 44, ay + av + 44)
    # avatar / monogram
    acx, acy, ar = ax + av / 2, ay + av / 2, av / 2
    if st.x:
        deco = (f'<path class="spin" d="{polar(W - 40, -10, 170 if not mobile else 120, 4, .17, .785)}" fill="{c["tertiaryContainer"]}" opacity=".9"/>'
                f'<path class="spin-r" d="{polar(30, H + 20, 110 if not mobile else 80, 8, .06)}" fill="{mix(ink, bg, .1)}"/>')
        mono_bg = f'<path class="pop spin" d="{polar(acx, acy, ar, 12, .07)}" fill="{c["tertiary"]}"/>'
        mono_ink = c["onTertiary"]
    else:
        deco = ""
        mono_bg = f'<circle class="pop" cx="{acx}" cy="{acy}" r="{ar}" fill="{c["primaryContainer"]}"/>'
        mono_ink = c["onPrimaryContainer"]
    mono = text(acx, acy + ar * .3, "JE", round(ar * .82), st.display, mono_ink, "middle")
    body = (f'<clipPath id="hc"><rect width="{W}" height="{H}" rx="{st.r_hero}"/></clipPath>'
            f'<g clip-path="url(#hc)"><rect width="{W}" height="{H}" fill="{bg}"/>{deco}</g>'
            + mono_bg + mono + f'<g class="in">{"".join(out)}</g>')
    return svg(W, H, body, f"{NAME} — {ROLE[0]} · {ROLE[1]}. {PITCH}")


def badge_colors(st: Style):
    c = st.c
    if st.x:
        return mix(c["onPrimaryContainer"], c["primaryContainer"], .14), c["onPrimaryContainer"], None
    return c["surfaceContainerHigh"], c["onSurfaceVariant"], c["outline"]


def button(st: Style, label: str, icon: str, kind: str) -> str:
    c, h = st.c, st.btn_h
    size = 16 if st.x else 14
    w = tw(label, size, st.title if st.x else "medium") + (h * 1.2) + 44
    fill, ink, stroke = {
        "filled": (c["primary"], c["onPrimary"], None),
        "tonal": (c["secondaryContainer"], c["onSecondaryContainer"], None),
        "outlined": ("none", c["primary"] if st.x else c["onSurfaceVariant"], c["outline"]),
    }[kind]
    r = h / 2 if not (st.x and kind == "tonal") else 18
    s = f' stroke="{stroke}" stroke-width="1.2"' if stroke else ""
    icon_ink = ink if kind != "outlined" else c["primary"]
    isz = 20 if st.x else 18
    body = (f'<rect x=".6" y=".6" width="{w - 1.2:.1f}" height="{h - 1.2}" rx="{r}" fill="{fill}"{s}/>'
            f'<g transform="translate({h * .48:.1f} {(h - isz) / 2:.1f}) scale({isz / 24:.3f})"><path d="{ICON_PATHS[icon]}" fill="{icon_ink}"/></g>'
            + text(h * .48 + isz + 10, h / 2 + size * .36, label, size, st.title if st.x else "medium", ink))
    return svg(w, h, body, label)


def link_button(st: Style, label: str) -> str:
    c, h, size = st.c, (44 if st.x else 36), 14
    w = tw(label, size, "medium") + 64
    body = (f'<rect x=".6" y=".6" width="{w - 1.2:.1f}" height="{h - 1.2}" rx="{h / 2}" fill="{c["secondaryContainer"] if st.x else "none"}" '
            + ("" if st.x else f'stroke="{c["outline"]}"') + "/>"
            + text(20, h / 2 + 5, label, size, "medium", c["onSecondaryContainer"] if st.x else c["primary"])
            + text(w - 20, h / 2 + 5, "↗", size, "medium", c["onSecondaryContainer"] if st.x else c["primary"], "end"))
    return svg(w, h, body, label)


SHEET_R = 36
HEADER_H = 76


def sheet(st: Style, w, h) -> str:
    """The soft background each section sits on (the closest a README gets to a page background)."""
    return f'<rect width="{w}" height="{h}" rx="{SHEET_R}" fill="{st.c["surfaceContainerLow"]}"/>'


def header(st: Style, x, y, num: str, title: str, mobile: bool, sub: str = "") -> str:
    c = st.c
    out = (f'<path class="pop spin" d="{polar(x + 24, y + 38, 22, 9, .08)}" fill="{c["tertiaryContainer"]}"/>'
           + text(x + 24, y + 43, num, 14, "bold", c["onTertiaryContainer"], "middle")
           + text(x + 60, y + 48, title, 28 if not mobile else 24, "emph-title", c["onSurface"], extra='letter-spacing="-.4"'))
    if sub and not mobile:
        out += text(x + 60 + tw(title, 28, "emph-title") + 16, y + 47, sub, 14, "body", c["onSurfaceVariant"])
    return out


def section(st: Style, num: str, title: str, mobile: bool) -> str:
    c, W = st.c, (400 if mobile else 880)
    if st.x:
        H = HEADER_H
        body = sheet(st, W, H) + header(st, 12, 0, num, title, mobile, "tap a card for the case study")
    else:
        H = 64
        body = (text(0, 22, num, 13, "medium", c["primary"], extra='letter-spacing="1.2"')
                + text(0, 52, title, 26 if not mobile else 24, "body", c["onSurface"])
                + f'<rect x="0" y="{H - 1}" width="{W}" height="1" fill="{c["outlineVariant"]}"/>')
    return svg(W, H, body, title)


def stack_panel(st: Style, title, role, items, x, y, w, rows, cols) -> tuple[str, float]:
    c = st.c
    if st.x:
        fill, ink = container(c, role)
        tile_fill, mono_ink = ink, fill
    else:
        fill, ink = c["surfaceContainer"], c["onSurface"]
        tile_fill, mono_ink = c["surfaceContainerHighest"], c[role]
    row_h, top, pad = (58 if st.x else 52), 70, 20
    h = top + rows * row_h + 10
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{st.r_card}" fill="{fill}"/>',
           text(x + pad, y + 44, title, 18 if st.x else 16, st.title, ink)]
    if not st.x:
        out.append(f'<rect x="{x + pad}" y="{y + 56}" width="28" height="3" rx="1.5" fill="{c[role]}"/>')
    col_w = (w - 2 * pad) / cols
    tsz = 42 if st.x else 38
    for i, (label, icon, mono) in enumerate(items):
        r_, k = divmod(i, cols)
        ix, iy = x + pad + k * col_w, y + top + r_ * row_h
        avail = col_w - tsz - 16
        lines = [label] if tw(label, 15, "medium") <= avail else wrap(label, 14, "medium", avail)[:2]
        size = 15 if len(lines) == 1 else 14
        ly = iy + tsz / 2 + 5 - (len(lines) - 1) * 8.5
        labels = "".join(text(ix + tsz + 12, ly + j * 17, ln, size, "medium", ink) for j, ln in enumerate(lines))
        out.append(f'<g class="in" style="animation-delay:{.06 * i:.2f}s">'
                   + tile(st, i, ix, iy, tsz, icon, mono, tile_fill, mono_ink) + labels + "</g>")
    return "".join(out), h


def stack(st: Style, mobile: bool) -> str:
    rows = max(len(items) for *_, items in STACK)
    alt = "Tech stack — " + "; ".join(f"{t}: " + ", ".join(i[0] for i in items) for t, _, items in STACK)
    pad, gap = (10, 10) if mobile else (16, 14)
    if mobile:
        W, y, parts = 400, HEADER_H, []
        for title, role, items in STACK:
            svg_, h = stack_panel(st, title, role, items, pad, y, W - 2 * pad, math.ceil(len(items) / 2), 2)
            parts.append(svg_)
            y += h + gap
        H = y - gap + pad
    else:
        W = 880
        pw = (W - 2 * pad - 2 * gap) / 3
        parts = [stack_panel(st, t, r, items, pad + i * (pw + gap), HEADER_H, pw, rows, 1)[0]
                 for i, (t, r, items) in enumerate(STACK)]
        H = HEADER_H + 70 + rows * (58 if st.x else 52) + 10 + pad
    return svg(W, H, sheet(st, W, H) + header(st, 12, 0, "01", "Tech stack", mobile) + "".join(parts), alt)


def project(st: Style, p: dict, repo: dict, mobile: bool) -> str:
    c, role = st.c, p["role"]
    W = 400 if mobile else 880
    if st.x:
        fill, ink = container(c, role)
        sub = mix(ink, fill, .82)
        accent, chip_fill, chip_ink, chip_stroke = ink, mix(ink, fill, .14), ink, None
    else:
        fill, ink, sub = c["surfaceContainer"], c["onSurface"], c["onSurfaceVariant"]
        accent, chip_fill, chip_ink, chip_stroke = c[role], "none", c["onSurfaceVariant"], c["outline"]
    pad = 24 if mobile else 32
    commits = ((repo.get("defaultBranchRef") or {}).get("target") or {}).get("history", {}).get("totalCount", 0)
    pushed = repo.get("pushedAt", "")[:10]
    pushed = datetime.fromisoformat(pushed).strftime("%d %b %Y") if pushed else "—"
    langs = top_langs(repo["languages"]["edges"], 4)
    metrics = [("Commits", f"{commits:,}"), ("Last push", pushed),
               ("Primary", (repo.get("primaryLanguage") or {}).get("name", "—"))]
    content_w = (W - 2 * pad) if mobile else 560
    out = []
    # status chip
    st_label = p["status"]
    sw = tw(st_label, 13, "medium") + 44
    if st.x:
        out.append(f'<rect x="{pad}" y="{pad}" width="{sw:.0f}" height="32" rx="16" fill="{ink}"/>'
                   f'<circle class="pulse" cx="{pad + 18}" cy="{pad + 16}" r="4" fill="{fill}"/>'
                   + text(pad + 30, pad + 21, st_label, 13, "medium", fill))
    else:
        out.append(f'<rect x="{pad}" y="{pad}" width="{sw:.0f}" height="32" rx="8" fill="none" stroke="{c["outline"]}"/>'
                   f'<circle class="pulse" cx="{pad + 18}" cy="{pad + 16}" r="4" fill="{accent}"/>'
                   + text(pad + 30, pad + 21, st_label, 13, "medium", c["onSurfaceVariant"]))
    y = pad + 32 + (54 if st.x else 48)
    tsize = (40 if st.x else 30) if not mobile else (34 if st.x else 28)
    out.append(text(pad, y, p["title"], tsize, st.display if st.x else "body", ink, extra='letter-spacing="-.5"'))
    y += 32
    for line in wrap(p["pitch"], 16, "body", content_w):
        out.append(text(pad, y, line, 16, "body", sub))
        y += 24
    y += 12
    for i, h_ in enumerate(p["highlights"]):
        bullet = (f'<path d="{shape(i, pad + 7, y - 5, 7)}" fill="{accent}"/>' if st.x
                  else f'<circle cx="{pad + 4}" cy="{y - 5}" r="3" fill="{accent}"/>')
        out.append(f'<g class="in" style="animation-delay:{.1 + .08 * i:.2f}s">{bullet}'
                   + text(pad + 22, y, h_, 15, "medium" if st.x else "body", ink) + "</g>")
        y += 26
    y += 10
    chips_svg, y = chip_flow(st, p["chips"], pad, y, pad + content_w, chip_fill, chip_ink, chip_stroke)
    out.append(chips_svg)
    y += 24
    # metrics
    if mobile:
        mw = (W - 2 * pad - 16) / 3
        for i, (label, value) in enumerate(metrics):
            mx = pad + i * (mw + 8)
            if st.x:
                out.append(f'<rect x="{mx:.1f}" y="{y}" width="{mw:.1f}" height="64" rx="20" fill="{mix(ink, fill, .1)}"/>')
            out.append(text(mx + (12 if st.x else 0), y + 24, label, 11.5, "medium", sub)
                       + text(mx + (12 if st.x else 0), y + 48, value, 14 if len(value) > 8 else 17, "bold", ink))
        y += 64 + 22
        bar_y = y
    else:
        mx, my = 640, pad
        if st.x:
            out.append(f'<rect x="{mx - 12}" y="{my}" width="{W - mx - pad + 12}" height="{3 * 70 + 8}" rx="24" fill="{mix(ink, fill, .1)}"/>')
        else:
            out.append(f'<rect x="{mx - 24}" y="{my}" width="1" height="{3 * 70}" fill="{c["outlineVariant"]}"/>')
        for i, (label, value) in enumerate(metrics):
            vy = my + 28 + i * 70
            out.append(text(mx + (12 if st.x else 0), vy, label, 12.5, "medium", sub)
                       + text(mx + (12 if st.x else 0), vy + 30, value, 22 if st.x else 20, "emph-title" if st.x else "body", ink))
        bar_y = max(y, my + 3 * 70 + 8 + 24)
    colors = [ink, mix(ink, fill, .55), mix(ink, fill, .35), mix(ink, fill, .2)] if st.x else None
    out.append(segmented_bar(st, langs, pad, bar_y, W - 2 * pad, 8, 4, colors))
    out.append(legend(st, langs, pad, bar_y + 32, 12.5, colors, sub))
    H = bar_y + 32 + pad
    deco = ""
    if st.x and not mobile:
        deco = f'<path class="spin" d="{shape(PROJECTS.index(p) * 2, W - 10, H + 10, 120)}" fill="{ink}" opacity=".06"/>'
    # Square-ish bottom corners: the card continues into its action row (a separate image per link).
    edge = rrect(0, 0, W, H, st.r_card, st.r_card, ACTION_GAP_R, ACTION_GAP_R)
    body = (f'<clipPath id="pc"><path d="{edge}"/></clipPath>'
            f'<g clip-path="url(#pc)"><rect width="{W}" height="{H}" fill="{fill}"/>{deco}</g>' + "".join(out))
    return svg(W, H, body, f'{p["title"]} — {p["status"]}. {p["pitch"]}')


ACTION_GAP_R = 10


def rrect(x, y, w, h, tl, tr, br, bl) -> str:
    return (f"M{x + tl},{y} H{x + w - tr} Q{x + w},{y} {x + w},{y + tr} V{y + h - br} "
            f"Q{x + w},{y + h} {x + w - br},{y + h} H{x + bl} Q{x},{y + h} {x},{y + h - bl} "
            f"V{y + tl} Q{x},{y} {x + tl},{y} Z")


def action(st: Style, p: dict, idx: int, mobile: bool) -> str:
    """One segment of a card's action row. Segments sit side by side with no gap between the
    images; each draws its own half of the 4px gutter so the row reads as a connected group."""
    c = st.c
    fill, ink = container(c, p["role"]) if st.x else (c["surfaceContainer"], c["onSurface"])
    n = len(p["links"])
    W, H = (400 if mobile else 880) / n, (56 if mobile else 64)
    label, _ = p["links"][idx]
    first, last, g = idx == 0, idx == n - 1, 2
    x0 = 0 if first else g
    x1 = W if last else W - g
    big, small = st.r_card, ACTION_GAP_R
    shape_d = rrect(x0, 0, x1 - x0, H, small, small, big if last else small, big if first else small)
    primary = idx == 0
    bg = mix(ink, fill, .16) if primary else mix(ink, fill, .07)
    size = 16 if not mobile else 15
    tx = (x0 + x1) / 2
    lw = tw(label, size, st.title)
    body = (f'<path d="{shape_d}" fill="{fill}"/>'
            f'<path d="{shape_d}" fill="{bg}"/>'
            + text(tx - 10, H / 2 + size * .36, label, size, st.title, ink, "middle")
            + text(tx + lw / 2 + 6, H / 2 + size * .36, "↗", size, st.title, ink, "middle"))
    return svg(W, H, body, f'{p["title"]} — {label}')


def stats_card(st: Style, x, y, w, data) -> tuple[str, float]:
    c = st.c
    fill = c["surfaceContainer"] if not st.x else c["surfaceContainerHigh"]
    pad = 24
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="0" rx="{st.r_card}" fill="{fill}"/>',
           text(x + pad, y + 42, "GitHub activity", 18 if st.x else 16, st.title, c["onSurface"])]
    yy = y + 64
    if st.x:
        # hero number in a shape
        out.append(f'<path class="pop" d="{polar(x + pad + 46, yy + 46, 46, 9, .08)}" fill="{c["primaryContainer"]}"/>'
                   + text(x + pad + 46, yy + 54, data["year"], 24, "emph", c["onPrimaryContainer"], "middle")
                   + text(x + pad + 108, yy + 40, "contributions", 15, "medium", c["onSurface"])
                   + text(x + pad + 108, yy + 62, "in the last 12 months", 13, "body", c["onSurfaceVariant"]))
        yy += 112
        rows = data["rows"][1:]
    else:
        rows = data["rows"]
    for i, (label, value) in enumerate(rows):
        out.append(f'<g class="in" style="animation-delay:{.06 * i:.2f}s">'
                   + text(x + pad, yy + 18, label, 14, "body", c["onSurfaceVariant"])
                   + text(x + w - pad, yy + 18, value, 15, "bold", c["onSurface"], "end") + "</g>")
        if not st.x and i < len(rows) - 1:
            out.append(f'<rect x="{x + pad}" y="{yy + 30}" width="{w - 2 * pad}" height="1" fill="{c["outlineVariant"]}"/>')
        yy += 38
    yy += 6
    out.append(text(x + pad, yy + 12, "Contributions per week · last 26 weeks", 12, "body", c["onSurfaceVariant"]))
    yy += 24
    top, base, left, right = yy, yy + 44, x + pad, x + w - pad
    peak = max(data["weekly"]) or 1
    if st.x:
        bw = (right - left) / len(data["weekly"])
        for i, v in enumerate(data["weekly"]):
            bh = max(4, (v / peak) * (base - top))
            out.append(f'<rect class="in" style="animation-delay:{.02 * i:.2f}s" x="{left + i * bw + 1.5:.1f}" y="{base - bh:.1f}" '
                       f'width="{bw - 3:.1f}" height="{bh:.1f}" rx="{min(4, (bw - 3) / 2):.1f}" fill="{c["primary"] if i == len(data["weekly"]) - 1 else c["primaryContainer"]}"/>')
    else:
        step = (right - left) / (len(data["weekly"]) - 1)
        pts = [(left + i * step, base - (v / peak) * (base - top)) for i, v in enumerate(data["weekly"])]
        area = f"M{left},{base} L" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f" L{right},{base} Z"
        out.append(f'<path d="{area}" fill="{c["primary"]}" opacity=".16"/>'
                   f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{c["primary"]}" stroke-width="2" stroke-linejoin="round"/>')
    yy = base + 18
    out.append(text(x + w - pad, yy + 8, f"Synced {data['synced']}", 11.5, "body", c["onSurfaceVariant"], "end"))
    h = yy + 26 - y
    out[0] = f'<rect x="{x}" y="{y}" width="{w}" height="{h:.0f}" rx="{st.r_card}" fill="{fill}"/>'
    return "".join(out), h


def langs_card(st: Style, x, y, w, langs, h_min=0) -> tuple[str, float]:
    c = st.c
    fill = c["surfaceContainer"] if not st.x else c["surfaceContainerHigh"]
    pad = 24
    if st.x:
        colors = [c["primaryContainer"], c["tertiaryContainer"], c["secondaryContainer"], c["outline"],
                  c["outlineVariant"], c["onSurfaceVariant"], c["outlineVariant"]]
    else:
        colors = [c["primary"], c["tertiary"], c["secondary"], c["outline"], c["outlineVariant"],
                  c["onSurfaceVariant"], c["outlineVariant"]]
    out = [text(x + pad, y + 42, "Top languages", 18 if st.x else 16, st.title, c["onSurface"])]
    yy = y + 70
    lead = langs[0][1] if langs else 1
    for i, (name, share) in enumerate(langs[:7]):
        bar_x, bar_w = x + pad + 110, w - 2 * pad - 110 - 56
        out.append(text(x + pad, yy + 9, name, 14, "medium", c["onSurface"])
                   + f'<rect x="{bar_x}" y="{yy}" width="{bar_w}" height="10" rx="5" fill="{c["surfaceContainerHighest"]}"/>'
                   + f'<rect class="grow" style="animation-delay:{.08 * i:.2f}s" x="{bar_x}" y="{yy}" width="{max(bar_w * share / lead, 10):.1f}" height="10" rx="5" fill="{colors[i]}"/>'
                   + text(x + w - pad, yy + 9, f"{share * 100:.1f}%", 13, "bold", c["onSurfaceVariant"], "end"))
        yy += 34
    h = max(yy - y + 14, h_min)
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h:.0f}" rx="{st.r_card}" fill="{fill}"/>' + "".join(out), h


def telemetry(st: Style, mobile: bool, data, langs) -> str:
    label = "Live activity — GitHub activity and top languages"
    top = HEADER_H
    if mobile:
        W, pad, gap = 400, 10, 10
        a, ha = stats_card(st, pad, top, W - 2 * pad, data)
        b, hb = langs_card(st, pad, top + ha + gap, W - 2 * pad, langs)
        H = top + ha + gap + hb + pad
    else:
        W, pad, gap = 880, 16, 14
        cw = (W - 2 * pad - gap) / 2
        a, ha = stats_card(st, pad, top, cw, data)
        b, hb = langs_card(st, pad + cw + gap, top, cw, langs, ha)
        H = top + max(ha, hb) + pad
    return svg(W, H, sheet(st, W, H) + header(st, 12, 0, "03", "Live activity", mobile) + a + b, label)


def footer(st: Style, mobile: bool) -> str:
    c, W = st.c, (400 if mobile else 880)
    body = (f'<rect x="0" y="0" width="{W}" height="1" fill="{c["outlineVariant"]}"/>'
            + text(W / 2, 30, "Live data · refreshed daily", 12.5, "body", c["onSurfaceVariant"], "middle"))
    return svg(W, 44, body, "Live data, refreshed daily")


ICON_PATHS = {
    "globe": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.9 6h-2.95a15.7 15.7 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.9 8ZM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96ZM4.26 14A7.9 7.9 0 0 1 4 12c0-.69.1-1.36.26-2h3.38a16.5 16.5 0 0 0 0 4H4.26Zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.99 7.99 0 0 1 5.08 16Zm2.95-8H5.08a7.99 7.99 0 0 1 4.33-3.56A15.7 15.7 0 0 0 8.03 8ZM12 19.96A14.1 14.1 0 0 1 10.09 16h3.82A14.1 14.1 0 0 1 12 19.96ZM14.34 14H9.66a14.7 14.7 0 0 1 0-4h4.68a14.7 14.7 0 0 1 0 4Zm.25 5.56A15.7 15.7 0 0 0 15.97 16h2.95a8.03 8.03 0 0 1-4.33 3.56ZM16.36 14a16.5 16.5 0 0 0 0-4h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38Z",
    "linkedin": "M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12Zm1.78 13.02H3.56V9h3.56v11.45ZM22.23 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z",
    "mail": "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Zm0 4.24-7.47 4.67a1 1 0 0 1-1.06 0L4 8.24V6l8 5 8-5v2.24Z",
}


# ── Live data ────────────────────────────────────────────────────────────────────────────
def gql(query: str, variables: dict, token: str) -> dict:
    req = Request("https://api.github.com/graphql",
                  data=json.dumps({"query": query, "variables": variables}).encode(),
                  headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                           "User-Agent": "profile-renderer"})
    with urlopen(req, timeout=40) as resp:
        payload = json.load(resp)
    if payload.get("errors") and not payload.get("data"):
        raise RuntimeError(payload["errors"])
    return payload.get("data") or {}


USER_Q = """
query($login:String!, $privacy:RepositoryPrivacy) {
  user(login:$login) {
    createdAt
    pullRequests { totalCount }
    publicRepos: repositories(ownerAffiliations:OWNER, privacy:PUBLIC) { totalCount }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, privacy:$privacy) {
      nodes { languages(first:10, orderBy:{field:SIZE, direction:DESC}) { edges { size node { name } } } }
    }
  }
}"""

CAL_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) { contributionsCollection(from:$from, to:$to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } } } }
}"""

REPO_Q = """
query($owner:String!, $name:String!) {
  repository(owner:$owner, name:$name) {
    pushedAt primaryLanguage { name }
    languages(first:8, orderBy:{field:SIZE, direction:DESC}) { edges { size node { name } } }
    defaultBranchRef { target { ... on Commit { history { totalCount } } } }
  }
}"""


def top_langs(edges: list[dict], limit: int = 5) -> list[tuple[str, float]]:
    sizes: dict[str, int] = {}
    for edge in edges:
        sizes[edge["node"]["name"]] = sizes.get(edge["node"]["name"], 0) + edge["size"]
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    head = [(n, s / total) for n, s in ranked[:limit] if s / total >= 0.01]
    rest = 1 - sum(s for _, s in head)
    return head + ([("Other", rest)] if rest > 0.005 else [])


def fetch(token: str):
    today = datetime.now(timezone.utc).date()
    include_private = os.environ.get("INCLUDE_PRIVATE", "").lower() == "true"
    user = gql(USER_Q, {"login": LOGIN, "privacy": None if include_private else "PUBLIC"}, token)["user"]
    created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    days: dict[date, int] = {}
    start = created
    while start <= today:
        end = min(start + timedelta(days=364), today)
        cal = gql(CAL_Q, {"login": LOGIN, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}, token)
        for week in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
        start = end + timedelta(days=1)
    first = today - timedelta(days=26 * 7 - 1)
    data = {
        "year": f"{sum(v for d, v in days.items() if d > today - timedelta(days=365)):,}",
        "rows": [
            ("Contributions · 12 months", f"{sum(v for d, v in days.items() if d > today - timedelta(days=365)):,}"),
            ("Contributions · all time", f"{sum(days.values()):,}"),
            ("Pull requests" if include_private else "Public pull requests", f"{user['pullRequests']['totalCount']:,}"),
            ("Public repositories", f"{user['publicRepos']['totalCount']:,}"),
            ("On GitHub", f"{(today - created).days / 365.25:.1f} yrs"),
        ],
        "weekly": [sum(days.get(first + timedelta(days=w * 7 + i), 0) for i in range(7)) for w in range(26)],
        "synced": today.strftime("%d %b %Y"),
    }
    langs = top_langs([e_ for n in user["repositories"]["nodes"] for e_ in n["languages"]["edges"]], 6)

    cache_path = LIVE / "repos.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for p in PROJECTS:
        repo = gql(REPO_Q, {"owner": LOGIN, "name": p["repo"]}, token).get("repository")
        if repo:
            cache[p["repo"]] = repo
        else:
            print(f"{p['repo']}: not readable with this token; using cached data")
    write(cache_path, json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return data, langs, cache


# ── Output ───────────────────────────────────────────────────────────────────────────────
def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


def render_variant(variant: str, data, langs, repos) -> None:
    out = ASSETS / variant
    for dark in (True, False):
        st = Style(variant, dark)
        theme = "dark" if dark else "light"
        for mobile in (False, True):
            size = "m" if mobile else "d"
            sfx = f"{size}-{theme}"
            write(out / f"hero-{sfx}.svg", hero(st, mobile))
            write(out / f"stack-{sfx}.svg", stack(st, mobile))
            write(out / f"telemetry-{sfx}.svg", telemetry(st, mobile, data, langs))
            write(out / f"footer-{sfx}.svg", footer(st, mobile))
            write(out / f"section-02-{sfx}.svg", section(st, "02", "Featured systems", mobile))
            for p in PROJECTS:
                if p["repo"] in repos:
                    write(out / f"project-{p['slug']}-{sfx}.svg", project(st, p, repos[p["repo"]], mobile))
                for i in range(len(p["links"])):
                    write(out / f"action-{p['slug']}-{i}-{sfx}.svg", action(st, p, i, mobile))
        write(out / f"btn-portfolio-{theme}.svg", button(st, "jacobelcharar.dev", "globe", "filled"))
        write(out / f"btn-linkedin-{theme}.svg", button(st, "LinkedIn", "linkedin", "tonal"))
        write(out / f"btn-email-{theme}.svg", button(st, "Email", "mail", "outlined"))


def pic(base: str, alt: str, width: str = "100%", responsive: bool = True, height: str = "") -> str:
    size = f'height="{height}"' if height else f'width="{width}"'
    if responsive:
        return ("<picture>"
                f'<source media="(max-width: 600px) and (prefers-color-scheme: light)" srcset="{base}-m-light.svg">'
                f'<source media="(max-width: 600px)" srcset="{base}-m-dark.svg">'
                f'<source media="(prefers-color-scheme: light)" srcset="{base}-d-light.svg">'
                f'<img src="{base}-d-dark.svg" {size} alt="{e(alt)}"></picture>')
    return ("<picture>"
            f'<source media="(prefers-color-scheme: light)" srcset="{base}-light.svg">'
            f'<img src="{base}-dark.svg" {size} alt="{e(alt)}"></picture>')


def readme(variant: str) -> str:
    a = f"./assets/{variant}"
    btn_h = "56" if variant == "expressive" else "44"
    parts = [
        "<!-- Generated by .github/scripts/render_profile.py: edit content there, not here. -->",
        "",
        '<div align="center">',
        "",
        f'<a href="{PORTFOLIO}">{pic(f"{a}/hero", f"{NAME} — {ROLE[0]} · {ROLE[1]}")}</a>',
        "",
        f'<a href="{PORTFOLIO}">{pic(f"{a}/btn-portfolio", "jacobelcharar.dev", responsive=False, height=btn_h)}</a>&nbsp;'
        f'<a href="{LINKEDIN}">{pic(f"{a}/btn-linkedin", "LinkedIn", responsive=False, height=btn_h)}</a>&nbsp;'
        f'<a href="{EMAIL}">{pic(f"{a}/btn-email", "Email", responsive=False, height=btn_h)}</a>',
        "",
        "</div>",
        "",
        "<br />",
        "",
        pic(f"{a}/stack", "Tech stack: Kotlin, Android, Jetpack Compose, Coroutines / Flow; TypeScript, Next.js, "
                          "Node.js, PostgreSQL, Tailwind CSS; Python, OpenAI / GenAI, Webhooks, WhatsApp Cloud API"),
        "",
        pic(f"{a}/section-02", "02 — Featured systems"),
        "",
    ]
    for p in PROJECTS:
        # Card body and its action row are one paragraph; the action images must touch (no
        # whitespace between them) so their widths add up to exactly 100%.
        width = f"{100 / len(p['links']):g}%"
        actions = "".join(
            f'<a href="{url}">{pic(f"{a}/action-{p["slug"]}-{i}", f"{p['title']} — {label}", width=width)}</a>'
            for i, (label, url) in enumerate(p["links"]))
        parts += [f'<p><a href="{p["links"][0][1]}">{pic(f"{a}/project-{p["slug"]}", f"{p['title']} — {p['pitch']}")}</a><br>{actions}</p>',
                  ""]
    parts += [
        pic(f"{a}/telemetry", "Live activity: GitHub activity and top languages"),
        "",
        pic(f"{a}/footer", "Live data, refreshed daily"),
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    variants = argv or [VARIANT]
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN is required", file=sys.stderr)
        return 1
    data, langs, repos = fetch(token)
    for v in variants:
        render_variant(v, data, langs, repos)
    preview = os.environ.get("PREVIEW_DIR")
    if preview:
        for v in variants:
            write(Path(preview) / f"README-{v}.md", readme(v))
    else:
        write(ROOT / "README.md", readme(variants[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
