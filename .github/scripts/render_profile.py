#!/usr/bin/env python3
"""Render every image the profile README shows, in one palette, from live GitHub data.

Output is plain SVG in assets/, so the README never depends on a third-party image host or on
GitHub's image proxy being reachable. Edit content here, not in the SVGs.

    GH_TOKEN=...  python .github/scripts/render_profile.py

A repository the token cannot read keeps its previous card instead of being overwritten.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

LOGIN = os.environ.get("PROFILE_LOGIN", "jacobel640")
ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "assets" / "ui"
LIVE = ROOT / "assets" / "live"
ICONS_DIR = UI / "icons"

# ── Design tokens ────────────────────────────────────────────────────────────────────────
BG = "#0D1117"
SURFACE = "#111827"
TILE = "#242938"  # matches the skillicons dark tile
STROKE = "#1E293B"
TEXT = "#E2E8F0"
TITLE = "#F8FAFC"
MUTED = "#94A3B8"
DIM = "#64748B"
CYAN = "#38BDF8"
VIOLET = "#818CF8"
EMERALD = "#10B981"
RAMP = [CYAN, VIOLET, EMERALD, "#0284C7", "#6366F1", "#059669", "#475569"]

MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
SANS = "'Inter','Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"

BASE_CSS = """
.mono{font-family:%(mono)s}
.sans{font-family:%(sans)s}
.fade{opacity:0;animation:fade .7s ease-out forwards}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-in-out infinite}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes pulse{0%%,100%%{opacity:1;transform:scale(1)}50%%{opacity:.35;transform:scale(1.9)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;opacity:1!important}}
""" % {"mono": MONO, "sans": SANS}

# ── Content ──────────────────────────────────────────────────────────────────────────────
# Each stack item is (label, skillicons file name or None, monogram for items without an icon).
STACK = [
    ("mobile", "Mobile / Native", CYAN, [
        ("Kotlin", "kotlin", ""),
        ("Android", "androidstudio", ""),
        ("Jetpack Compose", None, "JC"),
        ("Coroutines / Flow", None, "Co"),
    ]),
    ("fullstack", "Fullstack & Backend", VIOLET, [
        ("TypeScript", "ts", ""),
        ("Next.js", "nextjs", ""),
        ("Node.js", "nodejs", ""),
        ("PostgreSQL", "postgres", ""),
        ("Tailwind CSS", "tailwind", ""),
    ]),
    ("ai", "AI & Integrations", EMERALD, [
        ("Python", "python", ""),
        ("OpenAI / GenAI", None, "AI"),
        ("Webhooks", None, "⇄"),
        ("WhatsApp Cloud API", None, "WA"),
    ]),
]

FLAGSHIPS = [
    {
        "slug": "minim4you",
        "repo": "Minim4You-waba-wix",
        "title": "Minim4You",
        "status": "PRODUCTION CLIENT SYSTEM",
        "accent": EMERALD,
        "pitch": "Automated retail ordering & messaging platform bridging Wix e-commerce "
        "with Meta's WhatsApp Business API.",
        "highlights": ["Resilient event-driven webhooks", "PostgreSQL state management",
                       "Automated customer confirmation pipelines"],
        "chips": ["Java", "Spring Boot", "WhatsApp API", "PostgreSQL", "Wix"],
    },
    {
        "slug": "files",
        "repo": "Files",
        "title": "Files",
        "status": "CORE NATIVE OS",
        "accent": CYAN,
        "pitch": "High-performance, memory-safe file manager engineered for modern "
        "Android storage constraints.",
        "highlights": ["Scoped Storage & SAF mastery", "Async background concurrency with Coroutines / Flow",
                       "Zero main-thread jank"],
        "chips": ["Kotlin", "Jetpack Compose", "Coroutines", "Android SDK"],
    },
    {
        "slug": "gio-manetti",
        "repo": "gio-manetti",
        "title": "GIO MANETTI",
        "status": "ACTIVE BUILD",
        "accent": VIOLET,
        "pitch": "Modern fullstack e-commerce and brand platform built for low-latency rendering.",
        "highlights": ["Next.js App Router", "Deterministic inventory handling",
                       "Clean component design system"],
        "chips": ["Next.js", "TypeScript", "Tailwind CSS", "Fullstack"],
    },
]

SECTIONS = [("01", "TECH STACK"), ("02", "FEATURED SYSTEMS"), ("03", "LIVE ACTIVITY")]


# ── Helpers ──────────────────────────────────────────────────────────────────────────────
def e(text: object) -> str:
    return escape(str(text), quote=True)


def svg(width: int, height: int, body: str, css: str = "", label: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{e(label)}">'
        f"<style>{BASE_CSS}{css}</style>{body}</svg>\n"
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


def text_w(text: str, size: float) -> float:
    return len(text) * size * 0.61


def wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) <= max_chars:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def card_frame(width: int, height: int, accent: str = CYAN) -> str:
    return (
        '<defs><linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{accent}" stop-opacity=".55"/>'
        f'<stop offset=".45" stop-color="{STROKE}"/><stop offset="1" stop-color="{STROKE}"/>'
        "</linearGradient></defs>"
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="14" fill="{BG}" stroke="url(#edge)"/>'
    )


def chrome(prompt: str, x: int = 22, y: int = 30) -> str:
    dots = "".join(
        f'<circle cx="{x + i * 16}" cy="{y - 4}" r="4.5" fill="{c}" opacity=".9"/>'
        for i, c in enumerate((CYAN, VIOLET, EMERALD))
    )
    return (
        dots + f'<text x="{x + 56}" y="{y}" class="mono" font-size="12.5" fill="{DIM}">'
        f'<tspan fill="{EMERALD}">~</tspan> <tspan fill="{CYAN}">$</tspan> <tspan fill="{TEXT}">{e(prompt)}</tspan></text>'
    )


def chip_row(chips: list[str], x: float, y: float, max_x: float, size: float = 11.5) -> tuple[str, float]:
    out, cx, cy, h, gap = [], x, y, 24, 8
    for chip in chips:
        w = text_w(chip, size) + 22
        if cx + w > max_x and cx > x:
            cx, cy = x, cy + h + gap
        out.append(
            f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{w:.1f}" height="{h}" rx="7" fill="{SURFACE}" stroke="{STROKE}"/>'
            f'<text x="{cx + w / 2:.1f}" y="{cy + h / 2 + 4:.1f}" text-anchor="middle" class="mono" '
            f'font-size="{size}" fill="{TEXT}">{e(chip)}</text>'
        )
        cx += w + gap
    return "".join(out), cy + h


def lang_bar(langs: list[tuple[str, float]], x: float, y: float, width: float) -> str:
    out = [f'<clipPath id="bar"><rect x="{x}" y="{y}" width="{width}" height="6" rx="3"/></clipPath>',
           f'<rect x="{x}" y="{y}" width="{width}" height="6" rx="3" fill="{SURFACE}"/><g clip-path="url(#bar)">']
    cx = x
    for i, (_, share) in enumerate(langs):
        out.append(f'<rect x="{cx:.2f}" y="{y}" width="{width * share + .5:.2f}" height="6" fill="{RAMP[i % len(RAMP)]}"/>')
        cx += width * share
    return "".join(out) + "</g>"


def top_langs(edges: list[dict], limit: int = 5) -> list[tuple[str, float]]:
    sizes: dict[str, int] = {}
    for edge in edges:
        sizes[edge["node"]["name"]] = sizes.get(edge["node"]["name"], 0) + edge["size"]
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    head = [(name, size / total) for name, size in ranked[:limit] if size / total >= 0.01]
    rest = 1 - sum(share for _, share in head)
    if rest > 0.005:
        head.append(("Other", rest))
    return head


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_day(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else "—"


# ── Static UI ────────────────────────────────────────────────────────────────────────────
def render_hero() -> str:
    w, h = 1200, 360
    css = """
.b1{animation:d1 14s ease-in-out infinite alternate}
.b2{animation:d2 17s ease-in-out infinite alternate}
.b3{animation:d3 20s ease-in-out infinite alternate}
@keyframes d1{to{transform:translate(120px,40px)}}
@keyframes d2{to{transform:translate(-140px,-30px)}}
@keyframes d3{to{transform:translate(90px,-50px)}}
.shine{animation:shine 6s linear infinite}
@keyframes shine{from{transform:translateX(-1200px)}to{transform:translateX(1200px)}}
.cursor{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
"""
    body = f"""
<defs>
  <filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="70"/></filter>
  <filter id="glow" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
  <linearGradient id="name" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#E0F2FE"/><stop offset=".45" stop-color="{CYAN}"/><stop offset="1" stop-color="{VIOLET}"/>
  </linearGradient>
  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".2" stop-color="{CYAN}"/>
    <stop offset=".5" stop-color="{VIOLET}"/><stop offset=".8" stop-color="{EMERALD}"/>
    <stop offset="1" stop-color="{EMERALD}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".9"/>
    <stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
    <path d="M40 0H0V40" fill="none" stroke="{CYAN}" stroke-opacity=".07"/>
  </pattern>
  <radialGradient id="fadeMask" cx=".5" cy=".45" r=".65">
    <stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </radialGradient>
  <mask id="gridMask"><rect width="{w}" height="{h}" fill="url(#fadeMask)"/></mask>
  <clipPath id="frame"><rect width="{w}" height="{h}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#frame)">
  <rect width="{w}" height="{h}" fill="{BG}"/>
  <g filter="url(#blur)" opacity=".55">
    <circle class="b1" cx="250" cy="90" r="190" fill="{CYAN}" opacity=".55"/>
    <circle class="b2" cx="900" cy="110" r="210" fill="{VIOLET}" opacity=".6"/>
    <circle class="b3" cx="620" cy="360" r="170" fill="{EMERALD}" opacity=".35"/>
  </g>
  <rect width="{w}" height="{h}" fill="url(#grid)" mask="url(#gridMask)"/>
  <text x="44" y="52" class="mono" font-size="15" fill="{DIM}"><tspan fill="{EMERALD}">jacobel640@github</tspan>:<tspan fill="{CYAN}">~</tspan>$ whoami<tspan class="cursor" fill="{CYAN}"> ▍</tspan></text>
  <text x="1156" y="52" text-anchor="end" class="mono" font-size="13" fill="{DIM}">jacobelcharar.dev</text>
  <text x="600" y="186" text-anchor="middle" class="sans" font-size="84" font-weight="800" letter-spacing="-1.5" fill="{CYAN}" opacity=".45" filter="url(#glow)">Jacob Elcharar</text>
  <text x="600" y="186" text-anchor="middle" class="sans" font-size="84" font-weight="800" letter-spacing="-1.5" fill="url(#name)">Jacob Elcharar</text>
  <text x="600" y="236" text-anchor="middle" class="mono" font-size="21" fill="{MUTED}" letter-spacing="1">Native Android Engineer  <tspan fill="{VIOLET}">·</tspan>  Fullstack GenAI Builder</text>
  <g class="mono" font-size="14" fill="{DIM}">
    <circle class="pulse" cx="438" cy="286" r="4.5" fill="{EMERALD}"/>
    <text x="452" y="291">4 yrs shipping production systems <tspan fill="{VIOLET}">·</tspan> open to senior roles</text>
  </g>
  <rect x="0" y="{h - 3}" width="{w}" height="3" fill="url(#rule)"/>
  <rect class="shine" x="0" y="{h - 3}" width="260" height="3" fill="url(#sheen)" opacity=".7"/>
</g>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{STROKE}"/>
"""
    return svg(w, h, body, css, "Jacob Elcharar — Native Android Engineer, Fullstack GenAI Builder")


def render_divider(num: str, title: str) -> str:
    w, h = 880, 46
    tw = text_w(f"{num}  {title}", 15) + 40
    body = f"""
<defs><linearGradient id="r" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="{VIOLET}" stop-opacity=".6"/>
  <stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></linearGradient></defs>
<text x="0" y="29" class="mono" font-size="15" font-weight="700" letter-spacing="2">
  <tspan fill="{CYAN}">// {e(num)}</tspan><tspan fill="{TITLE}" dx="10">{e(title)}</tspan></text>
<rect x="{tw:.0f}" y="23" width="{w - tw:.0f}" height="1.5" fill="url(#r)"/>
"""
    return svg(w, h, body, label=title.title())


def icon_tile(icon: str | None, mono: str, x: float, y: float, size: float, accent: str) -> str:
    if icon:
        data = base64.b64encode((ICONS_DIR / f"{icon}.svg").read_bytes()).decode()
        return f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:image/svg+xml;base64,{data}"/>'
    r = size * 60 / 256
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{r:.1f}" fill="{TILE}"/>'
        f'<text x="{x + size / 2}" y="{y + size / 2 + 5}" text-anchor="middle" class="mono" '
        f'font-size="{size * .42:.1f}" font-weight="800" fill="{accent}">{e(mono)}</text>'
    )


def render_stack_panel(title: str, accent: str, items: list[tuple[str, str | None, str]], rows: int) -> str:
    w, row_h, top = 286, 46, 66
    h = top + rows * row_h + 12
    out = [card_frame(w, h, accent),
           f'<rect x="22" y="26" width="4" height="18" rx="2" fill="{accent}"/>',
           f'<text x="36" y="40" class="mono" font-size="13" font-weight="700" letter-spacing="1.4" fill="{TITLE}">{e(title.upper())}</text>']
    for i, (label, icon, mono) in enumerate(items):
        y = top + i * row_h
        out.append(f'<g class="fade" style="animation-delay:{.08 * i:.2f}s">'
                   + icon_tile(icon, mono, 22, y, 34, accent)
                   + f'<text x="70" y="{y + 22}" class="sans" font-size="15" font-weight="600" fill="{TEXT}">{e(label)}</text></g>')
    return svg(w, h, "".join(out), label=f"{title}: " + ", ".join(i[0] for i in items))


ICON_PATHS = {
    "globe": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.9 6h-2.95a15.7 15.7 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.9 8ZM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96ZM4.26 14A7.9 7.9 0 0 1 4 12c0-.69.1-1.36.26-2h3.38a16.5 16.5 0 0 0 0 4H4.26Zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.99 7.99 0 0 1 5.08 16Zm2.95-8H5.08a7.99 7.99 0 0 1 4.33-3.56A15.7 15.7 0 0 0 8.03 8ZM12 19.96A14.1 14.1 0 0 1 10.09 16h3.82A14.1 14.1 0 0 1 12 19.96ZM14.34 14H9.66a14.7 14.7 0 0 1 0-4h4.68a14.7 14.7 0 0 1 0 4Zm.25 5.56A15.7 15.7 0 0 0 15.97 16h2.95a8.03 8.03 0 0 1-4.33 3.56ZM16.36 14a16.5 16.5 0 0 0 0-4h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38Z",
    "linkedin": "M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12Zm1.78 13.02H3.56V9h3.56v11.45ZM22.23 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z",
    "mail": "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Zm0 4.24-7.47 4.67a1 1 0 0 1-1.06 0L4 8.24V6l8 5 8-5v2.24Z",
}


def render_button(label: str, icon: str, accent: str) -> str:
    h = 46
    w = int(text_w(label, 14) * 1.12 + 92)
    body = f"""
<defs><linearGradient id="s" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent}" stop-opacity=".25"/></linearGradient></defs>
<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{(h - 2) / 2}" fill="{BG}" stroke="url(#s)" stroke-width="1.5"/>
<g transform="translate(20 {h / 2 - 9}) scale(.75)"><path d="{ICON_PATHS[icon]}" fill="{accent}"/></g>
<text x="48" y="{h / 2 + 5}" class="mono" font-size="14" font-weight="600" fill="{TITLE}">{e(label)}</text>
<text x="{w - 22}" y="{h / 2 + 5}" text-anchor="end" class="mono" font-size="14" fill="{accent}">↗</text>
"""
    return svg(w, h, body, label=label)


def render_link(label: str, accent: str) -> str:
    h = 30
    w = int(text_w(label, 12) + 42)
    body = (
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{(h - 1) / 2}" fill="{BG}" stroke="{accent}" stroke-opacity=".5"/>'
        f'<text x="16" y="{h / 2 + 4}" class="mono" font-size="12" font-weight="600" fill="{TEXT}">{e(label)}</text>'
        f'<text x="{w - 16}" y="{h / 2 + 4}" text-anchor="end" class="mono" font-size="12" fill="{accent}">↗</text>'
    )
    return svg(w, h, body, label=label)


def render_footer() -> str:
    w, h = 880, 40
    body = f"""
<defs><linearGradient id="r" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".3" stop-color="{CYAN}"/>
  <stop offset=".5" stop-color="{VIOLET}"/><stop offset=".7" stop-color="{EMERALD}"/>
  <stop offset="1" stop-color="{EMERALD}" stop-opacity="0"/></linearGradient></defs>
<rect x="0" y="8" width="{w}" height="1.5" fill="url(#r)"/>
<text x="{w / 2}" y="32" text-anchor="middle" class="mono" font-size="12" fill="{DIM}">live data · refreshed daily</text>
"""
    return svg(w, h, body, label="Live data, refreshed daily")


# ── Live data ────────────────────────────────────────────────────────────────────────────
def gql(query: str, variables: dict, token: str) -> dict:
    req = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-renderer"},
    )
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
    isPrivate pushedAt
    primaryLanguage { name }
    languages(first:8, orderBy:{field:SIZE, direction:DESC}) { edges { size node { name } } }
    defaultBranchRef { target { ... on Commit { history { totalCount } } } }
  }
}"""


def calendar(token: str, created: date, today: date) -> dict[date, int]:
    days: dict[date, int] = {}
    start = created
    while start <= today:
        end = min(start + timedelta(days=364), today)
        data = gql(CAL_Q, {"login": LOGIN, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}, token)
        for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[date.fromisoformat(day["date"])] = day["contributionCount"]
        start = end + timedelta(days=1)
    return days


def render_stats(rows: list[tuple[str, str, str]], weekly: list[int], synced: str) -> str:
    w, h = 430, 250
    out = [card_frame(w, h, CYAN), chrome(f"gh stats {LOGIN}")]
    for i, (label, value, color) in enumerate(rows):
        y = 70 + i * 25
        out.append(
            f'<g class="fade" style="animation-delay:{.1 + i * .08:.2f}s">'
            f'<text x="24" y="{y}" class="mono" font-size="13" fill="{color}">▸</text>'
            f'<text x="42" y="{y}" class="mono" font-size="13" fill="{MUTED}">{e(label)}</text>'
            f'<text x="{w - 24}" y="{y}" text-anchor="end" class="mono" font-size="13.5" font-weight="700" fill="{TITLE}">{e(value)}</text></g>'
        )
    top, base, left, right = 206, 230, 24, w - 24
    peak = max(weekly) or 1
    step = (right - left) / max(len(weekly) - 1, 1)
    pts = [(left + i * step, base - (v / peak) * (base - top)) for i, v in enumerate(weekly)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M{left},{base} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{right},{base} Z"
    out.append(
        f'<defs><linearGradient id="sp" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{CYAN}"/>'
        f'<stop offset="1" stop-color="{VIOLET}"/></linearGradient>'
        f'<linearGradient id="spa" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity=".28"/>'
        f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient></defs>'
        f'<text x="24" y="{top - 12}" class="mono" font-size="10.5" fill="{DIM}">contributions / week · last 26 weeks</text>'
        f'<text x="{w - 24}" y="{top - 12}" text-anchor="end" class="mono" font-size="10.5" fill="{DIM}">synced {e(synced)}</text>'
        f'<path d="{area}" fill="url(#spa)"/>'
        f'<polyline points="{line}" fill="none" stroke="url(#sp)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle class="pulse" cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="{VIOLET}"/>'
    )
    return svg(w, h, "".join(out), label="GitHub activity")


def render_languages(langs: list[tuple[str, float]], scope: str) -> str:
    w, h = 430, 250
    css = ".grow{transform-box:fill-box;transform-origin:left;animation:grow 1s ease-out forwards;transform:scaleX(0)}@keyframes grow{to{transform:scaleX(1)}}"
    out = [card_frame(w, h, VIOLET), chrome(f"linguist --top --{scope}")]
    bar_x, bar_w = 150, w - 150 - 70
    for i, (name, share) in enumerate(langs[:6]):
        y = 66 + i * 28
        color = RAMP[i % len(RAMP)]
        out.append(
            f'<text x="24" y="{y + 9}" class="mono" font-size="13" fill="{TEXT}">{e(name)}</text>'
            f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="10" rx="5" fill="{SURFACE}"/>'
            f'<rect class="grow" style="animation-delay:{.1 + i * .08:.2f}s" x="{bar_x}" y="{y}" '
            f'width="{max(bar_w * share / langs[0][1], 6):.1f}" height="10" rx="5" fill="{color}"/>'
            f'<text x="{w - 24}" y="{y + 9}" text-anchor="end" class="mono" font-size="12.5" font-weight="700" fill="{MUTED}">{share * 100:.1f}%</text>'
        )
    return svg(w, h, "".join(out), css, "Top languages: " + ", ".join(f"{n} {p * 100:.0f}%" for n, p in langs))


def render_project(cfg: dict, repo: dict) -> str:
    w = 880
    accent = cfg["accent"]
    commits = ((repo.get("defaultBranchRef") or {}).get("target") or {}).get("history", {}).get("totalCount", 0)
    pushed = datetime.fromisoformat(repo["pushedAt"].replace("Z", "+00:00")).date() if repo.get("pushedAt") else None
    langs = top_langs(repo["languages"]["edges"], 4)
    status_w = text_w(cfg["status"], 11) + 46

    out = [
        f'<rect x="0" y="22" width="3" height="0" rx="1.5" fill="{accent}"/>',  # placeholder, height set below
        f'<rect x="28" y="24" width="{status_w:.0f}" height="26" rx="13" fill="{accent}" fill-opacity=".1" stroke="{accent}" stroke-opacity=".55"/>',
        f'<circle cx="44" cy="37" r="7" fill="{accent}" opacity=".25" class="pulse"/>',
        f'<circle cx="44" cy="37" r="3.5" fill="{accent}"/>',
        f'<text x="58" y="41.5" class="mono" font-size="11" font-weight="700" letter-spacing="1.2" fill="{accent}">{e(cfg["status"])}</text>',
        f'<text x="28" y="92" class="sans" font-size="30" font-weight="800" letter-spacing="-.4" fill="{TITLE}">{e(cfg["title"])}</text>',
    ]
    y = 122
    for line in wrap(cfg["pitch"], 70, 2):
        out.append(f'<text x="28" y="{y}" class="sans" font-size="15.5" fill="{MUTED}">{e(line)}</text>')
        y += 23
    y += 10
    for i, item in enumerate(cfg["highlights"]):
        out.append(
            f'<g class="fade" style="animation-delay:{.15 + i * .1:.2f}s">'
            f'<text x="28" y="{y}" class="mono" font-size="13" fill="{accent}">▹</text>'
            f'<text x="46" y="{y}" class="sans" font-size="14.5" fill="{TEXT}">{e(item)}</text></g>'
        )
        y += 24
    chips_svg, chips_bottom = chip_row(cfg["chips"], 28, y + 4, 640)
    out.append(chips_svg)
    h = int(chips_bottom + 50)

    mx = 676
    out.append(f'<rect x="{mx - 18}" y="24" width="1" height="{h - 70}" fill="{STROKE}"/>')
    for i, (label, value, color) in enumerate((
        ("commits", fmt_int(commits), CYAN),
        ("last push", fmt_day(pushed), VIOLET),
        ("primary", (repo.get("primaryLanguage") or {}).get("name", "—"), EMERALD),
    )):
        my = 48 + i * 50
        out.append(
            f'<text x="{mx}" y="{my}" class="mono" font-size="10.5" letter-spacing="1" fill="{DIM}">{e(label.upper())}</text>'
            f'<text x="{mx}" y="{my + 22}" class="mono" font-size="17" font-weight="700" fill="{color}">{e(value)}</text>'
        )
    out.append(lang_bar(langs, 28, h - 30, w - 56))
    out.append(f'<text x="{w - 28}" y="{h - 10}" text-anchor="end" class="mono" font-size="10.5" fill="{DIM}">'
               + e("  ·  ".join(f"{n} {p * 100:.0f}%" for n, p in langs)) + "</text>")
    out[0] = f'<rect x="0" y="22" width="3" height="{h - 44}" rx="1.5" fill="{accent}"/>'
    return svg(w, h, card_frame(w, h, accent) + "".join(out), label=f'{cfg["title"]} — {cfg["pitch"]}')


def render_live(token: str) -> None:
    today = datetime.now(timezone.utc).date()
    include_private = os.environ.get("INCLUDE_PRIVATE", "").lower() == "true"

    user = gql(USER_Q, {"login": LOGIN, "privacy": None if include_private else "PUBLIC"}, token)["user"]
    created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    days = calendar(token, created, today)
    start = today - timedelta(days=26 * 7 - 1)
    weekly = [sum(days.get(start + timedelta(days=wk * 7 + i), 0) for i in range(7)) for wk in range(26)]
    rows = [
        ("contributions · 12 months", fmt_int(sum(v for d, v in days.items() if d > today - timedelta(days=365))), CYAN),
        ("contributions · all time", fmt_int(sum(days.values())), VIOLET),
        # The PR total only includes private repositories when the token can read them.
        ("pull requests" if include_private else "public pull requests",
         fmt_int(user["pullRequests"]["totalCount"]), EMERALD),
        ("public repositories", fmt_int(user["publicRepos"]["totalCount"]), CYAN),
        ("on GitHub", f"{(today - created).days / 365.25:.1f} yrs", VIOLET),
    ]
    write(LIVE / "stats.svg", render_stats(rows, weekly, today.strftime("%d %b %Y")))

    edges = [edge for node in user["repositories"]["nodes"] for edge in node["languages"]["edges"]]
    write(LIVE / "languages.svg", render_languages(top_langs(edges, 6), "all" if include_private else "public"))

    for cfg in FLAGSHIPS:
        repo = gql(REPO_Q, {"owner": LOGIN, "name": cfg["repo"]}, token).get("repository")
        if repo is None:
            print(f"skip {cfg['repo']}: not readable with this token; keeping previous card")
            continue
        write(LIVE / f"project-{cfg['slug']}.svg", render_project(cfg, repo))


def render_static() -> None:
    write(UI / "hero.svg", render_hero())
    for num, title in SECTIONS:
        write(UI / f"section-{num}.svg", render_divider(num, title))
    rows = max(len(items) for *_, items in STACK)
    for slug, title, accent, items in STACK:
        write(UI / f"stack-{slug}.svg", render_stack_panel(title, accent, items, rows))
    write(UI / "btn-portfolio.svg", render_button("jacobelcharar.dev", "globe", CYAN))
    write(UI / "btn-linkedin.svg", render_button("LinkedIn", "linkedin", VIOLET))
    write(UI / "btn-email.svg", render_button("Email", "mail", EMERALD))
    write(UI / "link-case-study.svg", render_link("Case study", CYAN))
    write(UI / "link-repo.svg", render_link("Repository", VIOLET))
    write(UI / "footer.svg", render_footer())


def main() -> int:
    render_static()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN not set; rendered static assets only", file=sys.stderr)
        return 0
    render_live(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
