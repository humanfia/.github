#!/usr/bin/env python3
"""Generate the Humanfia org profile banner from humanfia.ai: a 120-second constructivist explainer.

Nothing about Humanfia is written down here. Every run reads the live sites and lays out what it
finds, chapter by chapter, on one 120 s SMIL clock:

     1  the mark        /logo.svg: the H assembles from three planes, the red dot rolls in and hops
     2  the thesis      the home page's headline and manifesto, and About's bet
     3  the runtime     the Humanize docs' "how it fits together" bands
     4  a turn          the docs' definition of a turn, and the runtime's features from the home page
     5  the flows       the nav's Flows menu
     6  a flow, running the first flow page with exactly two agent roles: a maker and a checker
     7  the projects    the nav's Projects menu, each page's headline stat, the home page's results
     8  the latest      /news/feed.rss and /blog/feed.rss
     9  the people      About's roster, principles and contacts
    10  the address

A chapter whose source the site does not have (a 404 or 410, or markup without the parts it needs)
is dropped and the others share its time. Any other failure -- a 403, a 5xx, a timeout -- stops
the run, so a bad fetch never overwrites a good profile.

The look is constructivist throughout: flat planes, bars, wedges and circles with hard edges, in
paper, ink and one red; one diagonal; heavy sans type set in bands; planes that slide along their
axes, bars that extend, a red circle that rolls and drops, and diagonal wipes between chapters.
GitHub shows README images through <img>, so there is no JavaScript and no web font: motion is
SMIL, type is the system's heaviest sans, and avatars are inlined.

    python3 tools/gen_portfolio.py              # both banners
    THEME=dark python3 tools/gen_portfolio.py   # one banner (light|dark)
    SITE=http://localhost:4173 DOCS=http://localhost:5173/humanize python3 tools/gen_portfolio.py
"""

from __future__ import annotations

import base64
import html
import http.client
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
from typing import Callable, Iterator
from xml.etree import ElementTree as ET

SITE = os.environ.get("SITE", "https://humanfia.ai").rstrip("/")
DOCS = os.environ.get("DOCS", "https://docs.humanfia.ai/humanize").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

THEMES = {  # light: ink and red on paper; dark: paper and red on ink
    "light": {"paper": "#f4efe6", "ink": "#16161a", "red": "#d6331f", "mute": "#5f5a54"},
    "dark": {"paper": "#16161a", "ink": "#ece6da", "red": "#ff5a43", "mute": "#a39d92"},
}
BLOCK = "'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif"  # heavy block type
SANS = "'Helvetica Neue',Helvetica,Arial,'Segoe UI',sans-serif"
W, H = 1000, 560   # shown ~830 px wide on GitHub, so 14 px here is never under 11 px there
T = 120.0          # the loop, seconds
ANGLE = 17.0       # the one diagonal, degrees
SLOPE = math.tan(math.radians(ANGLE))


# ------------------------------------------------------------------------------------ fetching

GONE = (404, 410)  # the only answers that mean "this is not there"


def fetch_bytes(url: str) -> bytes | None:
    """The body at url, or None on 404/410. Any other failure is retried, then stops the run."""
    req = urllib.request.Request(url, headers={"User-Agent": "humanfia-org-profile"})
    why = ""
    for attempt in range(3):
        if attempt:
            time.sleep(2 * attempt)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in GONE:
                return None
            why = f"HTTP {e.code}"
        except (OSError, http.client.HTTPException) as e:  # URLError, timeouts, resets, short reads
            why = f"{type(e).__name__}: {e}"
    sys.exit(f"gen_portfolio: could not read {url} ({why}); leaving the profile as it is")


def fetch(path: str) -> str | None:
    """A page of SITE (or an absolute URL) as text, or None if it is not there."""
    url = absolute(path)
    body = fetch_bytes(url)
    if body is None:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        sys.exit(f"gen_portfolio: {url} is not UTF-8; leaving the profile as it is")


def need(path: str) -> str:
    body = fetch(path)
    if body is None:
        sys.exit(f"gen_portfolio: {absolute(path)} is gone; leaving the profile as it is")
    return body


def absolute(href: str) -> str:
    return href if href.startswith("http") else SITE + "/" + href.lstrip("/")


# ------------------------------------------------------------------------------------- the DOM

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    kids: list[Node | str] = field(default_factory=list)

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def iter(self) -> Iterator[Node]:
        yield self
        for k in self.kids:
            if isinstance(k, Node):
                yield from k.iter()

    def all(self, tag: str | None = None, cls: str | None = None) -> list[Node]:
        return [x for x in self.iter() if x is not self and (tag is None or x.tag == tag)
                and (cls is None or cls in x.classes)]

    def first(self, tag: str | None = None, cls: str | None = None) -> Node | None:
        return next(iter(self.all(tag, cls)), None)

    def text(self, skip: tuple[str, ...] = ()) -> str:
        def walk(node: Node) -> Iterator[str]:
            for k in node.kids:
                if isinstance(k, str):
                    yield k
                elif k.tag not in skip:
                    yield " " if k.tag == "br" else ""
                    yield from walk(k)
        return " ".join("".join(walk(self)).split())


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].kids.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].kids.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag not in ("script", "style"):
            self.stack[-1].kids.append(data)


def dom(page: str) -> Node:
    b = _Builder()
    b.feed(page)
    return b.root


# ------------------------------------------------------------------------------------- the nav

@dataclass
class Menu:
    label: str
    href: str = ""
    groups: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)  # (title, [(label, href)])

    @property
    def items(self) -> list[tuple[str, str]]:
        return [it for _, its in self.groups for it in its]


def parse_nav(root: Node) -> list[Menu]:
    """VitePress's desktop nav bar: top-level links, and flyouts with their (titled) groups."""
    nav = next((x for x in root.all("nav") if "VPNavBarMenu" in x.classes), None)
    out: list[Menu] = []
    for x in nav.iter() if nav else []:
        if "VPFlyout" in x.classes:
            button = x.first("button")
            menu = Menu(button.text() if button else "")
            for grp in x.all(cls="VPMenuGroup") or [x]:
                title = grp.first(cls="title") if grp is not x else None
                links = [(a.text(), a.attrs.get("href", "")) for a in grp.all("a") if a.text()]
                menu.groups.append((title.text() if title else "", links))
            out.append(menu)
        elif x.tag == "a" and "VPNavBarMenuLink" in x.classes:
            out.append(Menu(x.text(), x.attrs.get("href", "")))
    return out


def find(nav: list[Menu], label: str) -> Menu | None:
    return next((m for m in nav if m.label.lower() == label.lower()), None)


# ----------------------------------------------------------------------------------- the facts

@dataclass
class Logo:
    viewbox: tuple[float, float, float, float]
    body: str                                  # the mark's elements, minus the dot, uncoloured
    dot: tuple[float, float, float] | None     # cx, cy, r in viewBox units


@dataclass
class Band:
    title: str
    about: str
    chips: list[tuple[str, str]]               # (name, small note)
    down: str = ""                             # what passes from this band to the next


@dataclass
class Project:
    name: str
    sub: str
    stat: str = ""
    stat_says: str = ""
    lede: str = ""


@dataclass
class Post:
    kind: str
    title: str
    href: str
    when: float
    date: str
    by: str = ""


@dataclass
class Person:
    name: str
    handle: str
    face: str = ""                             # a data: URI, or "" for initials


@dataclass
class Loop:
    name: str
    says: str
    roles: list[tuple[str, str]]               # (role, what it does)


@dataclass
class Facts:
    logo: Logo
    kicker: str = ""
    headline: str = ""
    manifesto: list[str] = field(default_factory=list)
    bet: str = ""
    bands: list[Band] = field(default_factory=list)
    features: list[tuple[str, str]] = field(default_factory=list)
    flows: list[tuple[str, list[str]]] = field(default_factory=list)
    loop: Loop | None = None
    projects: list[Project] = field(default_factory=list)
    results: list[tuple[str, str]] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    people_intro: str = ""
    principles: list[str] = field(default_factory=list)
    contact: list[tuple[str, str]] = field(default_factory=list)  # (what for, where)


def sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", s) if x.strip()]


def home_facts(f: Facts, root: Node) -> None:
    hero = root.first("h1")
    f.headline = hero.text() if hero else ""
    if not f.headline:
        title = root.first("title")
        f.headline = title.text().split(" — ", 1)[-1] if title else ""
    hero_box = next((s for s in root.all("section") if hero is not None and hero in s.iter()), None)
    kick = hero_box.first(cls="h-kicker") if hero_box else None
    f.kicker = kick.text() if kick else ""
    manifesto = root.first(cls="h-manifesto-text")
    f.manifesto = sentences(manifesto.text()) if manifesto else []
    f.features = [(h.text(), p.text()) for feat in root.all(cls="h-feature")
                  for h, p in [(feat.first("h3"), feat.first("p"))] if h and p]
    f.results = [(lab.text(), num.text()) for tile in root.all(cls="h-tile")
                 for lab, num in [(tile.first(cls="h-tile-label"), tile.first(cls="h-tile-num"))] if lab and num]


def docs_facts(f: Facts, root: Node) -> None:
    """The Humanize docs' "how it fits together": bands of chips, and what passes between them."""
    arch = root.first(cls="arch")
    for el in arch.iter() if arch else []:
        if el.tag == "section" and "band" in el.classes:
            h, p = el.first("h3"), el.first("p")
            chips = [(li.text(skip=("small",)), small.text() if small else "")
                     for li in el.all("li") for small in [li.first("small")]]
            f.bands.append(Band(h.text() if h else "", p.text() if p else "", chips))
        elif el.tag == "p" and "down" in el.classes and f.bands:
            f.bands[-1].down = el.text()


def flow_facts(f: Facts, nav: list[Menu]) -> None:
    menu = find(nav, "Flows")
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    if menu is not None:
        groups = [(t, [(lab, h) for lab, h in its if h.rstrip("/").rsplit("/", 1)[-1] not in ("", "flows")])
                  for t, its in menu.groups]
    else:
        index = fetch("/flows/")
        if index:
            links = [(a.text(), a.attrs.get("href", "")) for a in dom(index).all("a")
                     if re.fullmatch(r"(?:https?://[^/]+)?/flows/[a-z0-9-]+/?", a.attrs.get("href", ""))]
            groups = [("", list(dict.fromkeys(links)))]
    groups = [(t, its) for t, its in groups if its]
    f.flows = [(t, [lab for lab, _ in its]) for t, its in groups]
    # The loop to run: a maker and a checker -- the first flow in a group that says so, whose page
    # names exactly two agent roles.
    for _, its in [gr for gr in groups if re.search(r"check|review", gr[0], re.I)]:
        for lab, href in its:
            page = fetch(href)
            loop = parse_loop(lab, dom(page)) if page else None
            if loop:
                f.loop = loop
                return


def parse_loop(name: str, root: Node) -> Loop | None:
    main = root.first("main") or root
    for table in main.all("table"):
        head = [th.text().lower() for th in table.all("th")]
        if not head or head[0] != "role":
            continue
        roles = [(cells[0], cells[-1]) for tr in table.all("tr") for cells in [[td.text() for td in tr.all("td")]]
                 if len(cells) >= 2 and cells[1].lower().startswith("agent")]
        if len(roles) == 2:
            lede = next((p.text() for p in main.all("p") if p.text()), "")
            return Loop(name, sentences(lede)[0] if lede else "", roles)
    return None


def project_facts(f: Facts, nav: list[Menu]) -> None:
    menu = find(nav, "Projects")
    for label, href in menu.items if menu else []:
        name, _, tail = label.partition(":")
        p = Project(name.strip(), tail.strip())
        page = fetch(href)
        if page:
            root = dom(page)
            strip = root.first(cls="stat-strip")
            first = strip.first("div") if strip else None
            b, span = (first.first("b"), first.first("span")) if first else (None, None)
            p.stat, p.stat_says = (b.text() if b else ""), (span.text() if span else "")
            main = root.first("main") or root
            lede = main.first(cls="lede") or next((x for x in main.all("p") if x.text()), None)
            first = sentences(lede.text())[0].rstrip(".") if lede else ""
            p.sub = p.sub or first
            p.lede = first if first != p.sub else ""
        f.projects.append(p)


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
        by = it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or ""
        posts.append(Post(kind, (it.findtext("title") or "").strip(), it.findtext("link") or "",
                          d.timestamp(), f"{d:%b} {d.day}, {d.year}", by.strip()))
    return posts


def latest(n: int = 5) -> list[Post]:
    posts = feed("/news/feed.rss", "NEWS") + feed("/blog/feed.rss", "BLOG")
    unique = {p.href: p for p in posts}.values()
    return sorted(unique, key=lambda p: (-p.when, p.title))[:n]


def people_facts(f: Facts, nav: list[Menu]) -> None:
    """The roster on About (and on Team, while the site still has one), its principles and contacts."""
    seen: dict[str, Person] = {}
    for href in [m.href for m in nav if m.label.lower() in ("about", "team") and m.href]:
        page = fetch(href)
        if not page:
            continue
        root = dom(page)
        for card in root.all():
            if not {"person", "founder"} & set(card.classes):
                continue
            gh = next((a.attrs["href"] for a in card.all("a")
                       if re.fullmatch(r"https://github\.com/[\w-]+/?", a.attrs.get("href", ""))), "")
            handle = gh.rstrip("/").rsplit("/", 1)[-1]
            named = card.first(cls="person-name") or card.first("h3")
            name = named.text(skip=("span", "a")) if named else ""
            face = card.first("img")
            if name and handle and handle not in seen:
                seen[handle] = Person(name, handle, face.attrs.get("src", "") if face else "")
        lede = root.first(cls="lede")
        f.people_intro = f.people_intro or (lede.text() if lede else "")
        principles = root.first(cls="principles")
        f.principles = f.principles or [b.text() for li in (principles.all("li") if principles else [])
                                        for b in [li.first("b")] if b]
        contact = root.first(cls="contact")
        f.contact = f.contact or [(b.text(), absolute(a.attrs.get("href", "")).split("//", 1)[-1].rstrip("/"))
                                  for a in (contact.all("a") if contact else []) for b in [a.first("b")] if b]
        f.bet = f.bet or next((s for p in (root.first("main") or root).all("p") for s in sentences(p.text())
                               if re.search(r"\bloop is what lasts\b", s)), "")
    f.people = list(seen.values())
    for p in f.people:
        p.face = avatar(p.face)


def avatar(src: str) -> str:
    """A small copy of a GitHub avatar, inlined, since an SVG shown through <img> loads nothing."""
    if not src.startswith("https://avatars.githubusercontent.com/"):
        return ""
    url = re.sub(r"([?&])s=\d+", r"\1s=48", src) if "s=" in src else src + ("&" if "?" in src else "?") + "s=48"
    body = fetch_bytes(url)
    if not body:
        return ""
    mime = "image/png" if body[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(body).decode()}"


def gather() -> Facts:
    logo = parse_logo(need("/logo.svg"))
    home = dom(need("/"))
    nav = parse_nav(home)
    if not nav:
        sys.exit("gen_portfolio: found no nav on the home page; leaving the profile as it is")
    f = Facts(logo)
    home_facts(f, home)
    docs = fetch(DOCS + "/")
    if docs:
        docs_facts(f, dom(docs))
    flow_facts(f, nav)
    project_facts(f, nav)
    f.posts = latest()
    people_facts(f, nav)
    return f


# ------------------------------------------------------------------------------------- the logo

def _matrix(transform: str) -> tuple[float, ...]:
    m: tuple[float, ...] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for op, args in re.findall(r"(\w+)\s*\(([^)]*)\)", transform or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if op == "matrix":
            k: tuple[float, ...] = tuple(v)
        elif op == "translate":
            k = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif op == "scale":
            k = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif op == "rotate":
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            k = (c, s, -s, c, 0, 0)
            if len(v) == 3:
                k = _mul(_mul((1, 0, 0, 1, v[1], v[2]), k), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            continue
        m = _mul(m, k)
    return m


def _mul(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3],
            a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_logo(svg: str) -> Logo:
    root = ET.fromstring(svg)
    # Keep only SVG elements and plain or xlink attributes: editor namespaces (inkscape:, sodipodi:)
    # would otherwise come out under prefixes the banner never declares.
    ours = ("{" + SVG_NS + "}", "{" + XLINK_NS + "}")
    for el in root.iter():
        for k in [k for k in el.attrib if k.startswith("{") and not k.startswith(ours)]:
            del el.attrib[k]
    vb = tuple(float(x) for x in re.split(r"[\s,]+", root.get("viewBox", "0 0 96 108").strip()))
    parents = {c: p for p in root.iter() for c in p}
    for el in list(root.iter()):
        foreign = el.tag.startswith("{") and not el.tag.startswith("{" + SVG_NS + "}")
        if el in parents and (foreign or _local(el.tag) in ("title", "desc", "script", "metadata", "style")):
            parents[el].remove(el)
    circles = [el for el in root.iter() if _local(el.tag) == "circle"]
    named = [el for el in root.iter() if "dot" in f"{el.get('id', '')} {el.get('class', '')}".lower()]
    target = (named or circles or [None])[-1]
    dot = None
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
            parents[target].remove(target)
    body = "".join(ET.tostring(el, encoding="unicode") for el in root)
    body = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", body)
    body = re.sub(r'\bid="([^"]+)"', r'id="logo-\1"', body)
    body = re.sub(r'(url\(#|href="#)', r"\1logo-", body)
    body = re.sub(r'\s(?:fill|class)="[^"]*"', "", body)  # the banner inks the mark for its theme
    return Logo(vb, body, dot)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------- type & time

_NARROW, _WIDE = set("ijlrtfI.,:;'|!()· "), set("mwMW@")


def width(s: str, size: float, heavy: bool = False) -> float:
    """A conservative advance width for the system sans (heavy: Arial Black / Helvetica Bold)."""
    k = 1.2 if heavy else 1.0
    return k * size * sum(0.30 if c in _NARROW else 0.88 if c in _WIDE else 0.70 if c.isupper() or c.isdigit()
                          else 0.56 for c in s)


def fit(s: str, size: float, room: float, heavy: bool = False) -> str:
    if width(s, size, heavy) <= room:
        return s
    while s and width(s + "…", size, heavy) > room:
        s = s[:-1]
    return s.rstrip(" ,:;—-") + "…"


def wrap(s: str, size: float, room: float, lines: int, heavy: bool = False) -> list[str]:
    out, words = [], s.split()
    while words and len(out) < lines:
        line = words.pop(0)
        while words and width(line + " " + words[0], size, heavy) <= room:
            line += " " + words.pop(0)
        out.append(line)
    if words:
        out[-1] = out[-1] + " " + " ".join(words)
    return [fit(x, size, room, heavy) for x in out]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def text(x: float, y: float, s: str, cls: str, extra: str = "") -> str:
    return f'<text x="{n(x)}" y="{n(y)}" class="{cls}"{extra}>{esc(s)}</text>'


def _keys(pts: list[tuple[float, str]]) -> tuple[str, str]:
    pts = sorted(((min(max(t, 0.0), T), v) for t, v in pts), key=lambda p: p[0])
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < T:
        pts.append((T, pts[-1][1]))
    return ";".join(v for _, v in pts), ";".join(f"{t / T:.4f}".rstrip("0").rstrip(".") for t, _ in pts)


def anim(attr: str, pts: list[tuple[float, float]] | list[tuple[float, str]], discrete: bool = False) -> str:
    """One attribute on the one clock: (seconds, value) keyframes, linear (or discrete) between."""
    values, times = _keys([(t, v if isinstance(v, str) else n(v)) for t, v in pts])
    mode = ' calcMode="discrete"' if discrete else ""
    return (f'<animate attributeName="{attr}" dur="{n(T)}s" repeatCount="indefinite"{mode} '
            f'values="{values}" keyTimes="{times}"/>')


def move(pts: list[tuple[float, float, float]]) -> str:
    values, times = _keys([(t, f"{n(x)} {n(y)}") for t, x, y in pts])
    return (f'<animateTransform attributeName="transform" type="translate" dur="{n(T)}s" '
            f'repeatCount="indefinite" values="{values}" keyTimes="{times}"/>')


def on(t0: float, t1: float) -> str:
    """Shown from t0 to t1, hard-switched: the wipe covers the cut."""
    if t0 <= 0:
        return anim("opacity", [(0, 1), (t1, 0)], discrete=True)
    return anim("opacity", [(0, 0), (t0, 1), (t1, 0)], discrete=True)


def enter(t: float, dx: float, dy: float, d: float = 0.5) -> str:
    """Slide in along an axis and lock: a plane arriving, mechanically."""
    return move([(0, dx, dy), (t, dx, dy), (t + d, 0, 0)])


def appear(t: float, d: float = 0.2) -> str:
    return anim("opacity", [(0, 0), (t, 0), (t + d, 1)])


def extend(attr: str, t: float, to: float, d: float = 0.6) -> str:
    """A bar extending from nothing to its length."""
    return anim(attr, [(0, 0), (t, 0), (t + d, to)])


def g(content: str, *anims: str) -> str:
    return f"<g>{''.join(anims)}{content}</g>"


def slab(x: float, y: float, s: str, size: float, cls: str, fill: str, pad: float = 12, angle: float = 0.0) -> str:
    """Heavy type reversed out of a bar: the poster's basic unit."""
    w, h = width(s, size, True) + 2 * pad, size * 1.4
    rot = f' transform="rotate({n(-angle)} {n(x)} {n(y)})"' if angle else ""
    return (f'<g{rot}><rect x="{n(x)}" y="{n(y - h * 0.74)}" width="{n(w)}" height="{n(h)}" class="{fill}"/>'
            f'{text(x + pad, y, s, cls)}</g>')


def kicker(x: float, y: float, num: int, label: str) -> str:
    return (f'<rect x="{n(x)}" y="{n(y - 13)}" width="14" height="14" class="red"/>'
            + text(x + 24, y, fit(f"{num:02d} · {label.upper()}", 15, 600), "kick"))


# ------------------------------------------------------------------------------------ chapters

Draw = Callable[[float, float], str]


@dataclass
class Scene:
    kicker: str
    seconds: float
    draw: Draw


# The wordmark is built, not typeset: bars and arcs of one stroke on an x-height of 54 units, so it
# is the same on every machine and the dot over the i sits exactly where the geometry says.
S, XH, ASC = 13.0, 54.0, 80.0
_C, _H = XH - S / 2, S / 2


def _glyphs() -> list[tuple[str, float]]:
    def arch(x0: float, x1: float) -> str:  # n's shoulder, from the left stem over to the right
        r = (x1 - x0) / 2
        return f"M{n(x0)} {n(-_C + r)}A{n(r)} {n(r)} 0 0 1 {n(x1)} {n(-_C + r)}V0"
    h0, h1 = _H, 40 - _H
    ro = XH / 2 - _H
    a = (f"M{n(XH / 2 - ro)} {n(-XH / 2)}A{n(ro)} {n(ro)} 0 1 1 {n(XH / 2 + ro)} {n(-XH / 2)}"
         f"A{n(ro)} {n(ro)} 0 1 1 {n(XH / 2 - ro)} {n(-XH / 2)}M{n(XH / 2 + ro)} {n(-XH)}V0")
    r = (h1 - h0) / 2
    return [
        (f"M{n(h0)} 0V{n(-ASC)}" + arch(h0, h1), 40),                                             # h
        (f"M{n(h0)} {n(-XH)}V{n(-_H - r)}A{n(r)} {n(r)} 0 0 0 {n(h1)} {n(-_H - r)}M{n(h1)} {n(-XH)}V0", 40),  # u
        (f"M{n(_H)} 0V{n(-XH)}" + arch(_H, 31) + arch(31, 62 - _H), 62),                          # m
        (a, XH),                                                                                   # a
        (f"M{n(h0)} 0V{n(-XH)}" + arch(h0, h1), 40),                                              # n
        (f"M{n(_H)} 0V{n(-ASC + _H + 12)}A12 12 0 0 1 {n(_H + 12)} {n(-ASC + _H)}H{n(_H + 20)}"
         f"M-3 {n(-_C)}H24", 26),                                                                  # f
        (f"M{n(_H)} 0V{n(-XH)}", S),                                                               # dotless i
        (a, XH),                                                                                   # a
    ]


def wordmark(x0: float, base: float, k: float) -> tuple[str, tuple[float, float, float], float]:
    """The wordmark at scale k: its svg, the i's dot (cx, cy, r) and its width."""
    paths, x, dot = [], 0.0, (0.0, 0.0, 0.0)
    for i, (d, w) in enumerate(_glyphs()):
        paths.append(f'<path transform="translate({n(x)} 0)" d="{d}"/>')
        if i == 6:
            dot = (x0 + (x + _H) * k, base - (XH + 10 + S * 0.62) * k, S * 0.62 * k)
        x += w + 8
    width_ = (x - 8) * k
    return (f'<g transform="translate({n(x0)} {n(base)}) scale({n(k)})" class="glyph">{"".join(paths)}</g>',
            dot, width_)


def logo_svg(logo: Logo, x: float, y: float, h: float, cls: str = "inkf") -> tuple[str, float, tuple[float, float, float]]:
    """The H (without its dot) at height h, its width, and where its dot sits."""
    vx, vy, vw, vh = logo.viewbox
    s = h / vh
    w = vw * s
    slot = ((x + (logo.dot[0] - vx) * s, y + (logo.dot[1] - vy) * s, logo.dot[2] * s) if logo.dot
            else (x + w * 0.9, y - h * 0.12, h * 0.1))
    return (f'<svg x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" viewBox="{" ".join(n(v) for v in logo.viewbox)}" '
            f'overflow="visible" class="{cls}">{logo.body}</svg>', w, slot)


Frame = tuple[float, float, float, float]  # t, x, y, r


def hop(t0: float, a: tuple[float, float, float], b: tuple[float, float, float], d: float = 1.0) -> list[Frame]:
    """A ballistic hop from a to b starting at t0."""
    peak = min(a[1], b[1]) - 70
    ctrl = 2 * peak - (a[1] + b[1]) / 2
    out = []
    for i in range(9):
        u = i / 8
        e = u * u * (3 - 2 * u)
        x = a[0] + (b[0] - a[0]) * e
        y = (1 - e) ** 2 * a[1] + 2 * (1 - e) * e * ctrl + e * e * b[1]
        out.append((t0 + d * u, x, y, a[2] + (b[2] - a[2]) * e))
    return out


def land(t: float, at: tuple[float, float, float]) -> list[Frame]:
    """A squash on landing, mechanical rather than rubbery."""
    x, y, r = at
    return [(t + 0.1, x, y + r * 0.1, r * 0.9), (t + 0.25, x, y, r)]


def dot_track(frames: list[Frame], cls: str = "red") -> str:
    frames = sorted(frames)
    t, x, y, r = frames[0]
    return (f'<circle class="{cls}" cx="{n(x)}" cy="{n(y)}" r="{n(r)}">'
            + anim("cx", [(t, x) for t, x, _, _ in frames]) + anim("cy", [(t, y) for t, _, y, _ in frames])
            + anim("r", [(t, r) for t, _, _, r in frames]) + "</circle>")


def ch_mark(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        lx, ly, lh = 92, 130, 290
        mark, lw, slot = logo_svg(f.logo, lx, ly, lh)
        # The H arrives as three planes cut from the one mark: the left stem drops from above, the
        # middle slides in along the diagonal, the right stem rises from below.
        moves = [(0, -560), (-640, 640 * SLOPE), (0, 560)]
        cuts, parts = [], []
        for i, (dx, dy) in enumerate(moves):
            x0 = lx - 300 if i == 0 else lx + lw * i / 3
            x1 = lx + lw + 300 if i == 2 else lx + lw * (i + 1) / 3 + 0.5
            cuts.append(f'<clipPath id="cut{i}"><rect x="{n(x0)}" y="-600" width="{n(x1 - x0)}" height="1800"/></clipPath>')
            parts.append(f'<g clip-path="url(#cut{i})">{g(mark, enter(t0 + 0.3 + 0.35 * i, dx, dy, 0.6))}</g>')
        letters, idot, _ = wordmark(450, 330, 1.25)
        word = g(letters, enter(t0 + 2.0, 0, 160, 0.45), appear(t0 + 2.0, 0.1))
        # The red circle rolls down the diagonal from the right edge and drops into the H's slot,
        # hops over to dot the i, and comes home.
        home = slot
        sx, sy, sr = home
        frames: list[Frame] = [(t0, W + 80, sy - 260, sr), (t0 + 1.3, W + 80, sy - 260, sr),
                               (t0 + 2.2, sx + 60, sy - 40, sr), (t0 + 2.45, sx, sy, sr)]
        frames += land(t0 + 2.45, home) + hop(t0 + 4.0, home, idot) + land(t0 + 5.0, idot)
        frames += hop(t0 + 8.0, idot, home) + land(t0 + 9.0, home) + [(t1 + 1, sx, sy, sr)]
        lead = (f.kicker or "").upper()
        tag = g(slab(450, 410, lead, 22, "rev", "red"), enter(t0 + 3.0, -W - 400, 0)) if lead else ""
        ground = (g(f'<polygon points="{W},0 {W},{n(H * 0.62)} {n(W - 360)},0" class="red"/>', enter(t0 + 0.1, 420, -420 * SLOPE))
                  + g(f'<rect x="-40" y="{H - 88}" width="{W + 80}" height="18" class="inkf" '
                      f'transform="rotate({n(-ANGLE / 3)} {W / 2} {H - 80})"/>', enter(t0 + 0.5, -W - 80, 0)))
        return f"<defs>{''.join(cuts)}</defs>{ground}{''.join(parts)}{word}{tag}{dot_track(frames)}"
    return draw


def ch_thesis(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        # After Lissitzky: a red wedge driving into a circle. The circle is the model; the wedge is
        # the flow built around it.
        cx, cy, r = 230, 470, 200
        circle = g(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="inkf"/>' + text(cx - 60, cy + 6, "MODEL", "bk30r"),
                   enter(t0 + 0.2, -520, 0))
        wedge = g(f'<polygon points="{W + 20},{cy - 150} {W + 20},{cy + 40} {cx + 60},{cy - 20}" class="red"/>'
                  + text(W - 210, cy - 22, "FLOW", "bk40p"), enter(t0 + 1.0, 820, 0, 0.6))
        lines = wrap(f.headline.upper(), 40, 540, 3, True)
        head = "".join(g(text(420, 104 + i * 50, ln, "bk40"), enter(t0 + 0.5 + 0.2 * i, 700, 0))
                       for i, ln in enumerate(lines))
        rule = f'<rect x="420" y="{104 + len(lines) * 50 - 28}" height="10" class="red">{extend("width", t0 + 1.3, 240)}</rect>'
        # Then the argument, a sentence at a time.
        said = f.manifesto[:2] + ([f.bet.split(" — ")[0].rstrip(",;") + "."] if f.bet else [])
        step = (t1 - t0 - 4.0) / max(len(said), 1)
        talk = []
        for i, s in enumerate(said):
            a, b = t0 + 3.6 + i * step, t0 + 3.6 + (i + 1) * step
            body = "".join(text(440, 276 + j * 27, ln, "b20") for j, ln in enumerate(wrap(s, 20, 520, 4, True)))
            talk.append(g(body, anim("opacity", [(0, 0), (a, 0), (a + 0.15, 1), (b - 0.15, 1), (b, 0)]),
                          move([(0, 0, 24), (a, 0, 24), (a + 0.3, 0, 0)])))
        bar = f'<rect x="420" y="254" width="8" height="84" class="red">{appear(t0 + 3.6)}</rect>' if said else ""
        return circle + wedge + head + rule + bar + "".join(talk)
    return draw


def chips(x: float, y: float, items: list[tuple[str, str]], room: float, t: float, hot: Callable[[str], bool]) -> str:
    out, cx = [], x
    for i, (name, note) in enumerate(items):
        label = name + (f" · {note}" if note else "")
        w = width(label, 15, True) + 18
        if cx + w > x + room:
            out.append(g(text(cx + 4, y + 21, f"+{len(items) - i}", "c15"), appear(t + 0.05 * i)))
            break
        lit = hot(name)
        out.append(g(f'<rect x="{n(cx)}" y="{n(y)}" width="{n(w)}" height="30" class="{"red" if lit else "chip"}"/>'
                     + text(cx + 9, y + 21, label, "c15r" if lit else "c15"),
                     enter(t + 0.05 * i, 0, -24, 0.25), appear(t + 0.05 * i, 0.1)))
        cx += w + 6
    return "".join(out)


def native(name: str) -> bool:
    """The runtime's direct model call (litellm), set apart from the coding-agent CLIs."""
    return name.lower().startswith("litellm")


def ch_stack(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        # A vertical red slab carries the runtime's name; the docs' bands stack beside it.
        side = g(f'<rect x="{W - 110}" y="-10" width="84" height="{H + 20}" class="red"/>'
                 + text(W - 50, H - 36, "HUMANIZE", "bk48p", f' transform="rotate(-90 {W - 50} {H - 36})"'),
                 enter(t0 + 0.1, 0, -H - 20))
        rows, y = [], 64
        for i, band in enumerate(f.bands[:4]):
            ti = t0 + 0.5 + 0.7 * i
            title = band.title.upper()
            tw = width(title, 22, True)
            rows.append(g(f'<rect x="48" y="{y}" width="10" height="80" class="inkf"/>'
                          + text(74, y + 24, title, "bk22")
                          + text(88 + tw, y + 23, fit(band.about, 15, 770 - tw - 30), "m15")
                          + chips(74, y + 42, band.chips, 770, ti + 0.3, native),
                          enter(ti, -W, 0)))
            if band.down and i < min(len(f.bands), 4) - 1:
                rows.append(g(f'<polygon points="78,{y + 92} 98,{y + 92} 88,{y + 108}" class="red"/>'
                              + text(110, y + 106, fit(band.down, 15, 740), "i15"), appear(ti + 0.6)))
            y += 124
        hot = next(((c, note) for b in f.bands for c, note in b.chips if native(c)), None)
        note = g(slab(470, H - 22, f"{hot[0]}: {hot[1]}" if hot[1] else hot[0], 17, "rev17", "red", angle=ANGLE / 3),
                 enter(t0 + 4.5, 520, 0)) if hot else ""
        return side + "".join(rows) + note
    return draw


def ch_turn(f: Facts) -> Draw:
    turn = next((b.down for b in f.bands if b.down.lower().startswith("a turn")), "")

    def draw(t0: float, t1: float) -> str:
        out = []
        if turn:
            head, _, rest = turn.partition(":")
            parts = [p.strip() for p in re.split(r",\s*|\s+and\s+", rest) if p.strip()]
            out.append(g(text(64, 112, head.strip().upper(), "bk48"), enter(t0 + 0.2, -420, 0)))
            x = 64
            for i, p in enumerate(parts):
                w = width(p, 19, True) + 28
                ti = t0 + 0.8 + 0.35 * i
                out.append(g(f'<rect x="{n(x)}" y="136" width="{n(w)}" height="44" class="{"red" if i == 0 else "inkf"}"/>'
                             + text(x + 14, 165, p, "rev19"), enter(ti, 0, -220)))
                if i < len(parts) - 1:
                    out.append(g(text(x + w + 6, 168, "+", "bk22"), appear(ti + 0.3)))
                x += w + 28
        # The runtime's features, each with a working diagram: a budget meter, one clock, the places.
        feats = f.features[:3]
        cw = (W - 128 - 32 * (len(feats) - 1)) / max(len(feats), 1)
        env = next((b.chips for b in f.bands if b.title.lower().startswith("environment")), [])
        for i, (h3, p) in enumerate(feats):
            x = 64 + i * (cw + 32)
            ti = t0 + 2.4 + 0.5 * i
            body = [f'<rect x="{n(x)}" y="226" width="{n(cw)}" height="6" class="inkf"/>',
                    *[text(x, 258 + 22 * j, ln, "bk17") for j, ln in enumerate(wrap(h3.upper(), 17, cw, 2, True))]]
            body += [text(x, 306 + 22 * j, ln, "m15") for j, ln in enumerate(wrap(p, 15, cw, 3))]
            dy, key = 392, (h3 + " " + p).lower()
            if "budget" in key:     # a meter filling to its stop line, and the run stopping there
                stop = x + cw * 0.84
                body += [f'<rect x="{n(x)}" y="{dy}" width="{n(cw)}" height="34" class="chip"/>',
                         f'<rect x="{n(x)}" y="{dy}" height="34" class="inkf">{anim("width", [(0, 0), (ti + 0.6, 0), (ti + 5.6, stop - x)])}</rect>',
                         f'<rect x="{n(stop)}" y="{dy - 12}" width="6" height="58" class="red"/>',
                         g(slab(stop - 84, dy + 80, "STOP", 19, "rev19", "red"), appear(ti + 5.6, 0.05))]
            elif "trace" in key or "clock" in key:   # lanes of turns on one timeline, a cursor sweeping it
                for j, (a, w_, cls) in enumerate([(0.0, 0.3, "inkf"), (0.32, 0.22, "red"), (0.56, 0.4, "inkf"),
                                                  (0.08, 0.18, "red"), (0.4, 0.25, "inkf"), (0.7, 0.26, "red")]):
                    body.append(f'<rect x="{n(x + a * cw)}" y="{dy + (j % 3) * 22}" height="16" class="{cls}">'
                                f'{extend("width", ti + 0.5 + a * 4, w_ * cw, 0.8)}</rect>')
                body.append(f'<rect y="{dy - 10}" width="3" height="84" class="inkf" x="{n(x)}">'
                            f'{anim("x", [(0, x), (ti + 0.5, x), (ti + 5.3, x + cw)])}</rect>')
            elif env:               # the places the work can land
                for j, (name, _) in enumerate(env[:4]):
                    body.append(g(f'<rect x="{n(x)}" y="{dy + j * 24}" width="12" height="16" class="red"/>'
                                  + text(x + 22, dy + j * 24 + 14, fit(name, 15, cw - 22), "c15"),
                                  enter(ti + 0.6 + 0.3 * j, 80, 0, 0.35)))
            out.append(g("".join(body), enter(ti, 0, 90), appear(ti, 0.15)))
        return "".join(out)
    return draw


def ch_flows(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        total = sum(len(ns) for _, ns in f.flows)
        big = g(text(40, 250, str(total), "huge") + text(50, 300, "FLOWS", "bk40"), enter(t0 + 0.2, 0, -320))
        wedge = g(f'<polygon points="0,{H} 380,{H} 0,{n(H - 380 * SLOPE * 1.5)}" class="red"/>', enter(t0 + 0.1, -420, 0))
        rows, y = [], 64
        gap = min(64, (H - 100) / max(len(f.flows), 1))
        for i, (title, names) in enumerate(f.flows):
            ti = t0 + 0.6 + 0.3 * i
            rows.append(g(f'<rect x="300" y="{n(y)}" width="236" height="32" class="inkf"/>'
                          + text(310, y + 22, fit((title or "Flows").upper(), 14, 220, True), "rev14"),
                          enter(ti, -320, 0, 0.4)))
            rows.append(chips(546, y + 1, [(nm, "") for nm in names], W - 572, ti + 0.3, lambda s: False))
            y += gap
        return wedge + big + "".join(rows)
    return draw


def ch_loop(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        lp = f.loop
        assert lp is not None
        (a, a_does), (b, b_does) = lp.roles
        out = [g(slab(64, 106, lp.name.upper(), 40, "bk40p", "red"), enter(t0 + 0.1, -520, 0)),
               g("".join(text(64, 160 + 27 * j, ln, "b20") for j, ln in enumerate(wrap(lp.says, 20, 870, 2, True))),
                 appear(t0 + 0.6))]
        # Two blocks on the diagonal; the red circle carries the work up to the checker and the
        # verdict back down, round after round, until the checker says done.
        ax, ay = 120, 420
        bx, by = 600, ay - 480 * SLOPE
        bw = min(300, max(220, width(max(a, b, key=len).upper(), 30, True) + 32))
        for x, y, role, does in ((ax, ay, a, a_does), (bx, by, b, b_does)):
            out.append(g(f'<rect x="{x}" y="{n(y)}" width="{n(bw)}" height="80" class="inkf"/>'
                         + text(x + 16, y + 50, fit(role.upper(), 30, bw - 26, True), "bk30r")
                         + "".join(text(x, y + 104 + 20 * j, ln, "m15") for j, ln in enumerate(wrap(does, 15, 300, 2))),
                         enter(t0 + 0.4, 0, 320, 0.5)))
        out.append(f'<line x1="{n(ax + bw)}" y1="{n(ay + 40)}" x2="{bx}" y2="{n(by + 40)}" class="wire">{appear(t0 + 1.0)}</line>')
        rounds = 3
        span = (t1 - t0 - 2.6) / rounds
        p, q = (ax + 196, ay - 26), (bx + 110, by - 26)
        frames: list[Frame] = [(t0, *p, 0.01), (t0 + 1.2, *p, 0.01), (t0 + 1.4, *p, 18)]
        marks = []
        for rnd in range(rounds):
            s = t0 + 1.6 + rnd * span
            frames += [(s, *p, 18), (s + span * 0.35, *q, 18), (s + span * 0.55, *q, 18), (s + span * 0.9, *p, 18)]
            last = rnd == rounds - 1
            shown = [(0, 0), (s + span * 0.45, 0), (s + span * 0.5, 1)] + ([] if last else [(s + span, 1), (s + span + 0.01, 0)])
            marks.append(g(slab(bx + bw + 20, by + 52, "DONE" if last else "NOT YET", 22, "rev", "red" if last else "inkf"),
                           anim("opacity", shown, discrete=True)))
            here = [(0, 0), (s, 0), (s + 0.01, 1)] + ([] if last else [(s + span, 1), (s + span + 0.01, 0)])
            marks.append(g(text(ax, ay - 24, f"ROUND {rnd + 1}", "bk22"), anim("opacity", here, discrete=True)))
        frames.append((t1 + 0.5, *p, 18))
        return "".join(out) + "".join(marks) + dot_track(frames)
    return draw


def ch_projects(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        rows = []
        ps = f.projects[:6]
        gap = min(70, (H - 160) / max(len(ps), 1))
        for i, p in enumerate(ps):
            y = 66 + i * gap
            ti = t0 + 0.4 + 0.35 * i
            sw = width(p.stat, 30, True) + 24 if p.stat else 0
            row = text(64, y + 30, fit(p.name.upper(), 24, 290, True), "bk24") + text(64, y + 52, fit(p.sub, 15, 290), "m15")
            if p.stat:
                row += (f'<rect x="372" y="{n(y + 2)}" height="46" class="red">{extend("width", ti + 0.3, sw, 0.45)}</rect>'
                        + g(text(384, y + 38, p.stat, "bk30r"), appear(ti + 0.65)))
            says = p.stat_says or p.lede
            row += g("".join(text(372 + (sw + 16 if sw else 0), y + 20 + 20 * j, ln, "m15") for j, ln in enumerate(wrap(says, 15, W - 430 - sw, 2))),
                     appear(ti + 0.75))
            rows.append(g(row, enter(ti, -W, 0)))
        # What came back, as a ticker on an ink band across the foot.
        ticker = ""
        if f.results:
            s = "   ■   ".join(f"{lab.upper()}  {num}" for lab, num in f.results) + "   ■   "
            run = width(s, 17, True)
            ticker = (f'<g transform="rotate({n(-ANGLE / 5)} {W / 2} {H - 46})"><rect x="-60" y="{H - 72}" width="{W + 120}" height="42" class="inkf"/>'
                      f'<g>{move([(0, 0, 0), (t0, 0, 0), (t1, -min(run, 70 * (t1 - t0)), 0)])}'
                      + text(0, H - 45, s, "rev17") + text(run, H - 45, s, "rev17") + "</g></g>")
        return "".join(rows) + ticker
    return draw


def ch_latest(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        out = [g(f'<polygon points="{W},{H} {W},{H - 190} {n(W - 190 / SLOPE)},{H}" class="red"/>', enter(t0 + 0.2, 640, 0)),
               g(text(W - 44, 74, "LATEST", "bk64", ' text-anchor="end"'), enter(t0 + 0.1, 420, 0))]
        y = 80
        for i, p in enumerate(f.posts):
            lines = wrap(p.title, 22, 600, 2, True)
            h = 27 * len(lines) + (22 if p.by else 0) + 30
            if y + h > H - 60:
                break
            ti = t0 + 0.5 + 0.45 * i
            row = (f'<rect x="64" y="{y}" width="92" height="28" class="{"red" if p.kind == "NEWS" else "inkf"}"/>'
                   + text(76, y + 20, p.kind, "rev14") + text(64, y + 50, p.date.upper(), "m15")
                   + "".join(text(180, y + 22 + 27 * j, ln, "bk22") for j, ln in enumerate(lines))
                   + (text(180, y + 22 + 27 * len(lines), fit(p.by, 15, 600), "m15") if p.by else ""))
            out.append(g(row, enter(ti, 0, 60, 0.35), appear(ti, 0.1)))
            y += h
        return "".join(out)
    return draw


def ch_people(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        out = []
        intro = sentences(f.people_intro)[-1] if f.people_intro else ""
        if intro:
            out.append(g(text(64, 100, fit(intro, 26, 870, True), "bk26"), enter(t0 + 0.1, -520, 0)))
        ppl = f.people[:24]
        per = min(12, max(len(ppl), 1))
        cw = (W - 128) / per
        rows = math.ceil(len(ppl) / per)
        for i, p in enumerate(ppl):
            r, c = divmod(i, per)
            cx, cy = 64 + c * cw + cw / 2, 176 + r * 104 - c * 4  # the grid rises with the diagonal
            ti = t0 + 0.5 + 0.06 * i
            if p.face:
                face = (f'<g transform="translate({n(cx)} {n(cy)})"><image href="{p.face}" x="-28" y="-28" width="56" height="56" '
                        f'clip-path="url(#face)" filter="url(#gray)"/></g>')
            else:
                face = (f'<circle cx="{n(cx)}" cy="{n(cy)}" r="28" class="inkf"/>'
                        + text(cx, cy + 7, "".join(w[0] for w in p.name.split()[:2]), "rev19", ' text-anchor="middle"'))
            ring = f'<circle cx="{n(cx)}" cy="{n(cy)}" r="28" class="{"ringr" if i % 4 == 0 else "ring"}"/>'
            first = p.name.split()[0]
            out.append(g(face + ring + text(cx, cy + 48, fit(first, 14, cw - 4), "n14", ' text-anchor="middle"'),
                         enter(ti, 0, -420, 0.4)))
        # How they work, on ink bars that extend one by one, and how to join in, on red.
        top = 176 + rows * 104 - 14
        half = t0 + 3.0
        for j, s in enumerate(f.principles[:5]):
            y = top + 26 * j
            if y > H - 76:
                break
            out.append(f'<rect x="64" y="{y - 18}" width="8" height="24" class="red">{appear(half + 0.35 * j)}</rect>'
                       + g(text(84, y, fit(s, 18, W - 150, True), "bk18"), appear(half + 0.35 * j), enter(half + 0.35 * j, 40, 0, 0.3)))
        if f.contact:
            what, where = f.contact[0]
            out.append(g(f'<rect x="0" y="{H - 64}" width="{W}" height="44" class="red"/>'
                         + text(64, H - 35, fit(f"{what} → {where.upper()}", 17, W - 128, True), "rev17"),
                         enter(half + 2.2, -W, 0)))
        return "".join(out)
    return draw


def ch_outro(f: Facts) -> Draw:
    def draw(t0: float, t1: float) -> str:
        mark, lw, slot = logo_svg(f.logo, 90, 150, 250, "paperf")
        sx, sy, sr = slot
        site = SITE.split("//", 1)[-1].upper()
        out = [f'<rect width="{W}" height="{H}" class="red"/>',
               g(mark, enter(t0 + 0.2, -420, 0)),
               g(text(370, 300, site, "huge2", f' style="font-size:{n(min(64, 64 * (W - 400) / width(site, 64, True)))}px"'),
                 enter(t0 + 0.6, 640, 0)),
               g(text(374, 352, "GITHUB.COM/HUMANFIA", "bk22i"), appear(t0 + 1.2)),
               f'<rect x="374" y="372" height="10" class="inkf">{extend("width", t0 + 1.4, 400)}</rect>']
        frames: list[Frame] = [(t0, sx, -60, sr), (t0 + 1.4, sx, -60, sr), (t0 + 1.9, sx, sy, sr)]
        out.append(dot_track(frames + land(t0 + 1.9, slot) + [(t1 + 1, sx, sy, sr)], "inkf"))
        return "".join(out)
    return draw


def scenes(f: Facts) -> list[Scene]:
    """The storyboard: a chapter appears only if the site gave it something to say."""
    out = [Scene("Humanfia", 12, ch_mark(f))]
    if f.headline:
        out.append(Scene("The thesis", 14, ch_thesis(f)))
    if f.bands:
        out.append(Scene("Humanize, the runtime", 11, ch_stack(f)))
    if any(b.down.lower().startswith("a turn") for b in f.bands) or f.features:
        out.append(Scene("A turn, and what it keeps", 11, ch_turn(f)))
    if f.flows:
        out.append(Scene("Flows", 9, ch_flows(f)))
    if f.loop:
        out.append(Scene(f"A flow, running: {f.loop.name}", 11, ch_loop(f)))
    if f.projects:
        out.append(Scene("Projects", 14, ch_projects(f)))
    if f.posts:
        out.append(Scene("News and blog", 11, ch_latest(f)))
    if f.people:
        out.append(Scene("The people", 13, ch_people(f)))
    out.append(Scene("Find us", 8, ch_outro(f)))
    return out


# ------------------------------------------------------------------------------------ the banner

def wipe(t: float, cls: str) -> str:
    """A diagonal plane crossing the frame, centred on t; the cut between chapters happens under it."""
    skew = H * SLOPE * 2.2
    wp = W + 440
    poly = f'<polygon points="0,0 {n(wp)},0 {n(wp - skew)},{H} {n(-skew)},{H}" class="{cls}"/>'
    a, b, d = -wp, W + skew, 0.8
    return g(poly, move([(0, a, 0), (t - d / 2, a, 0), (t + d / 2, b, 0)]))


def css(theme: str) -> str:
    c = THEMES[theme]
    blk = f"font-family:{BLOCK};font-weight:900"
    return (f".bg{{fill:{c['paper']}}}.inkf{{fill:{c['ink']}}}.paperf{{fill:{c['paper']}}}.red{{fill:{c['red']}}}"
            f".chip{{fill:{c['ink']};fill-opacity:.12}}.ring,.ringr{{fill:none;stroke:{c['ink']};stroke-width:3}}"
            f".ringr{{stroke:{c['red']}}}.wire{{stroke:{c['ink']};stroke-width:4;stroke-dasharray:12 8}}"
            f"text{{font-family:{SANS};fill:{c['ink']}}}"
            f".kick{{font-size:15px;font-weight:800;letter-spacing:.16em}}"
            f".glyph{{fill:none;stroke:{c['ink']};stroke-width:{n(S)}}}.huge{{{blk};font-size:170px;letter-spacing:-.04em}}"
            f".huge2{{{blk};font-size:64px;fill:{c['paper']}}}"
            + "".join(f".bk{s}{{{blk};font-size:{s}px}}" for s in (17, 18, 22, 24, 26, 40, 48, 64))
            + "".join(f".bk{s}{k}{{{blk};font-size:{s}px;fill:{c['paper']}}}" for s, k in ((30, "r"), (40, "p"), (48, "p")))
            + f".bk22i{{{blk};font-size:22px;letter-spacing:.08em;fill:{c['ink']}}}"
            f".rev,.rev14,.rev17,.rev19{{{blk};fill:{c['paper']}}}"
            f".rev{{font-size:22px}}.rev14{{font-size:14px;letter-spacing:.06em}}.rev17{{font-size:17px}}.rev19{{font-size:19px}}"
            f".b20{{font-size:20px;font-weight:800}}.m15{{font-size:15px;fill:{c['mute']}}}.n14{{font-size:14px;font-weight:700}}"
            f".i15{{font-size:15px;font-style:italic;fill:{c['mute']}}}.c15{{font-size:15px;font-weight:700}}"
            f".c15r{{font-size:15px;font-weight:700;fill:{c['paper']}}}")


def banner(theme: str, f: Facts) -> str:
    plan = scenes(f)
    scale = T / sum(s.seconds for s in plan)
    t, layers, cuts = 0.0, [], []
    for k, s in enumerate(plan, 1):
        t0, t1 = t, t + s.seconds * scale
        layers.append(f'<g opacity="{1 if k == 1 else 0}">{on(t0, t1)}{s.draw(t0, t1)}{kicker(48, 40, k, s.kicker)}</g>')
        cuts.append(t1)
        t = t1
    # The last cut is the loop's seam: wipe just before it so the plane is gone when the clock restarts.
    wipes = "".join(wipe(min(cut, T - 0.41), "red" if i % 2 else "inkf") for i, cut in enumerate(cuts))
    # The clock itself: a rail across the foot, ticked at each chapter, with a red block travelling it.
    rail = (f'<rect x="0" y="{H - 6}" width="{W}" height="6" class="chip"/>'
            + "".join(f'<rect x="{n(W * cut / T - 1)}" y="{H - 6}" width="2" height="6" class="bg"/>' for cut in cuts[:-1])
            + f'<rect x="-40" y="{H - 6}" width="40" height="6" class="red">{anim("x", [(0, -40), (T, W)])}</rect>')
    title = "Humanfia" + (f" — {f.headline}" if f.headline else "")
    return (
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-labelledby="t"><title id="t">{esc(title)}</title><style>{css(theme)}</style>'
        f'<defs><clipPath id="face"><circle r="28"/></clipPath>'
        f'<filter id="gray"><feColorMatrix type="saturate" values="0"/></filter></defs>'
        f'<rect width="{W}" height="{H}" class="bg"/>{"".join(layers)}{wipes}{rail}</svg>\n'
    )


# ----------------------------------------------------------------------------------------- main

def main() -> None:
    themes = [os.environ["THEME"]] if os.environ.get("THEME") else ["light", "dark"]
    facts = gather()
    for theme in themes:
        out = PROFILE / f"humanfia-portfolio-{theme}.svg"
        out.write_text(banner(theme, facts), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
