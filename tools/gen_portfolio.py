#!/usr/bin/env python3
"""Generate the Humanfia org profile from humanfia.ai: the banner (light + dark) and the README links.

Nothing about Humanfia is written down here. Every run reads the live site -- the H mark from
/logo.svg and /logo-dark.svg, the projects and flows from the nav, the tagline from <title>, the
latest posts from /news/feed.rss and /blog/feed.rss -- and lays it out in the constructivist
house style: paper, ink and one red circle, the dot that hops from the "i" of the wordmark to the
H's top-right corner and back. A section the site does not have yet (no flows, no news feed) is
left out rather than faked; only an unreachable home page or logo stops the run, so a bad fetch
never overwrites a good profile.

GitHub shows README images through <img>: no JavaScript and no web fonts, so motion is SMIL and
text is set in system fonts.

    python3 tools/gen_portfolio.py              # both banners and profile/README.md
    THEME=dark python3 tools/gen_portfolio.py   # one banner (light|dark), README untouched
    SITE=http://localhost:4173 python3 tools/gen_portfolio.py
"""

from __future__ import annotations

import html
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

SITE = os.environ.get("SITE", "https://humanfia.ai").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Fixed homes that are not pages of the site.
DOCS = "https://docs.humanfia.ai/humanize/"
HUMANIZE = "https://github.com/humanfia/humanize"
FLOWVERSE = "https://github.com/humanfia/flowverse"
KDA = "https://nvlabs.github.io/kda"

# Brand palette from the shared design brief: ink, paper, constructivist red.
THEMES = {
    "light": {"paper": "#f4efe6", "ink": "#16161a", "red": "#d6331f", "mute": "#6b6660", "rule": "#d9d1c3"},
    "dark": {"paper": "#16161a", "ink": "#ece6da", "red": "#ff5a43", "mute": "#9a948a", "rule": "#33322f"},
}
SANS = "'Helvetica Neue', Helvetica, Arial, 'Segoe UI', sans-serif"
W, H = 1200, 480
T = 10.0           # loop length, seconds
SLOPE = math.tan(math.radians(17))  # the one diagonal everything leans on


# ------------------------------------------------------------------------------------ fetching

def fetch(path: str) -> str | None:
    """The body at SITE+path, or None if the site says it is not there (a section not shipped yet)."""
    url = path if path.startswith("http") else SITE + path
    req = urllib.request.Request(url, headers={"User-Agent": "humanfia-org-profile"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return None
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 * (attempt + 1))
    return None


def need(path: str) -> str:
    body = fetch(path)
    if body is None:
        sys.exit(f"gen_portfolio: could not read {SITE}{path}; leaving the profile as it is")
    return body


def absolute(href: str) -> str:
    return href if href.startswith("http") else SITE + "/" + href.lstrip("/")


# ------------------------------------------------------------------------------------- the nav

@dataclass
class Entry:
    label: str
    href: str = ""
    items: list[tuple[str, str]] = field(default_factory=list)


class NavParser(HTMLParser):
    """Reads VitePress's desktop nav bar: top-level links, and flyout groups with their items."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[Entry] = []
        self.in_nav = self.done = False
        self.divs = 0
        self.group: Entry | None = None
        self.group_at = 0
        self.in_button = False
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "nav" and "VPNavBarMenu" in cls and not self.done:
            self.in_nav = True
        if not self.in_nav:
            return
        if tag == "div":
            if "VPFlyout" in cls and self.group is None:
                self.group, self.group_at = Entry(""), self.divs
            self.divs += 1
        elif tag == "button" and self.group is not None:
            self.in_button = True
        elif tag == "a":
            self.href, self.text = a.get("href") or "", []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_nav:
            return
        if tag == "nav":
            self.in_nav, self.done = False, True
        elif tag == "button":
            self.in_button = False
        elif tag == "a" and self.href is not None:
            label = " ".join("".join(self.text).split())
            if label:
                if self.group is not None:
                    self.group.items.append((label, self.href))
                else:
                    self.entries.append(Entry(label, self.href))
            self.href = None
        elif tag == "div":
            self.divs -= 1
            if self.group is not None and self.divs == self.group_at:
                self.entries.append(self.group)
                self.group = None

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)
        elif self.in_button and self.group is not None:
            self.group.label = " ".join((self.group.label + " " + data).split())


def parse_nav(page: str) -> list[Entry]:
    p = NavParser()
    p.feed(page)
    return p.entries


def find(nav: list[Entry], label: str) -> Entry | None:
    """A nav entry by label, top level first, then inside the flyouts."""
    for e in nav:
        if e.label.lower() == label.lower():
            return e
    for e in nav:
        for lab, href in e.items:
            if lab.lower() == label.lower():
                return Entry(lab, href)
    return None


def meta(page: str, name: str) -> str:
    m = re.search(rf'<meta[^>]+(?:name|property)="{name}"[^>]+content="([^"]*)"', page)
    return html.unescape(m.group(1)) if m else ""


def blurb(name: str, desc: str) -> str:
    """The first clause of a page description, with the leading "<name> — " / "<name> is" dropped."""
    s = desc.strip()
    for head in (name, name.split(":")[0], name.split(" ")[0]):
        for sep in (" — ", " - ", " is ", ": "):
            if s.startswith(head + sep):
                s = s[len(head + sep):]
                break
    s = re.split(r"(?<=[a-z0-9)])\.\s| — |, and |; ", s)[0].rstrip(".")
    return s[:1].upper() + s[1:]


@dataclass
class Item:
    title: str
    sub: str
    href: str


def projects(nav: list[Entry]) -> list[Item]:
    group = find(nav, "Projects")
    out = []
    for label, href in group.items if group else []:
        name, _, tail = label.partition(":")
        sub = tail.strip()
        if not sub:
            page = fetch(href)
            sub = blurb(name, meta(page, "description")) if page else ""
        out.append(Item(name.strip(), sub, absolute(href)))
    return out


def flows(nav: list[Entry]) -> tuple[list[Item], str | None]:
    """The flows the site lists (nav flyout, else the /flows/ index) and the index URL if it exists."""
    index = fetch("/flows/")
    group = find(nav, "Flows")
    pairs = list(group.items) if group else []
    if not pairs and index:
        pairs = [(html.unescape(re.sub("<[^>]+>", "", t)).strip(), h) for h, t in
                 re.findall(rf'<a[^>]+href="((?:{re.escape(SITE)})?/flows/[a-z0-9-]+/?)"[^>]*>(.*?)</a>', index, re.DOTALL)]
    seen, out = set(), []
    for lab, href in pairs:
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if slug in ("flows", "") or slug in seen or not lab or lab.lower().startswith(("all ", "overview")):
            continue
        seen.add(slug)
        out.append(Item(lab, "", absolute(href)))
    url = absolute("/flows/") if index else (absolute(group.href) if group and group.href else None)
    return out, url


@dataclass
class Post:
    kind: str
    title: str
    href: str
    when: float
    date: str


def feed(path: str, kind: str) -> list[Post]:
    body = fetch(path)
    if not body:
        return []
    try:
        channel = ET.fromstring(body).find("channel")
    except ET.ParseError:
        return []
    posts = []
    for it in channel.findall("item") if channel is not None else []:
        try:
            d = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        posts.append(Post(kind, (it.findtext("title") or "").strip(), it.findtext("link") or "",
                          d.timestamp(), d.strftime("%b %-d, %Y")))
    return posts


def latest(n: int = 4) -> list[Post]:
    posts = feed("/news/feed.rss", "NEWS") + feed("/blog/feed.rss", "BLOG")
    unique = {p.href: p for p in posts}.values()
    return sorted(unique, key=lambda p: (-p.when, p.title))[:n]


# ------------------------------------------------------------------------------------- the logo

def _matrix(transform: str) -> tuple[float, ...]:
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for op, args in re.findall(r"(\w+)\s*\(([^)]*)\)", transform or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if op == "matrix":
            n = tuple(v)
        elif op == "translate":
            n = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif op == "scale":
            n = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif op == "rotate":
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            n = (c, s, -s, c, 0, 0)
            if len(v) == 3:
                n = _mul(_mul((1, 0, 0, 1, v[1], v[2]), n), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            continue
        m = _mul(m, n)
    return m


def _mul(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3],
            a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


@dataclass
class Logo:
    viewbox: tuple[float, float, float, float]
    body: str                                  # the mark's elements, minus the dot
    dot: tuple[float, float, float] | None     # cx, cy, r in viewBox units
    dot_fill: str | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_logo(svg: str) -> Logo:
    root = ET.fromstring(svg)
    vb = tuple(float(x) for x in re.split(r"[\s,]+", root.get("viewBox", "0 0 51 57").strip()))
    parents = {c: p for p in root.iter() for c in p}
    for el in list(root.iter()):
        if _local(el.tag) in ("title", "desc", "script", "metadata"):
            parents[el].remove(el)
    circles = [el for el in root.iter() if _local(el.tag) == "circle"]
    named = [el for el in root.iter() if "dot" in f"{el.get('id', '')} {el.get('class', '')}".lower()]
    target = (named or circles or [None])[-1]
    dot = fill = None
    if target is not None:
        c = target if _local(target.tag) == "circle" else next(
            (e for e in target.iter() if _local(e.tag) == "circle"), None)
        if c is not None:
            m, node = _matrix(c.get("transform", "")), c
            while node in parents:
                node = parents[node]
                m = _mul(_matrix(node.get("transform", "")), m)
            cx, cy, r = (float(c.get(k, "0")) for k in ("cx", "cy", "r"))
            dot = (m[0] * cx + m[2] * cy + m[4], m[1] * cx + m[3] * cy + m[5], r * math.sqrt(abs(m[0] * m[3] - m[1] * m[2])))
            fill = c.get("fill") or target.get("fill")
            parents[target].remove(target)
    body = "".join(ET.tostring(el, encoding="unicode") for el in root)
    body = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", body)
    body = re.sub(r'\bid="([^"]+)"', r'id="logo-\1"', body)
    body = re.sub(r'(url\(#|href="#)', r"\1logo-", body)
    return Logo(vb, body, dot, fill if fill and fill.startswith("#") else None)


# ------------------------------------------------------------------------------------ rendering

_NARROW, _WIDE = set("ijlrtfI.,:;'|!() "), set("mwMW@")


def width(s: str, size: float, bold: bool = False) -> float:
    k = 0.04 if bold else 0.0
    return size * sum((0.30 if c in _NARROW else 0.86 if c in _WIDE else 0.68 if c.isupper() or c.isdigit()
                       else 0.56) + k for c in s)


def fit(s: str, size: float, room: float, bold: bool = False) -> str:
    if width(s, size, bold) <= room:
        return s
    while s and width(s + "…", size, bold) > room:
        s = s[:-1]
    return s.rstrip(" ,:;—-") + "…"


def wrap(s: str, size: float, room: float, lines: int, bold: bool = False) -> list[str]:
    out, words = [], s.split()
    while words and len(out) < lines:
        line = words.pop(0)
        while words and width(line + " " + words[0], size, bold) <= room:
            line += " " + words.pop(0)
        out.append(line)
    if words:
        out[-1] = fit(out[-1] + " " + " ".join(words), size, room, bold)
    return [fit(x, size, room, bold) for x in out]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def text(x: float, y: float, s: str, cls: str, extra: str = "") -> str:
    return f'<text x="{n(x)}" y="{n(y)}" class="{cls}"{extra}>{esc(s)}</text>'


def intro(i: int, dx: float = 40) -> str:
    """Slide in once along the diagonal, staggered: the composition assembling itself. The static
    value is the end state, so a renderer without SMIL still shows everything."""
    b = 0.15 + 0.12 * i
    d, k = b + 0.7, n(b / (b + 0.7))
    return (f'<animateTransform attributeName="transform" type="translate" dur="{n(d)}s" fill="freeze" '
            f'values="{n(dx)} {n(-dx * SLOPE)};{n(dx)} {n(-dx * SLOPE)};0 0" keyTimes="0;{k};1" '
            f'calcMode="spline" keySplines="0 0 1 1;0.2 0.8 0.2 1"/>'
            f'<animate attributeName="opacity" dur="{n(d)}s" fill="freeze" values="0;0;1" keyTimes="0;{k};1"/>')


# Advance widths of the wordmark's letters (Helvetica Bold, per em). Each letter is placed on its own
# at a known x, so the dotless i -- and the dot that leaves it -- line up in whatever font renders.
WORD = [("h", .611), ("u", .611), ("m", .889), ("a", .556), ("n", .611), ("f", .333), ("ı", .278), ("a", .556)]


def wordmark(x0: float, base: float, size: float, track: float = -0.02) -> tuple[str, tuple[float, float, float]]:
    parts, x = [], x0
    dot = (0.0, 0.0, 0.0)
    for ch, adv in WORD:
        w = (adv + track) * size
        parts.append(text(x + w / 2, base, ch, "wm"))
        if ch == "ı":
            dot = (x + w / 2, base - 0.70 * size, 0.085 * size)
        x += w
    return "".join(parts), dot


def hop(start: tuple[float, float, float], end: tuple[float, float, float]) -> str:
    """The red dot: rests on the i, arcs to the H's top-right, lands with a squash, and comes back."""
    (x0, y0, r0), (x1, y1, r1) = start, end
    peak = min(y0, y1) - 36
    # Quadratic arcs whose control point sits above both ends: a ballistic path out and back.
    cx = (x0 + x1) / 2
    path = (f"M{n(x0)},{n(y0)} Q{n(cx)},{n(2 * peak - (y0 + y1) / 2)} {n(x1)},{n(y1)} "
            f"Q{n(cx)},{n(2 * peak - (y0 + y1) / 2)} {n(x0)},{n(y0)}")
    # Times (s): rest on i, fly out, land, rest on H, fly back, land, rest.
    t = [0, 1.6, 2.5, 6.4, 7.3, T]
    kt = ";".join(n(v / T) for v in t)
    ease = "0 0 1 1;0.35 0 0.65 1;0 0 1 1;0.35 0 0.65 1;0 0 1 1"
    motion = (f'<animateMotion dur="{n(T)}s" repeatCount="indefinite" path="{path}" keyPoints="0;0;0.5;0.5;1;1" '
              f'keyTimes="{kt}" calcMode="spline" keySplines="{ease}"/>')

    def radius(attr: str, squash: float) -> str:
        # grow/shrink in flight, then a short squash on landing and a small overshoot back to round.
        pts = [(0, r0), (1.6, r0), (2.5, r1), (2.6, r1 * squash), (2.75, r1 * (2 - squash) ** 0.5), (2.9, r1),
               (6.4, r1), (7.3, r0), (7.4, r0 * squash), (7.55, r0 * (2 - squash) ** 0.5), (7.7, r0), (T, r0)]
        return (f'<animate attributeName="{attr}" dur="{n(T)}s" repeatCount="indefinite" '
                f'values="{";".join(n(v) for _, v in pts)}" keyTimes="{";".join(n(a / T) for a, _ in pts)}"/>')

    return (f'<g>{motion}<ellipse cx="0" cy="0" rx="{n(r0)}" ry="{n(r0)}" class="dot">'
            f'{radius("rx", 1.3)}{radius("ry", 0.72)}</ellipse></g>')


def column(x: float, y: float, w: float, label: str, rows: list[str], i: int, count: str = "") -> str:
    head = (f'<rect x="{n(x)}" y="{n(y - 11)}" width="11" height="11" class="red"/>'
            + text(x + 19, y, label, "lab")
            + (text(x + w, y, count, "cnt", ' text-anchor="end"') if count else "")
            + f'<rect x="{n(x)}" y="{n(y + 10)}" width="{n(w)}" height="3" class="ink"/>')
    return f'<g>{intro(i)}{head}{"".join(rows)}</g>'


def banner(theme: str, logo: Logo, tagline: str, proj: list[Item], flow: list[Item], posts: list[Post]) -> str:
    c = THEMES[theme]
    # The H, large, on the left; the wordmark under it; the tagline under that.
    lx, ly, lh = 64, 54, 236
    vx, vy, vw, vh = logo.viewbox
    s = lh / vh
    lw = vw * s
    marks, idot = wordmark(lx, 368, 66)
    if logo.dot:
        slot = (lx + (logo.dot[0] - vx) * s, ly + (logo.dot[1] - vy) * s, logo.dot[2] * s)
    else:  # an H without a detachable dot: the red dot perches just above its top-right corner
        slot = (lx + lw * 0.86, ly - 22, 15)
    red = logo.dot_fill or c["red"]

    # The right-hand side: one column per section the site has, top edges stepping up the diagonal.
    x0, x1, gap = 452, W - 48, 32
    weights = [0.95 if proj else 0, 1.0 if flow else 0, 1.3 if posts else 0]
    unit = (x1 - x0 - gap * (sum(1 for v in weights if v) - 1)) / max(sum(weights), 1)
    xs, x = [], x0
    for wgt in weights:
        xs.append((x, wgt * unit))
        x += wgt * unit + (gap if wgt else 0)

    blocks, k = [], 0
    if proj:
        cx, cw = xs[0]
        top = 150 - k * 22
        rows = []
        for j, p in enumerate(proj[:6]):
            y = top + 44 + j * 46
            rows.append(text(cx, y, fit(p.title, 17, cw, True), "t") + text(cx, y + 18, fit(p.sub, 13, cw), "s"))
        blocks.append(column(cx, top, cw, "PROJECTS", rows, k, str(len(proj))))
        k += 1
    if flow:
        cx, cw = xs[1]
        top = 150 - k * 22
        rows = [text(cx, top + 108, str(len(flow)), "big"), text(cx + width(str(len(flow)), 96, True) + 10,
                top + 108, "flows", "s")]
        for j, f in enumerate(flow[:5]):
            y = top + 148 + j * 26
            tick = 12 + 6 * (j % 3)   # little red bars on the diagonal, of varying length
            rows.append(f'<polygon points="{n(cx)},{n(y - 3)} {n(cx + tick)},{n(y - 3 - tick * SLOPE)} '
                        f'{n(cx + tick)},{n(y - 7 - tick * SLOPE)} {n(cx)},{n(y - 7)}" class="red"/>'
                        + text(cx + 30, y, fit(f.title, 15, cw - 30, True), "t2"))
        blocks.append(column(cx, top, cw, "FLOWS", rows, k))
        k += 1
    if posts:
        cx, cw = xs[2]
        top = 150 - k * 22
        rows, y = [], top + 40
        for j, p in enumerate(posts):
            lines = wrap(p.title, 17, cw, 2, True)
            rows.append(text(cx, y, f"{p.kind} · {p.date.upper()}", "meta")
                        + "".join(text(cx, y + 21 + 20 * i, ln, "t") for i, ln in enumerate(lines)))
            span = 21 + 20 * len(lines) + 10
            # A red bar marks one post at a time, walking down the list over the loop.
            on, off = j / len(posts), (j + 1) / len(posts)
            rows.append(f'<rect x="{n(cx - 14)}" y="{n(y - 10)}" width="4" height="{n(span - 12)}" class="red" opacity="0">'
                        f'<animate attributeName="opacity" dur="{n(T)}s" repeatCount="indefinite" calcMode="discrete" '
                        f'values="0;1;0" keyTimes="0;{n(on)};{n(off)}"/></rect>')
            y += span
        blocks.append(column(cx, top, cw, "LATEST", rows, k))

    # Constructivist ground: a red wedge cutting in from the bottom-right on the diagonal, carrying the
    # address; an ink bar the H stands against; a hairline under the mark.
    rise = 100
    run = rise / SLOPE
    angle = -math.degrees(math.atan(SLOPE))
    url_x = W - 24  # the address runs parallel to the hypotenuse, just inside it
    url_y = H - (url_x - (W - run)) * SLOPE + 24
    ground = (
        f'<g>{intro(k + 1, 90)}<polygon points="{n(W)},{n(H)} {n(W)},{n(H - rise)} {n(W - run)},{n(H)}" class="red"/>'
        f'<text transform="translate({n(url_x)} {n(url_y)}) rotate({n(angle)})" class="url" text-anchor="end">'
        f'{esc(SITE.split("//", 1)[-1].upper())}</text></g>'
        f'<rect x="{n(lx + lw + 26)}" y="{n(ly)}" width="6" height="{n(lh)}" class="ink"/>'
        f'<rect x="{n(lx)}" y="{n(ly + lh + 14)}" width="{n(lw + 32)}" height="2" class="rule"/>'
    )
    css = (f".bg{{fill:{c['paper']}}}.ink{{fill:{c['ink']}}}.red,.dot{{fill:{red}}}.rule{{fill:{c['rule']}}}"
           f"text{{font-family:{SANS};fill:{c['ink']}}}"
           f".wm{{font-size:66px;font-weight:800;text-anchor:middle}}"
           f".tag{{font-size:17px;fill:{c['mute']}}}.lab{{font-size:13px;font-weight:800;letter-spacing:.18em}}"
           f".cnt{{font-size:13px;font-weight:700;fill:{c['mute']}}}"
           f".t{{font-size:17px;font-weight:700}}.t2{{font-size:15px;font-weight:700}}"
           f".s{{font-size:13px;fill:{c['mute']}}}.meta{{font-size:11px;font-weight:700;letter-spacing:.12em;fill:{red}}}"
           f".url{{font-size:15px;font-weight:800;letter-spacing:.24em;fill:{c['paper']}}}"
           f".big{{font-size:96px;font-weight:800;letter-spacing:-.04em}}")
    title = f"Humanfia — {tagline}" if tagline else "Humanfia"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-labelledby="t"><title id="t">{esc(title)}</title><style>{css}</style>'
        f'<rect width="{W}" height="{H}" class="bg"/>{ground}'
        f'<svg x="{n(lx)}" y="{n(ly)}" width="{n(lw)}" height="{n(lh)}" viewBox="{" ".join(n(v) for v in logo.viewbox)}" '
        f'overflow="visible">{logo.body}</svg>'
        f'{marks}{text(lx, 400, fit(tagline, 17, x0 - lx - 30), "tag")}'
        f'{"".join(blocks)}{hop(idot, slot)}</svg>\n'
    )


# --------------------------------------------------------------------------------------- README

BEGIN, END = "<!-- BEGIN gen_portfolio.py -->", "<!-- END gen_portfolio.py -->"


def links(nav: list[Entry], flows_url: str | None) -> list[tuple[str, str]]:
    """humanfia.ai · Docs · Humanize · Flows · Flowverse · KDA · Blog · News · About, as far as they exist."""
    def nav_link(label: str) -> list[tuple[str, str]]:
        e = find(nav, label)
        href = e.href if e and e.href else (e.items[0][1] if e and e.items else "")
        return [(label, absolute(href))] if href else []

    docs = find(nav, "Docs")
    return ([("humanfia.ai", SITE), ("Docs", absolute(docs.href) if docs and docs.href else DOCS), ("Humanize", HUMANIZE)]
            + ([("Flows", flows_url)] if flows_url else [])
            + [("Flowverse", FLOWVERSE), ("KDA", KDA)]
            + nav_link("Blog") + nav_link("News") + nav_link("About"))


def readme(old: str, alt: str, nav_links: list[tuple[str, str]]) -> str:
    sep = " ·\n  "
    joined = sep.join(f'<a href="{esc(h)}">{"<b>" + esc(t) + "</b>" if i == 0 else esc(t)}</a>'
                      for i, (t, h) in enumerate(nav_links))
    block = f"""{BEGIN}
<p align="center">
  <a href="{SITE}">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="./humanfia-portfolio-dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="./humanfia-portfolio-light.svg">
      <img src="./humanfia-portfolio-light.svg" width="100%" alt="{esc(alt)}" />
    </picture>
  </a>
</p>

<p align="center">
  {joined}
</p>
{END}"""
    if BEGIN in old and END in old:
        head, rest = old.split(BEGIN, 1)
        return head + block + rest.split(END, 1)[1]
    return block + "\n"


# ----------------------------------------------------------------------------------------- main

def main() -> None:
    home = need("/")
    nav = parse_nav(home)
    if not nav:
        sys.exit("gen_portfolio: found no nav on the home page; leaving the profile as it is")
    title = re.search(r"<title>([^<]*)</title>", home)
    tagline = html.unescape(title.group(1)).split(" — ", 1)[-1].strip() if title else ""
    proj, (flow, flows_url), posts = projects(nav), flows(nav), latest()

    themes = [os.environ["THEME"]] if os.environ.get("THEME") else ["light", "dark"]
    for theme in themes:
        src = (fetch("/logo-dark.svg") if theme == "dark" else None) or need("/logo.svg")
        out = PROFILE / f"humanfia-portfolio-{theme}.svg"
        out.write_text(banner(theme, parse_logo(src), tagline, proj, flow, posts), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")

    if not os.environ.get("THEME"):
        names = ", ".join(p.title for p in proj)
        alt = f"Humanfia — {tagline}." + (f" {names}." if names else "")
        path = PROFILE / "README.md"
        path.write_text(readme(path.read_text(encoding="utf-8") if path.exists() else "", alt, links(nav, flows_url)),
                        encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
