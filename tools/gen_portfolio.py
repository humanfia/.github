#!/usr/bin/env python3
"""Generate the Humanfia org profile banner from humanfia.ai: a constructivist spot of two minutes.

Nothing about Humanfia is written down here. Every run reads the live sites and cuts what it finds
together like a commercial -- about fifty shots of one to three seconds, one idea set big in each:

    the mark        /logo.svg: the ball drops, swells to a red frame, shrinks into the H's slot; the
                    H, a slab, turns; the wordmark draws itself; the headline slams down a word at a
                    time with the ball as its full stop; the manifesto, a line a shot
    the runtime     the Humanize docs' bands: a tower that lands slab by slab, the turn falling
                    through it, each band's parts flying out as it lands; the home page's features
    the flows       a counter, then the /flows/ catalogue at montage speed, each loop acted out
    the projects    the nav's Projects menu: a solid spinning in, the name cut deep
    the results     the home page's tiles: each number spun into place on a counter
    the latest      /news/feed.rss and /blog/feed.rss: the kind stamped on, the title cascading in
    the people      About's roster bursting out of the ball, then turning over as a wave; its
                    principles stamped on plates, stacking up
    the address     on red: the H, the site's name, the ball dropping home, About's contacts

Shots are cut on the beat -- whips with speed lines, punch-ins, irises, flights through the
section titles -- and everything in a shot moves from its first frame to its last. The red ball
is the one actor all the way through.

A section whose source the site does not have (a 404 or 410, or markup without the parts it needs)
is left out. Any other failure -- a 403, a 5xx, a timeout -- stops the run, so a bad fetch never
overwrites a good profile.

GitHub shows README images through <img>: no JavaScript, no web fonts, nothing loaded. So the 3D
is rotated and projected here (tools/proun.py) and played back by the browser on one SMIL clock,
with CSS keyframes for the extruded mark; type is the system's heaviest sans, avatars are inlined.

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
import shutil
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proun as P  # noqa: E402
from proun import n  # noqa: E402

SITE = os.environ.get("SITE", "https://humanfia.ai").rstrip("/")
DOCS = os.environ.get("DOCS", "https://docs.humanfia.ai/humanize").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
ART = "art"  # where the poster wall this replaced lived; removed on sight
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

THEMES = {  # light: ink and red on paper; dark: paper and red on ink
    "light": {"paper": "#f4efe6", "ink": "#16161a", "red": "#d6331f", "mute": "#5f5a54", "deep": "#5e140b"},
    "dark": {"paper": "#16161a", "ink": "#ece6da", "red": "#ff5a43", "mute": "#a39d92", "deep": "#4a120b"},
}
BLOCK = "'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif"  # heavy block type
SANS = "'Helvetica Neue',Helvetica,Arial,'Segoe UI',sans-serif"
SLOPE = 1 / 3                       # the logo's one diagonal: one in three
ANGLE = math.degrees(math.atan(SLOPE))


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
    href: str
    sub: str = ""                              # what it is, in a few words
    lede: str = ""                             # its page's first sentence


@dataclass
class Flow:
    name: str
    href: str
    tag: str                                   # the kind of loop: "A relay", "Maker and checker", ...
    blurb: str = ""
    roles: list[str] = field(default_factory=list)
    ends: str = ""
    source: str = ""


@dataclass
class Result:
    label: str
    num: str
    body: str = ""
    href: str = ""


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
class Facts:
    logo: Logo
    kicker: str = ""
    headline: str = ""
    lead: str = ""
    acts: list[str] = field(default_factory=list)
    bet: str = ""
    bands: list[Band] = field(default_factory=list)
    features: list[tuple[str, str]] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    flows_href: str = "/flows/"
    projects: list[Project] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    people_href: str = "/about/"
    people_intro: str = ""
    principles: list[str] = field(default_factory=list)
    contact: list[tuple[str, str]] = field(default_factory=list)  # (what for, href)


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
    lead = hero_box.first(cls="h-lead") if hero_box else None
    f.lead = lead.text() if lead else ""
    acts = root.first(cls="h-manifesto-acts")
    f.acts = [li.text() for li in acts.all("li") if li.text()] if acts else []
    if not f.acts:  # the manifesto as one paragraph, as the site once had it
        text = root.first(cls="h-manifesto-text")
        f.acts = sentences(text.text()) if text else []
    f.features = [(h.text(), p.text()) for feat in root.all(cls="h-feature")
                  for h, p in [(feat.first("h3"), feat.first("p"))] if h and p]
    f.results = [Result(lab.text(), num.text(), body.text() if body else "", absolute(tile.attrs.get("href", "")) if tile.attrs.get("href") else "")
                 for tile in root.all(cls="h-tile")
                 for lab, num, body in [(tile.first(cls="h-tile-label"), tile.first(cls="h-tile-num"), tile.first(cls="h-tile-body"))]
                 if lab and num]


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
    """The /flows/ catalogue: a tile per flow, with its kind, its line, its roles and when it ends."""
    menu = find(nav, "Flows")
    f.flows_href = (menu.href if menu and menu.href else "/flows/")
    page = fetch(f.flows_href)
    if not page:
        return
    seen = set()
    for a in dom(page).all("a"):
        if "tile" not in a.classes or not a.attrs.get("href"):
            continue
        h3, tag, blurb = a.first("h3"), a.first(cls="tile-tag"), a.first(cls="tile-blurb")
        if not h3 or not h3.text() or a.attrs["href"] in seen:
            continue
        seen.add(a.attrs["href"])
        meta = a.first(cls="tile-meta")
        source = next((s.text() for s in (meta.all("span") if meta else []) if "tile-tag" not in s.classes and s.text()), "")
        flow = Flow(h3.text().replace(" ", ""), absolute(a.attrs["href"]), tag.text() if tag else "",
                    blurb.text() if blurb else "", source=source)
        for div in a.all("div"):
            dt, dd = div.first("dt"), div.first("dd")
            if dt and dd and dt.text() == "-a":
                flow.roles = [r.strip() for r in re.split(r"\s+·\s+", dd.text()) if r.strip()]
            elif dt and dd and dt.text() == "ends":
                flow.ends = dd.text()
        f.flows.append(flow)


def project_facts(f: Facts, nav: list[Menu]) -> None:
    """Each project the nav lists: what it is in a few words (its title's subtitle, or what its
    kicker says after the name), and its page's first sentence."""
    menu = find(nav, "Projects")
    for label, href in menu.items if menu else []:
        name, _, tail = label.partition(":")
        p = Project(name.strip(), absolute(href), tail.strip())
        page = fetch(href)
        if page:
            root = dom(page)
            h1 = root.first("h1")
            sub = next((x for x in (h1.all() if h1 else []) if any(c.endswith("sub") for c in x.classes)), None)
            kick = next((x for x in root.all("p") if any(c.endswith("kicker") for c in x.classes) and "·" in x.text()), None)
            if sub is not None and sub.text():
                p.sub = p.sub or sub.text().rstrip(".")
            elif kick is not None and kick.text().split("·")[0].strip().lower() == p.name.lower():
                p.sub = p.sub or kick.text().split("·", 1)[1].strip()
            lede = next((x for x in root.all("p") if x.text() and any(re.search(r"(lead|stand|lede)$", c) for c in x.classes)), None)
            p.lede = next(iter(sentences(lede.text())), "") if lede else ""
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


def latest(n_: int = 5) -> list[Post]:
    posts = feed("/news/feed.rss", "NEWS") + feed("/blog/feed.rss", "BLOG")
    unique = {p.href: p for p in posts}.values()
    return sorted(unique, key=lambda p: (-p.when, p.title))[:n_]


def people_facts(f: Facts, nav: list[Menu]) -> None:
    """The roster on About (and on Team, while the site still has one), its principles and contacts."""
    seen: dict[str, Person] = {}
    for href in [m.href for m in nav if m.label.lower() in ("about", "team") and m.href]:
        page = fetch(href)
        if not page:
            continue
        f.people_href = href
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
        f.contact = f.contact or [(b.text(), absolute(a.attrs.get("href", "")))
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
    url = re.sub(r"([?&])s=\d+", r"\1s=96", src) if "s=" in src else src + ("&" if "?" in src else "?") + "s=96"
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


# ----------------------------------------------------------------------------------- type & paper

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


def tracked(s: str, size: float) -> float:
    """The width of letter-spaced block caps (the "t" kind)."""
    return width(s, size, True) * 0.9 + 0.14 * size * len(s)


def fitsize(s: str, size: float, room: float, heavy: bool = True, least: float = 0.0) -> float:
    """The largest size up to `size` at which s fits in room."""
    return max(least, min(size, size * room / max(width(s, size, heavy), 1e-6)))


def esc(s: str) -> str:
    return html.escape(s, quote=True)


KINDS = {  # a text class's family, weight and style
    "k": f"font-family:{BLOCK};font-weight:900",
    "b": f"font-family:{SANS};font-weight:800",
    "r": f"font-family:{SANS};font-weight:500",
    "i": f"font-family:{SANS};font-weight:500;font-style:italic",
    "t": f"font-family:{BLOCK};font-weight:900;letter-spacing:.14em",
}


class Sheet:
    """One poster: its size, its theme's paper and inks, and the classes, defs and keyframes it uses."""

    def __init__(self, theme: str, w: float, h: float, title: str) -> None:
        self.theme, self.c, self.w, self.h, self.title = theme, THEMES[theme], w, h, title
        self.css: list[str] = []
        self.defs: list[str] = []
        self.sizes: set[tuple[str, float]] = set()
        self._uid = 0

    def uid(self, p: str = "u") -> str:
        self._uid += 1
        return f"{p}{self._uid}"

    def text(self, x: float, y: float, s: str, size: float, kind: str = "k", ink: str = "ink",
             anchor: str = "", extra: str = "") -> str:
        self.sizes.add((kind, size))
        a = f' text-anchor="{anchor}"' if anchor else ""
        return f'<text x="{n(x)}" y="{n(y)}" class="{kind}{n(size).replace(".", "_")} {ink}"{a}{extra}>{esc(s)}</text>'

    def ball(self) -> str:
        """The red ball's gradient: lit from the top left, like everything else here."""
        if not any('id="ball"' in d for d in self.defs):
            c = self.c
            self.defs.append(f'<radialGradient id="ball" cx=".38" cy=".34" r=".72" fx=".3" fy=".26">'
                             f'<stop offset="0" stop-color="{P.mix(c["red"], "#ffffff", .45)}"/>'
                             f'<stop offset=".35" stop-color="{c["red"]}"/>'
                             f'<stop offset="1" stop-color="{c["deep"]}"/></radialGradient>')
        return "url(#ball)"

    def grain(self) -> str:
        """Print grain over the whole sheet: still, so it costs nothing after the first paint."""
        r, g_, b = (int(self.c["ink"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.defs.append(f'<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" '
                         f'baseFrequency=".85" numOctaves="2" seed="11" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 {r:.3f} '
                         f'0 0 0 0 {g_:.3f} 0 0 0 0 {b:.3f} 0 0 1.4 0 -.62"/></filter>')
        return f'<rect width="{n(self.w)}" height="{n(self.h)}" filter="url(#grain)" opacity=".16"/>'

    def render(self, body: str) -> str:
        c = self.c
        fills = "".join(f".{k}{{fill:{v}}}" for k, v in c.items())
        stroke = (f".hair{{fill:none;stroke:{c['ink']};stroke-width:1.5}}.wire{{fill:none;stroke:{c['ink']};stroke-width:3;"
                  f"stroke-dasharray:10 8}}.redwire{{fill:none;stroke:{c['red']};stroke-width:3}}"
                  f".chip{{fill:{c['ink']};fill-opacity:.1}}.glyph{{fill:none;stroke:{c['ink']};stroke-width:13}}"
                  f".glyphr{{fill:none;stroke:{c['red']};stroke-width:13}}")
        fonts = "".join(f".{k}{n(s).replace('.', '_')}{{{KINDS[k]};font-size:{n(s)}px}}" for k, s in sorted(self.sizes))
        calm = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {n(self.w)} {n(self.h)}" width="{n(self.w)}" height="{n(self.h)}" '
                f'role="img" aria-labelledby="t"><title id="t">{esc(self.title)}</title>'
                f'<style>{fills}{stroke}{fonts}{"".join(self.css)}{calm}</style>'
                f'<defs>{"".join(self.defs)}</defs><rect width="{n(self.w)}" height="{n(self.h)}" class="paper"/>{body}</svg>\n')


def chips(sh: Sheet, x: float, y: float, items: list[tuple[str, str]], room: float, rows: int = 2,
          hot: Callable[[str], bool] = lambda s: False, size: float = 14) -> tuple[str, float]:
    """Labels on flat plates, wrapped into rows. Returns the svg and the y under the last row."""
    out, cx, row = [], x, 0
    for i, (name, note) in enumerate(items):
        label = name + (f" · {note}" if note else "")
        w = width(label, size, True) * 0.86 + 16
        if cx + w > x + room:
            row, cx = row + 1, x
            if row >= rows:
                out.append(sh.text(x + room - 4, y + (row - 1) * 30 + 19, f"+{len(items) - i}", size, "b", anchor="end"))
                row -= 1
                break
        lit = hot(name)
        yy = y + row * 30
        out.append(f'<rect x="{n(cx)}" y="{n(yy)}" width="{n(w)}" height="24" class="{"red" if lit else "chip"}"/>'
                   + sh.text(cx + 8, yy + 17, label, size, "b", "paper" if lit else "ink"))
        cx += w + 6
    return "".join(out), y + (row + 1) * 30


# ------------------------------------------------------------------------------------- wordmark

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


def wordmark(x0: float, base: float, k: float, cls: str = "glyph") -> tuple[str, tuple[float, float, float], float]:
    """The wordmark at scale k: its svg, the i's dot (cx, cy, r) and its width."""
    paths, x, dot = [], 0.0, (0.0, 0.0, 0.0)
    for i, (d, w) in enumerate(_glyphs()):
        paths.append(f'<path transform="translate({n(x)} 0)" d="{d}"/>')
        if i == 6:
            dot = (x0 + (x + _H) * k, base - (XH + 10 + S * 0.62) * k, S * 0.62 * k)
        x += w + 8
    width_ = (x - 8) * k
    return (f'<g transform="translate({n(x0)} {n(base)}) scale({n(k)})" class="{cls}">{"".join(paths)}</g>',
            dot, width_)


# ------------------------------------------------------------------------------------- the spot

# The banner is cut like a commercial, not paged like a deck: about fifty shots of one to three
# seconds, each with one idea set big, each moving from its first frame to its last, cut on the
# beat with whips, punches, irises and zooms through the type. The red ball is the one actor all
# the way through: it drops, swells into a red frame, shrinks into the logo's slot, becomes the
# headline's full stop, falls through the runtime, and drops home at the end.

W, H = 1000.0, 560.0       # the frame; shown ~830 px wide on GitHub
BALL = 34.0                # the ball's radius, most of the time


def swing(u: float, yaw: float = 38.0, pitch: float = -14.0) -> P.Mat:
    """The mark's slow turn: a figure of eight of yaw and pitch, back where it began after one loop."""
    return P.rot(yaw * math.sin(2 * math.pi * u), pitch + 8 * math.sin(4 * math.pi * u), -2 * math.sin(2 * math.pi * u))


def mark_defs(sh: Sheet, logo: Logo, height: float) -> tuple[float, tuple[float, float, float]]:
    """The H, centred on the origin at the given height, as #hshape. Returns its scale and the dot's
    place (x, y, r) relative to the centre."""
    vx, vy, vw, vh = logo.viewbox
    s = height / vh
    sh.defs.append(f'<g id="hshape" transform="scale({n(s)}) translate({n(-vx - vw / 2)} {n(-vy - vh / 2)})">{logo.body}</g>')
    dx, dy, dr = logo.dot if logo.dot else (vx + vw * 0.875, vy + vh * 0.11, vw * 0.125)
    return s, ((dx - vx - vw / 2) * s, (dy - vy - vh / 2) * s, dr * s)


def _lerp(a, b, u):  # numbers or tuples
    if isinstance(a, tuple):
        return tuple(x + (y - x) * u for x, y in zip(a, b))
    return a + (b - a) * u


_C1 = 1.70158
EASE: dict[str, Callable[[float], float]] = {
    "lin": lambda u: u,
    "out": lambda u: 1 - (1 - u) ** 3,
    "in": lambda u: u ** 3,
    "io": lambda u: 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2,
    "back": lambda u: 1 + (_C1 + 1) * (u - 1) ** 3 + _C1 * (u - 1) ** 2,   # overshoots, then settles
}


def tween(t0: float, d: float, a, b, ease: str = "out", steps: int = 8) -> list:
    """(time, value) samples of a move from a to b: easing, overshoot included, is in the samples."""
    f = EASE[ease]
    return [(t0 + d * i / steps, _lerp(a, b, f(i / steps))) for i in range(steps + 1)]


def _fmt(v) -> str:
    if isinstance(v, tuple):
        return " ".join(n(x) for x in v)
    return v if isinstance(v, str) else n(v)


class Film:
    """The one clock every shot is cut against, and the ball that runs through them all."""

    def __init__(self, theme: str, f: Facts, T: float) -> None:
        self.f, self.T = f, T
        self.sh = Sheet(theme, W, H, "Humanfia" + (f" — {f.headline}" if f.headline else ""))
        self.c = self.sh.c
        self.ball_keys: list[tuple[float, tuple[float, float, float]]] = []
        self.ball_on: list[tuple[float, float]] = []

    def uid(self, p: str = "u") -> str:
        return self.sh.uid(p)

    def _keys(self, pts: list) -> tuple[str, str]:
        T = self.T
        pts = sorted(((min(max(t, 0.0), T), v) for t, v in pts), key=lambda p: p[0])
        if pts[0][0] > 0:
            pts.insert(0, (0.0, pts[0][1]))
        if pts[-1][0] < T:
            pts.append((T, pts[-1][1]))
        times = [f"{t / T:.5f}" for t, _ in pts]
        times[0], times[-1] = "0", "1"
        return ";".join(_fmt(v) for _, v in pts), ";".join(times)

    def anim(self, attr: str, pts: list, discrete: bool = False) -> str:
        values, times = self._keys(pts)
        mode = ' calcMode="discrete"' if discrete else ""
        return (f'<animate attributeName="{attr}" dur="{n(self.T)}s" repeatCount="indefinite"{mode} '
                f'values="{values}" keyTimes="{times}"/>')

    def tf(self, kind: str, pts: list) -> str:
        values, times = self._keys(pts)
        return (f'<animateTransform attributeName="transform" type="{kind}" dur="{n(self.T)}s" '
                f'repeatCount="indefinite" values="{values}" keyTimes="{times}"/>')

    def show(self, t0: float, t1: float) -> str:
        if t0 <= 0:
            return self.anim("display", [(0, "inline"), (t1, "none")], True)
        return self.anim("display", [(0, "none"), (t0, "inline"), (t1, "none")], True)

    def fade(self, t0: float, t1: float, d: float = 0.12) -> str:
        return self.anim("opacity", [(0, 0), *tween(t0, d, 0.0, 1.0, "lin", 2), *tween(t1 - d, d, 1.0, 0.0, "lin", 2)])

    def at(self, x: float, y: float, inner: str, *anims: str) -> str:
        """Content whose animated transforms (scale, rotate) act about the point (x, y)."""
        return f'<g transform="translate({n(x)} {n(y)})">' + "".join(f"<g>{a}" for a in anims) + inner + "</g>" * len(anims) + "</g>"

    def pop(self, t: float, x: float, y: float, inner: str, k0: float = 0.2, d: float = 0.38, ease: str = "back") -> str:
        """Content at (x, y), drawn about its own origin, that springs from k0 to full size at t."""
        return self.at(x, y, inner, self.tf("scale", [(0, (k0, k0)), *tween(t, d, (k0, k0), (1.0, 1.0), ease)]),
                       self.anim("opacity", [(0, 0), (t, 0), (t + 0.06, 1)]))

    def slide(self, t: float, dx: float, dy: float, d: float = 0.32, ease: str = "out") -> str:
        return self.tf("translate", [(0, (dx, dy)), *tween(t, d, (dx, dy), (0.0, 0.0), ease)])

    def drift(self, t0: float, t1: float, dx: float, dy: float = 0.0) -> str:
        return self.tf("translate", [(0, (0.0, 0.0)), (t0, (0.0, 0.0)), (t1, (dx, dy))])

    def reveal(self, t: float, x: float, y: float, w: float, h: float, inner: str, d: float = 0.4) -> str:
        """Content uncovered left to right, as if typed out at speed."""
        cid = self.uid("clip")
        return (f'<clipPath id="{cid}"><rect x="{n(x)}" y="{n(y)}" height="{n(h)}" width="0">'
                f'{self.anim("width", [(0, 0), *tween(t, d, 0.0, w, "out", 6)])}</rect></clipPath>'
                f'<g clip-path="url(#{cid})">{inner}</g>')

    def text(self, x: float, y: float, s: str, size: float, kind: str = "k", ink: str = "ink", anchor: str = "",
             extra: str = "") -> str:
        return self.sh.text(x, y, s, size, kind, ink, anchor, extra)

    def ball(self, pts: list[tuple[float, float, float, float]]) -> None:
        """The ball's path for a stretch of the film, (t, x, y, r); it is shown over that stretch."""
        self.ball_keys += [(t, (x, y, r)) for t, x, y, r in pts]
        self.ball_on.append((pts[0][0], pts[-1][0]))

    def bg(self, ink: str) -> str:
        return f'<rect x="-40" y="-40" width="{n(W + 80)}" height="{n(H + 80)}" class="{ink}"/>'


def flip(ink: str) -> str:
    """The ink that reads on a ground: paper on ink or red, ink on paper."""
    return "ink" if ink == "paper" else "paper"


def blockword(F: Film, x: float, y: float, s: str, size: float, t: float, front: str = "ink",
              side: tuple[str, str] | None = None, depth: int = 9, step: float = 1.7, anchor: str = "",
              length: float = 0.0) -> str:
    """Block capitals pushed back into a solid, the way a constructivist poster cuts its slogans:
    the copies behind slide out to their depth at t, so the letters thicken as they land."""
    side = side or (F.c["red"], F.c["deep"])
    fit_ = f' textLength="{n(length)}" lengthAdjust="spacingAndGlyphs"' if length else ""
    out = []
    for k in range(depth, 0, -1):
        col = P.mix(side[0], side[1], k / depth)
        mv = F.tf("translate", [(0, (0.0, 0.0)), *tween(t, 0.4, (0.0, 0.0), (k * step, k * step), "out", 5)])
        out.append(f"<g>{mv}" + F.text(x, y, s, size, "k", front, anchor, f' style="fill:{col}"{fit_}') + "</g>")
    out.append(F.text(x, y, s, size, "k", front, anchor, fit_))
    return "".join(out)


def capw(s: str, size: float) -> float:
    """What the heavy caps really measure, near enough: the width estimate is a safe upper bound."""
    return width(s, size, True) * 0.9


def fitlines(s: str, room: float, most: float, least: float, lines: int) -> tuple[float, list[str]]:
    """The largest size at which s wraps into at most `lines` lines of heavy caps within room."""
    size = most
    while size > least:
        out = wrap(s, size, room / 0.9, lines, True)
        if len(out) <= lines and all(capw(x, size) <= room for x in out) and "…" not in "".join(out):
            return size, out
        size -= 2
    return least, wrap(s, least, room / 0.9, lines, True)


def words_in(F: Film, t: float, x: float, y: float, lines: list[str], size: float, ink: str = "ink",
             lead: float = 1.08, gap: float = 0.09, hot: Callable[[str], bool] = lambda w: False) -> tuple[str, float, float]:
    """Lines of block capitals, word by word, each slammed down from large. Returns the svg and
    where the last word ends (x, baseline)."""
    out, k, end = [], 0, (x, y)
    for j, line in enumerate(lines):
        cx = x
        by = y + j * size * lead
        for w_ in line.split():
            ww = capw(w_, size)
            ti = t + gap * k
            body = ""
            if hot(w_):
                body += (f'<rect x="{n(-8)}" y="{n(-size * 0.86)}" width="{n(ww + 16)}" height="{n(size * 1.04)}" class="red">'
                         f'{F.anim("width", [(0, 0), *tween(ti, 0.25, 0.0, ww + 16, "out", 4)])}</rect>')
            body += F.text(0, 0, w_, size, "k", "paper" if hot(w_) else ink, extra=f' textLength="{n(ww)}" lengthAdjust="spacingAndGlyphs"')
            out.append(F.at(cx, by, F.at(ww / 2, -size * 0.35, f'<g transform="translate({n(-ww / 2)} {n(size * 0.35)})">{body}</g>',
                                         F.tf("scale", [(0, (2.4, 2.4)), *tween(ti, 0.3, (2.4, 2.4), (1.0, 1.0), "back", 6)])),
                            F.anim("opacity", [(0, 0), (ti, 0), (ti + 0.05, 1)])))
            end = (cx + ww, by)
            cx += ww + size * 0.28
            k += 1
    return "".join(out), end[0], end[1]


# ------------------------------------------------------------------------------------- the shots

Draw = Callable[[Film, float, float], str]


@dataclass
class Shot:
    name: str
    seconds: float
    draw: Draw
    enter: str = "cut"     # cut | whip | punch | rise


def shot_drop(F: Film, t0: float, t1: float) -> str:
    """Ink. The ball drops in, bounces, the bars slam round it -- then it swells to fill the frame."""
    c = F.c
    out = [F.bg("ink")]
    for i, (x, y, w, h) in enumerate(((140, 120, 760, 22), (60, 420, 520, 60), (620, 470, 420, 14), (720, 80, 300, 40))):
        ti = t0 + 0.55 + 0.07 * i
        bar = f'<rect x="{n(-w / 2)}" y="{n(-h / 2)}" width="{n(w)}" height="{n(h)}" class="{"red" if i == 1 else "paper"}"/>'
        dx = -1300 if i % 2 else 1300
        out.append(f'<g transform="translate({n(x + w / 2)} {n(y)}) rotate({n(-ANGLE)})"><g>'
                   f'{F.tf("translate", [(0, (dx, 0.0)), *tween(ti, 0.3, (dx, 0.0), (0.0, 0.0), "back", 6)])}{bar}</g></g>')
    out.append(f'<circle cx="500" cy="300" r="140" class="hair" style="stroke:{c["paper"]}" opacity="0">'
               f'{F.anim("r", [(0, 40), *tween(t0 + 0.5, 0.5, 40.0, 320.0, "out", 5)])}'
               f'{F.anim("opacity", [(0, 0), (t0 + 0.5, 0), (t0 + 0.5, 0.8), (t0 + 1.0, 0)])}</circle>')
    if F.f.kicker:
        k = F.f.kicker.upper()
        kw = tracked(k, 18)
        out.append(F.reveal(t0 + 1.0, 500 - kw / 2, 520, kw + 4, 40, F.text(500, 545, k, 18, "t", "paper", "middle"), 0.5))
    land = 300 - BALL
    F.ball([(t0, 500, -60, BALL), *[(t, 500, y, BALL) for t, y in tween(t0, 0.5, -60.0, land, "in", 5)][1:],
            *[(t, 500, y, BALL) for t, y in tween(t0 + 0.5, 0.22, land, land - 70, "out", 4)][1:],
            *[(t, 500, y, BALL) for t, y in tween(t0 + 0.72, 0.2, land - 70, land, "in", 4)][1:],
            (t1 - 0.42, 500, land, BALL),
            *[(t, 500, land, r) for t, r in tween(t1 - 0.42, 0.42, BALL, 1250.0, "in", 6)][1:]])
    return "".join(out)


HEIGHT_H = 300.0


def shot_mark(F: Film, t0: float, t1: float) -> str:
    """The red frame shrinks into the H's slot; the H, a slab, turns; the wordmark draws itself;
    the ball hops over to dot the i."""
    c = F.c
    hx, hy = 270.0, 280.0
    _, (sx, sy, sr) = mark_defs(F.sh, F.f.logo, HEIGHT_H)
    Ts = 12.0
    frames = [swing(u, 34, -12) for u in P.loop_frames(60)]
    css, slab = P.extrude("hx", "hshape", frames, Ts, (0, 0), HEIGHT_H * 0.3, 26, (c["red"], c["deep"]), "ink")
    F.sh.css.append(css)
    out = [F.bg("paper")]
    out.append(f'<g><polygon points="{n(W)},0 {n(W)},300 {n(W - 380)},0" class="red"/>{F.slide(t0 + 0.3, 420, -140, 0.4)}</g>')
    out.append(f'<circle cx="840" cy="110" r="230" class="hair" stroke-dasharray="3 9" opacity=".6">'
               f'<animateTransform attributeName="transform" type="rotate" dur="30s" repeatCount="indefinite" values="0 840 110;360 840 110"/></circle>')
    out.append(F.at(hx, hy, slab, F.tf("scale", [(0, (0.5, 0.5)), *tween(t0, 0.45, (0.5, 0.5), (1.0, 1.0), "back", 6)])))
    # The wordmark, drawn stroke by stroke.
    x0, base, k = 520.0, 330.0, 1.06
    paths, xx, dot = [], 0.0, (0.0, 0.0, 0.0)
    for i, (d, w) in enumerate(_glyphs()):
        ti = t0 + 0.7 + 0.11 * i
        paths.append(f'<path transform="translate({n(xx)} 0)" d="{d}" pathLength="1" stroke-dasharray="1 1">'
                     f'{F.anim("stroke-dashoffset", [(0, 1), *tween(ti, 0.4, 1.0, 0.0, "out", 4)])}</path>')
        if i == 6:
            dot = (x0 + (xx + _H) * k, base - (XH + 10 + S * 0.62) * k, S * 0.62 * k)
        xx += w + 8
    out.append(f'<g transform="translate({n(x0)} {n(base)}) scale({n(k)})" class="glyph">{"".join(paths)}</g>')
    if F.f.kicker:
        kk = F.f.kicker.upper()
        out.append(f'<g>{F.slide(t0 + 1.6, 700, 0, 0.35)}<rect x="{n(x0)}" y="372" width="{n(tracked(kk, 16) + 24)}" height="32" class="red"/>'
                   + F.text(x0 + 14, 394, kk, 16, "t", "paper") + "</g>")

    def slot(t: float) -> tuple[float, float]:
        m = swing(((t - t0) / Ts) % 1.0, 34, -12)
        x, y, _ = P.apply(m, (sx, sy, 10.0))
        return hx + x, hy + y

    land = t0 + 0.5
    pts = [(t, *_lerp((500.0, 300.0 - BALL, 1250.0), (*slot(land), sr), u)) for t, u in tween(t0, 0.5, 0.0, 1.0, "io", 6)]
    t = land
    while t < t0 + 2.6:
        t += 0.12
        pts.append((t, *slot(t), sr))
    a = (*slot(t), sr)
    for i in range(1, 9):
        u = i / 8
        e = EASE["io"](u)
        pts.append((t + 0.55 * u, a[0] + (dot[0] - a[0]) * e, a[1] + (dot[1] - a[1]) * e - 120 * math.sin(math.pi * u), sr + (dot[2] - sr) * e))
    pts.append((t1 - 0.05, dot[0], dot[1], dot[2]))
    F.ball(pts)
    return "".join(out)


def shot_headline(F: Film, t0: float, t1: float) -> str:
    """The headline, a word at a time, slammed down; the ball lands as its full stop, then swells."""
    head = F.f.headline.upper().rstrip(".")
    size, lines = fitlines(head, 880, 92, 40, 3)
    top = (H - size * 1.08 * len(lines)) / 2 + size * 0.8
    body, ex, ey = words_in(F, t0 + 0.15, 60, top, lines, size, hot=lambda w: w.startswith("FLOW"))
    out = [F.bg("paper"), f'<rect x="60" y="{n(top + size * 1.08 * (len(lines) - 1) + size * 0.4)}" height="12" class="ink">'
                          f'{F.anim("width", [(0, 0), *tween(t0 + 0.9, 0.4, 0.0, 300.0, "out", 4)])}</rect>', body]
    if F.f.lead:
        ll = wrap(F.f.lead, 19, 600, 2)
        out.append(f'<g opacity="0">{F.anim("opacity", [(0, 0), (t0 + 1.2, 0), (t0 + 1.5, 1)])}'
                   + "".join(F.text(60 + 320, top + size * 1.08 * (len(lines) - 1) + size * 0.55 + 22 * j, ln, 19, "r", "mute")
                             for j, ln in enumerate(ll)) + "</g>")
    nwords = sum(len(ln.split()) for ln in lines)
    r = size * 0.16
    bx, by = ex + r * 1.6, ey - r
    tl = t0 + 0.15 + 0.09 * nwords + 0.25
    F.ball([(tl - 0.3, bx, -60, r), *[(t, bx, y, r) for t, y in tween(tl - 0.3, 0.3, -60.0, by, "in", 5)][1:],
            *[(t, bx, by, rr) for t, rr in tween(tl, 0.16, r, r * 1.25, "out", 2)][1:],
            *[(t, bx, by, rr) for t, rr in tween(tl + 0.16, 0.2, r * 1.25, r, "back", 3)][1:],
            (t1 - 0.4, bx, by, r), *[(t, x, y, rr) for t, (x, y, rr) in tween(t1 - 0.4, 0.4, (bx, by, r), (500.0, 280.0, 1250.0), "in", 6)][1:]])
    return "".join(out)


def shot_act(i: int, act: str, last: bool) -> Draw:
    """One line of the manifesto, filling the frame, on its own composition."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("red", "paper", "ink")[i % 3]
        ink = flip(ground)
        out = [F.bg(ground)]
        if ground == "red":
            disc = (f'<circle r="230" class="ink"/><rect x="-230" y="-14" width="460" height="28" class="red"/>')
            out.append(F.at(800, 140, disc, F.tf("rotate", [(0, 0.0), (t0, 0.0), (t1, 60.0)]),
                            F.tf("scale", [(0, (0.0, 0.0)), *tween(t0, 0.4, (0.0, 0.0), (1.0, 1.0), "back", 6)])))
        elif ground == "paper":
            band = f'<rect x="-700" y="-70" width="1400" height="140" class="red"/>'
            out.append(f'<g transform="translate(500 300) rotate({n(-ANGLE)})"><g>{F.slide(t0, 1400, 0, 0.35)}{F.drift(t0 + 0.35, t1, -60)}{band}</g></g>')
            ink = "ink"
        else:
            out.append(f'<g>{F.slide(t0 + 0.05, -500, 300, 0.35, "back")}<polygon points="0,{n(H)} 0,{n(H - 330)} 520,{n(H)}" class="red"/></g>')
        size, lines = fitlines(act.upper(), 860, 104, 44, 3)
        top = (H - size * 1.06 * len(lines)) / 2 + size * 0.8
        body, ex, ey = words_in(F, t0 + 0.12, 70, top, lines, size, ink, 1.06, 0.07)
        out.append(f"<g>{F.drift(t0 + 0.4, t1, -26)}{body}</g>")
        if last:
            F.ball([(t1 - 0.9, ex + 30, ey - 26, 0.0), *[(t, ex + 30, ey - 26, r) for t, r in tween(t1 - 0.9, 0.3, 0.0, 22.0, "back", 4)][1:], (t1, ex + 30, ey - 26, 22)])
        return "".join(out)
    return draw


def shot_bumper(num: int, title: str) -> Draw:
    """A section's name, springing up, then the camera flies through it into the dark."""
    def draw(F: Film, t0: float, t1: float) -> str:
        word = title.upper()
        size = min(190.0, 900 / max(capw(word, 1), 1e-6))
        ww = capw(word, size)
        inner = (f'<g transform="translate({n(-ww / 2)} {n(size * 0.35)})">'
                 + blockword(F, 0, 0, word, size, t0 + 0.2, length=ww) + "</g>")
        grow = F.tf("scale", [(0, (0.3, 0.3)), *tween(t0, 0.35, (0.3, 0.3), (1.0, 1.0), "back", 6),
                              (t1 - 0.4, (1.08, 1.08)), *tween(t1 - 0.4, 0.4, (1.08, 1.08), (16.0, 16.0), "in", 6)[1:]])
        out = [F.bg("paper"),
               f'<rect x="0" y="{n(H / 2 - 4)}" height="8" class="red">{F.anim("width", [(0, 0), *tween(t0, 0.5, 0.0, W, "out", 5)])}</rect>',
               F.at(W / 2, H / 2, inner, grow),
               f'<g>{F.slide(t0 + 0.15, 0, -120, 0.3)}<rect x="40" y="40" width="70" height="70" class="red"/>'
               + F.text(75, 90, f"{num:02d}", 34, "k", "paper", "middle") + "</g>",
               f'<rect width="{n(W)}" height="{n(H)}" class="ink" opacity="0">{F.anim("opacity", [(0, 0), (t1 - 0.14, 0), (t1, 1)])}</rect>']
        return "".join(out)
    return draw


def shot_humanize(F: Film, t0: float, t1: float) -> str:
    """The runtime's name, cut deep, and what it does."""
    band = next((b for b in F.f.bands if b.title.lower() == "humanize"), F.f.bands[0])
    word = band.title.upper()
    size = min(170.0, 880 / capw(word, 1))
    ww = capw(word, size)
    out = [F.bg("paper"), f'<g>{F.slide(t0, 0, -400, 0.4, "back")}<rect x="60" y="0" width="40" height="230" class="red"/></g>',
           F.pop(t0 + 0.05, 60 + ww / 2, 290, f'<g transform="translate({n(-ww / 2)} 0)">' + blockword(F, 0, 0, word, size, t0 + 0.3, length=ww) + "</g>", 0.6),
           f'<rect x="60" y="322" height="10" class="red">{F.anim("width", [(0, 0), *tween(t0 + 0.4, 0.5, 0.0, ww, "out", 5)])}</rect>']
    for j, ln in enumerate(wrap(band.about, 26, 880, 2, True)):
        out.append(F.reveal(t0 + 0.6 + 0.25 * j, 60, 360 + 40 * j, 900, 40, F.text(60, 390 + 40 * j, ln, 26, "b"), 0.5))
    return "".join(out)


def shot_tower(F: Film, t0: float, t1: float) -> str:
    """The stack lands slab by slab; then a turn falls through it, and each band speaks as it lands."""
    c = F.c
    bands = F.f.bands[:4]
    iso = P.rot(-36, -28)
    sw, sd, st, gap = 280.0, 160.0, 34.0, 30.0
    tx, ty = 230.0, 150.0
    out = [F.bg("paper")]
    slabs = []
    for k, band in enumerate(bands):
        red = band.title.lower() == "humanize"
        lo, hi = (c["deep"], c["red"]) if red else (c["ink"], P.mix(c["ink"], c["paper"], .5))
        body = P.box(sw, st, sd).draw([iso, iso], 10, (0, 0), 1.0, hi, lo)
        fx = P.apply(iso, (-sw / 2 + 14, 8, sd / 2))
        label = (f'<g transform="matrix({n(iso[0][0])},{n(iso[1][0])},{n(iso[0][1])},{n(iso[1][1])},{n(fx[0])},{n(fx[1])})">'
                 + F.text(0, 0, fit(band.title.upper(), 18, sw - 40, True), 18, "k", "paper") + "</g>")
        oy = k * (st + gap)
        ox, oyy = P.apply(iso, (0, oy, 0))[:2]
        ti = t0 + 0.1 + 0.18 * k
        slabs.append(f'<g transform="translate({n(tx + ox)} {n(ty + oyy)})"><g>{F.slide(ti, 0, -700, 0.35, "back")}{body}{label}</g></g>')
    out.extend(reversed(slabs))
    land0 = t0 + 1.0
    beat = (t1 - land0 - 0.3) / max(len(bands), 1)

    def top(k: int) -> tuple[float, float]:
        x, y, _ = P.apply(iso, (sw * 0.25, -st / 2 + k * (st + gap), sd * 0.2))
        return tx + x, ty + y - 16

    pts = [(land0 - 0.35, top(0)[0], -60, 16.0), *[(t, top(0)[0], y, 16.0) for t, y in tween(land0 - 0.35, 0.35, -60.0, top(0)[1], "in", 5)][1:]]
    for k in range(1, len(bands)):
        a, b = top(k - 1), top(k)
        tk = land0 + beat * k
        pts.append((tk - 0.32, *a, 16.0))
        for i in range(1, 7):
            u = i / 6
            pts.append((tk - 0.32 + 0.32 * u, a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * EASE["in"](u) - 30 * math.sin(math.pi * u), 16.0))
    pts.append((t1, *top(len(bands) - 1), 16.0))
    F.ball(pts)
    hot = lambda s: s.lower().startswith("litellm")  # noqa: E731 -- the runtime's own model call
    for k, band in enumerate(bands):
        a = land0 + beat * k
        b = land0 + beat * (k + 1) if k + 1 < len(bands) else t1 + 0.01
        x0 = 520.0
        title = band.title.upper()
        size = min(54.0, 440 / capw(title, 1))
        panel = [F.pop(a, x0, 120, F.text(0, 0, title, size), 1.6, 0.3),
                 F.reveal(a + 0.12, x0, 140, 460, 60, "".join(F.text(x0, 164 + 22 * j, ln, 17, "r", "mute")
                                                              for j, ln in enumerate(wrap(band.about, 17, 450, 2))), 0.35)]
        cx, cy = x0, 220.0
        for i, (name, note) in enumerate(band.chips[:12]):
            label = name + (f" · {note}" if note else "")
            w = width(label, 16, True) * 0.86 + 18
            if cx + w > W - 30:
                cx, cy = x0, cy + 38
            lit = hot(name)
            chip = (f'<rect width="{n(w)}" height="30" class="{"red" if lit else "chip"}"/>' + F.text(9, 21, label, 16, "b", "paper" if lit else "ink"))
            ti = a + 0.18 + 0.035 * i
            px, py = P.apply(iso, (0, k * (st + gap), 0))[:2]
            out_ = F.tf("translate", [(0, (tx + px - cx, ty + py - cy)), *tween(ti, 0.3, (tx + px - cx, ty + py - cy), (0.0, 0.0), "out", 5)])
            panel.append(f'<g transform="translate({n(cx)} {n(cy)})"><g>{out_}{F.anim("opacity", [(0, 0), (ti, 0), (ti + 0.05, 1)])}{chip}</g></g>')
            cx += w + 8
        if band.down:
            panel.append(F.reveal(a + 0.4, 40, 480, 940, 50, f'<polygon points="40,488 60,488 50,503" class="red"/>'
                                  + F.text(72, 503, fit(band.down, 20, 880), 20, "i"), 0.5))
        out.append(f'<g display="none">{F.show(a, b)}{"".join(panel)}</g>')
    return "".join(out)


def shot_feature(i: int, h3: str, p: str, env: list[tuple[str, str]]) -> Draw:
    """A promise the runtime keeps, and a diagram that keeps it."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("paper", "ink", "paper")[i % 3]
        ink = flip(ground)
        out = [F.bg(ground)]
        size, lines = fitlines(h3.upper(), 400, 56, 30, 3)
        body, _, ey = words_in(F, t0 + 0.05, 50, 120, lines, size, ink, 1.06, 0.07)
        out.append(body)
        out.append(F.reveal(t0 + 0.5, 50, ey + 20, 420, 90, "".join(F.text(50, ey + 46 + 24 * j, ln, 18, "r", "mute" if ground == "paper" else "paper")
                                                                    for j, ln in enumerate(wrap(p, 18, 400, 3))), 0.5))
        key = (h3 + " " + p).lower()
        x, y, w = 520.0, 200.0, 430.0
        if "budget" in key:
            stop = x + w * 0.82
            out += [f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="70" class="chip"/>',
                    f'<rect x="{n(x)}" y="{n(y)}" height="70" class="{ink}">{F.anim("width", [(0, 0), *tween(t0 + 0.3, 1.2, 0.0, stop - x, "io", 6)])}</rect>',
                    f'<rect x="{n(stop)}" y="{n(y - 24)}" width="10" height="118" class="red"/>',
                    F.at(stop - 40, y + 160, '<rect x="-90" y="-36" width="180" height="62" class="red"/>' + F.text(0, 12, "STOP", 38, "k", "paper", "middle"),
                         F.tf("rotate", [(0, -8.0)]), F.tf("scale", [(0, (0.0, 0.0)), (t0 + 1.5, (0.0, 0.0)), *tween(t0 + 1.5, 0.25, (3.0, 3.0), (1.0, 1.0), "back", 5)[0:]]))]
        elif "trace" in key or "clock" in key:
            for j, (a, w_, cls) in enumerate([(0.0, 0.3, ink), (0.32, 0.22, "red"), (0.56, 0.4, ink),
                                              (0.08, 0.18, "red"), (0.4, 0.25, ink), (0.7, 0.26, "red")]):
                out.append(f'<rect x="{n(x + a * w)}" y="{n(y + (j % 3) * 46)}" height="34" class="{cls}">'
                           f'{F.anim("width", [(0, 0), *tween(t0 + 0.2 + a * 1.6, 0.4, 0.0, w_ * w, "out", 4)])}</rect>')
            out.append(f'<rect y="{n(y - 20)}" width="5" height="170" class="red">{F.anim("x", [(0, x), (t0 + 0.2, x), (t0 + 2.2, x + w)])}</rect>')
        else:
            for j, (name, _) in enumerate(env[:4]):
                ti = t0 + 0.25 + 0.22 * j
                out.append(f'<g>{F.slide(ti, 500, 0, 0.3, "back")}<rect x="{n(x)}" y="{n(y - 10 + j * 56)}" width="30" height="36" class="red"/>'
                           + F.text(x + 46, y + 18 + j * 56, fit(name.upper(), 24, w - 50, True), 24, "k", ink) + "</g>")
        return "".join(out)
    return draw


def shot_count(word: str, count: int, note: str) -> Draw:
    """A number, spun into place on a counter, and what it counts."""
    def draw(F: Film, t0: float, t1: float) -> str:
        s = str(count)
        size = 240.0
        adv = size * 0.74
        out = [F.bg("red"), odo(F, 70, 330, s, size, "paper", t0 + 0.05, adv)]
        x = 90 + adv * len(s)
        out.append(F.pop(t0 + 0.35, x, 250, blockword(F, 0, 0, word.upper(), 96, t0 + 0.5, "ink", (F.c["paper"], P.mix(F.c["paper"], F.c["red"], .5)), 7), 1.8, 0.3))
        out.append(F.reveal(t0 + 0.7, x, 280, W - x, 50, F.text(x, 312, note, 26, "b", "paper"), 0.4))
        return "".join(out)
    return draw


def odo(F: Film, x: float, base: float, s: str, size: float, ink: str, t: float, adv: float) -> str:
    """Digits that spin into place like a mechanical counter, from t; anything else stands still."""
    cid = F.uid("odo")
    out = [f'<clipPath id="{cid}"><rect x="{n(x - 10)}" y="{n(base - size * 0.95)}" width="{n(adv * len(s) + 40)}" height="{n(size * 1.2)}"/></clipPath>',
           f'<g clip-path="url(#{cid})">']
    cx, k = x, 0
    line = size * 1.2
    for ch in s:
        w = adv * (0.45 if ch in ".,:" else 1.0)
        if ch.isdigit():
            land = 10 + int(ch)
            strip = "".join(F.text(cx + w / 2, base + line * i, str(i % 10), size, "k", ink, "middle") for i in range(land + 1))
            ti = t + 0.06 * k
            out.append(f'<g>{F.tf("translate", [(0, (0.0, 0.0)), *tween(ti, 0.7 + 0.08 * k, (0.0, 0.0), (0.0, -line * land), "out", 8)])}{strip}</g>')
            k += 1
        else:
            out.append(F.pop(t + 0.5, cx + w / 2, base, F.text(0, 0, ch, size, "k", ink, "middle"), 0.2, 0.3))
        cx += w
    out.append("</g>")
    return "".join(out)


def kind_of(fl: Flow) -> str:
    """What kind of loop a flow is, from its catalogue tag (or, failing that, its name)."""
    s = f"{fl.tag} {fl.name}".lower()
    for key, words in (("lanes", ("lane", "parallel")), ("cleaner", ("clean",)), ("checker", ("check", "review")),
                       ("relay", ("relay", "chase")), ("divide", ("divide", "recursive", "conquer"))):
        if any(w in s for w in words):
            return key
    return "loop"


def cube(F: Film, x: float, y: float, s: float, red: bool) -> str:
    """A small axonometric block: an agent."""
    c = F.c
    top, left, right = ((P.mix(c["red"], "#ffffff", .2), c["red"], c["deep"]) if red else
                        (P.mix(c["ink"], c["paper"], .55), P.mix(c["ink"], c["paper"], .25), c["ink"]))
    h = s * 0.5
    return (f'<polygon points="{n(x)},{n(y - h)} {n(x + s)},{n(y - h - s * .5)} {n(x + 2 * s)},{n(y - h)} {n(x + s)},{n(y - h + s * .5)}" fill="{top}"/>'
            f'<polygon points="{n(x)},{n(y - h)} {n(x + s)},{n(y - h + s * .5)} {n(x + s)},{n(y + s * .9)} {n(x)},{n(y + s * .4)}" fill="{left}"/>'
            f'<polygon points="{n(x + s)},{n(y - h + s * .5)} {n(x + 2 * s)},{n(y - h)} {n(x + 2 * s)},{n(y + s * .4)} {n(x + s)},{n(y + s * .9)}" fill="{right}"/>')


def shot_flow(i: int, total: int, fl: Flow) -> Draw:
    """One flow, at montage speed: its kind stamped, its name sliding through, its loop acted out."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("paper", "ink")[i % 2]
        ink = flip(ground)
        d = t1 - t0
        out = [F.bg(ground)]
        tag = (fl.tag or "A flow").upper()
        out.append(F.at(60, 90, f'<rect x="0" y="-26" width="{n(tracked(tag, 18) + 26)}" height="38" class="red"/>' + F.text(13, 0, tag, 18, "t", "paper"),
                        F.tf("rotate", [(0, -4.0)]), F.tf("scale", [(0, (2.2, 2.2)), *tween(t0, 0.18, (2.2, 2.2), (1.0, 1.0), "back", 4)])))
        out.append(F.text(W - 50, 90, f"{i + 1:02d} / {total:02d}", 22, "t", ink, "end"))
        head, colon, rest = fl.name.partition(":")
        lines = [head + colon, rest] if colon and width(fl.name, 70, True) > 640 else [fl.name]
        size = min(84.0, min(640 / max(width(ln, 1, True), 1e-6) for ln in lines))
        names = "".join(F.text(60, 230 + j * size * 1.02, ln, size, "k", ink) for j, ln in enumerate(lines))
        sx = 160 if i % 2 else -160
        out.append(f'<g>{F.tf("translate", [(0, (sx, 0.0)), *tween(t0, 0.22, (sx, 0.0), (0.0, 0.0), "out", 4), (t1, (-sx * 0.25, 0.0))])}{names}</g>')
        yb = 230 + (len(lines) - 1) * size * 1.02 + 50
        out.append(F.reveal(t0 + 0.2, 60, yb - 28, 900, 70, "".join(F.text(60, yb + 26 * j, ln, 21, "r", "mute" if ground == "paper" else "paper")
                                                                  for j, ln in enumerate(wrap(fl.blurb, 21, 600, 2))), 0.3))
        if fl.roles:
            out.append(F.reveal(t0 + 0.35, 60, H - 70, 600, 40, F.text(60, H - 44, fit("-a " + " · ".join(fl.roles), 18, 560), 18, "b", "red"), 0.25))
        # The loop, acted out at the right.
        ox, oy = 790.0, 440.0
        kind = kind_of(fl)
        ball = F.sh.ball()
        mark = len(out)

        def orb(keys: list) -> str:
            return f'<circle r="13" fill="{ball}">{F.tf("translate", keys)}</circle>'

        if kind in ("relay", "checker"):
            a, b = (ox, oy), (ox + 130, oy - (60 if kind == "checker" else 0))
            out += [cube(F, a[0] - 26, a[1], 26, False), cube(F, b[0] - 26, b[1], 26, True)]
            keys = [(0, (a[0], a[1] - 34))]
            for j in range(2):
                p, q = (a, b) if j % 2 == 0 else (b, a)
                s0 = t0 + 0.1 + j * d * 0.42
                keys += [(t, (x, y)) for t, (x, y) in [(s0 + d * 0.38 * u, (p[0] + (q[0] - p[0]) * EASE["io"](u), p[1] - 34 + (q[1] - p[1]) * u - 70 * math.sin(math.pi * u)))
                                                       for u in (k_ / 8 for k_ in range(9))]]
            out.append(orb(keys))
        elif kind == "lanes":
            for j in range(3):
                yy = oy - 90 + 50 * j
                out.append(f'<line x1="{n(ox - 40)}" y1="{n(yy)}" x2="{n(ox + 190)}" y2="{n(yy)}" class="wire" opacity=".6"/>')
                out.append(orb([(0, (ox - 30, yy)), (t0 + 0.05 * j, (ox - 30, yy)), (t1 - 0.1 * j, (ox + 180, yy))]))
            out.append(f'<rect x="{n(ox + 200)}" y="{n(oy - 110)}" width="12" class="red">{F.anim("height", [(0, 0), (t0, 0), (t1, 120)])}</rect>')
        elif kind == "divide":
            root, kids = (ox + 70, oy - 120), [(ox, oy - 40), (ox + 140, oy - 40)]
            leaves = [(ox - 30, oy + 30), (ox + 30, oy + 30), (ox + 110, oy + 30), (ox + 170, oy + 30)]
            for j, lf in enumerate(leaves):
                kd = kids[j // 2]
                out.append(f'<polyline points="{n(root[0])},{n(root[1])} {n(kd[0])},{n(kd[1])} {n(lf[0])},{n(lf[1])}" class="hair" opacity=".6"/>')
                out.append(orb([(0, root), (t0, root), (t0 + d * 0.35, kd), (t0 + d * 0.7, lf)]))
        elif kind == "cleaner":
            out.append(cube(F, ox - 30, oy, 26, False))
            for j in range(4):
                out.append(f'<rect x="{n(ox + 60)}" y="{n(oy - 20 - 22 * j)}" width="100" height="16" class="{ink}" opacity="0">'
                           f'{F.anim("opacity", [(0, 0), (t0 + 0.1 + 0.12 * j, 1), (t0 + d * 0.75, 0)], True)}</rect>')
            out.append(f'<rect x="{n(ox + 60)}" y="{n(oy - 20)}" width="100" height="16" class="red" opacity="0">{F.anim("opacity", [(0, 0), (t0 + d * 0.75, 1)], True)}</rect>')
        else:
            out.append(f'<ellipse cx="{n(ox + 60)}" cy="{n(oy - 20)}" rx="120" ry="34" class="hair" opacity=".6"/>')
            keys = [(t0 + d * u, (ox + 60 + 120 * math.cos(2 * math.pi * u), oy - 20 + 34 * math.sin(2 * math.pi * u))) for u in (k_ / 16 for k_ in range(17))]
            out += [cube(F, ox + 30, oy - 6, 30, i % 4 == 0), orb([(0, keys[0][1]), *keys])]
        loop = "".join(out[mark:])  # the loop, drawn small, shown large
        return "".join(out[:mark]) + f'<g transform="translate({n(ox)} {n(oy)}) scale(1.6) translate({n(-ox - 40)} {n(-oy + 20)})">{loop}</g>'
    return draw


SOLIDS: list[Callable[[], P.Solid]] = [
    lambda: P.prism(6, 62, 120),   # a column: what the rest stands on
    lambda: P.box(110, 110, 110),
    lambda: P.octahedron(82),
    lambda: P.wedge(150, 104, 96),
    lambda: P.pyramid(4, 90, 140),
    lambda: P.prism(3, 80, 120, "z"),
]


def shot_project(i: int, p: Project) -> Draw:
    """A project: a solid spinning in, its name cut deep, what it is."""
    def draw(F: Film, t0: float, t1: float) -> str:
        c = F.c
        ground = ("paper", "red")[i % 2]
        ink = flip(ground)
        out = [F.bg(ground)]
        red = ground == "paper"
        lo, hi = (c["deep"], c["red"]) if red else (c["ink"], P.mix(c["ink"], c["paper"], .55))
        frames = [P.rot(360 * u + 30 * i, -24 + 10 * math.sin(2 * math.pi * u), 8 * math.sin(4 * math.pi * u)) for u in P.loop_frames(48)]
        solid = SOLIDS[i % len(SOLIDS)]().draw(frames, 6, (0, 0), 1.0, hi, lo, persp=900)
        out.append(f'<ellipse cx="240" cy="470" rx="150" ry="18" class="ink" opacity=".25"/>')
        out.append(F.at(240, 290, solid, F.tf("scale", [(0, (0.2, 0.2)), *tween(t0, 0.45, (0.2, 0.2), (2.0, 2.0), "back", 6), (t1, (2.15, 2.15))]),
                        F.tf("translate", [(0, (0.0, -500.0)), *tween(t0, 0.35, (0.0, -500.0), (0.0, 0.0), "out", 4)])))
        name = p.name.upper()
        size = min(130.0, 480 / max(capw(name, 1), 1e-6))
        x0 = 470.0
        side = (c["red"], c["deep"]) if ground == "paper" else (c["ink"], P.mix(c["ink"], c["red"], .4))
        out.append(F.pop(t0 + 0.15, x0, 250, blockword(F, 0, 0, name, size, t0 + 0.4, ink, side, length=capw(name, size)), 1.8, 0.3))
        sub = p.sub or ""
        if sub:
            sz, lines = fitlines(sub.upper(), 480, 34, 20, 2)
            out.append(F.reveal(t0 + 0.45, x0, 270, 520, 100, "".join(F.text(x0, 310 + sz * 1.1 * j, ln, sz, "k", ink) for j, ln in enumerate(lines)), 0.4))
        if p.lede:
            out.append(f'<g opacity="0">{F.anim("opacity", [(0, 0), (t0 + 0.8, 0), (t0 + 1.1, 1)])}'
                       + "".join(F.text(x0, 400 + 24 * j, ln, 18, "r", "mute" if ground == "paper" else "paper") for j, ln in enumerate(wrap(p.lede, 18, 480, 3))) + "</g>")
        out.append(f'<rect x="{n(x0)}" y="140" height="12" class="{"red" if ground == "paper" else "ink"}">{F.anim("width", [(0, 0), *tween(t0 + 0.2, 0.4, 0.0, 120.0, "out", 4)])}</rect>')
        return "".join(out)
    return draw


def shot_result(i: int, r: Result) -> Draw:
    """A result: the number spins into place, filling the frame; the claim beneath it."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("red", "paper", "ink")[i % 3]
        ink = flip(ground)
        num = r.num
        units = sum(0.45 if ch in ".,:" else 1.0 for ch in num)
        size = min(230.0, 860 / (units * 0.74))
        adv = size * 0.74
        x = (W - adv * units) / 2
        base = 300.0
        out = [F.bg(ground)]
        out.append(f'<g>{F.tf("scale", [(0, (1.0, 1.0)), (t0, (1.0, 1.0)), (t1, (1.05, 1.05))])}'
                   f'{odo(F, x, base, num, size, ink, t0 + 0.02, adv)}</g>')
        out.append(f'<rect x="{n(x)}" y="{n(base + 30)}" height="14" class="{"ink" if ground == "red" else "red"}">'
                   f'{F.anim("width", [(0, 0), *tween(t0 + 0.4, 0.4, 0.0, adv * units, "out", 4)])}</rect>')
        sz, lines = fitlines(r.label.upper(), 860, 34, 20, 2)
        out.append(F.reveal(t0 + 0.5, 40, base + 50, 920, 100, "".join(F.text(W / 2, base + 50 + sz + sz * 1.1 * j, ln, sz, "k", ink, "middle")
                                                                      for j, ln in enumerate(lines)), 0.35))
        return "".join(out)
    return draw


def shot_post(i: int, p: Post) -> Draw:
    """A post: its kind stamped on, its title cascading in."""
    def draw(F: Film, t0: float, t1: float) -> str:
        out = [F.bg("paper"), f'<rect x="0" y="0" width="26" height="{n(H)}" class="ink"/>',
               F.at(W - 40, H + 20, '<circle r="210" class="red"/><rect x="-210" y="-10" width="420" height="20" class="paper"/>',
                    F.tf("translate", [(0, (400.0, 0.0)), *tween(t0, 0.5, (400.0, 0.0), (0.0, 0.0), "out", 5), (t1, (-30.0, 0.0))]),
                    F.tf("rotate", [(0, -120.0), *tween(t0, 0.5, -120.0, 0.0, "out", 5), (t1, 14.0)])),
               f'<g>{F.slide(t0 + 0.1, 0, -300, 0.35, "back")}<polygon points="{n(W)},0 {n(W)},150 {n(W - 260)},0" class="ink"/></g>']
        plate = "red" if p.kind == "NEWS" else "ink"
        out.append(F.at(130, 110, f'<rect x="-80" y="-30" width="160" height="56" class="{plate}"/>' + F.text(0, 10, p.kind, 28, "t", "paper", "middle"),
                        F.tf("rotate", [(0, -6.0)]), F.tf("scale", [(0, (2.6, 2.6)), *tween(t0, 0.22, (2.6, 2.6), (1.0, 1.0), "back", 5)])))
        out.append(F.reveal(t0 + 0.2, 240, 90, 600, 40, F.text(240, 120, p.date.upper(), 22, "t", "mute"), 0.3))
        size, lines = fitlines(p.title.upper(), 880, 66, 30, 3)
        body, _, ey = words_in(F, t0 + 0.25, 60, 230, lines, size, "ink", 1.08, 0.05)
        out.append(f"<g>{F.drift(t0 + 0.5, t1, -20)}{body}</g>")
        if p.by:
            out.append(F.reveal(t0 + 0.7, 60, ey + 20, 900, 40, F.text(60, ey + 50, fit(p.by, 20, 880), 20, "r", "mute"), 0.4))
        return "".join(out)
    return draw


def shot_people(F: Film, t0: float, t1: float) -> str:
    """The people burst out of the ball, then turn over, one after the other, as a wave."""
    c = F.c
    ppl = F.f.people[:24]
    cols = 6 if len(ppl) > 8 else max(len(ppl), 1)
    rows_ = math.ceil(len(ppl) / cols)
    r = min(48.0, 400 / max(rows_, 1) / 2 - 14)
    sx, sy = 150.0, (H - 110) / max(rows_, 1)
    x0 = (W - sx * (cols - 1)) / 2
    out = [F.bg("ink")]
    if F.f.people_intro:
        out.append(F.reveal(t0 + 0.3, 40, 20, 920, 50, F.text(500, 52, fit(sentences(F.f.people_intro)[-1].upper(), 22, 900, True), 22, "k", "paper", "middle"), 0.5))
    F.ball([(t0, 500, 300, 0.0), *[(t, 500, 300, rr) for t, rr in tween(t0, 0.25, 0.0, 60.0, "back", 3)][1:], *[(t, 500, 300, rr) for t, rr in tween(t0 + 0.3, 0.12, 60.0, 0.0, "in", 2)][1:]])
    out.append(f'<clipPath id="facecut"><circle r="{n(r)}"/></clipPath>')
    for i, p in enumerate(ppl):
        cx, cy = x0 + (i % cols) * sx, 90 + r + (i // cols) * sy
        ti = t0 + 0.38 + 0.03 * i
        initials = "".join(w[0] for w in p.name.split()[:2]).upper()
        pic = (f'<image href="{p.face}" x="{n(-r)}" y="{n(-r)}" width="{n(2 * r)}" height="{n(2 * r)}" clip-path="url(#facecut)"/>'
               if p.face else f'<circle r="{n(r)}" fill="{P.mix(c["ink"], c["paper"], .7)}"/>' + F.text(0, 10, initials, 28, "k", "ink", "middle"))
        tf_ = t0 + 2.2 + 0.09 * i
        keys = [(0, (1.0, 1.0)), (tf_, (1.0, 1.0))]
        face, back = [(0, "inline"), (tf_ + 0.15, "none"), (tf_ + 0.45, "inline")], [(0, "none"), (tf_ + 0.15, "inline"), (tf_ + 0.45, "none")]
        for j in range(1, 13):
            u = j / 12
            keys.append((tf_ + 0.6 * u, (max(0.03, abs(math.cos(math.pi * u))), 1.0)))
        coin = (f'<circle r="{n(r + 3)}" fill="{P.mix(c["paper"], c["ink"], .3)}"/>'
                f'<g>{F.anim("display", face, True)}{pic}</g>'
                f'<g display="none">{F.anim("display", back, True)}<circle r="{n(r)}" fill="{P.mix(c["paper"], c["ink"], .45)}"/>'
                + F.text(0, 10, initials, 28, "k", "ink", "middle") + "</g>")
        fly = F.tf("translate", [(0, (500 - cx, 300 - cy)), (ti, (500 - cx, 300 - cy)), *tween(ti, 0.45, (500 - cx, 300 - cy), (0.0, 0.0), "out", 6)])
        out.append(f'<g transform="translate({n(cx)} {n(cy)})"><g>{fly}<g>{F.tf("scale", keys)}{coin}</g>'
                   + F.text(0, r + 26, fit(p.name, 18, sx - 8, True), 18, "b", "paper", "middle") + "</g></g>")
    return "".join(out)


def shot_principles(F: Film, t0: float, t1: float) -> str:
    """How they work: each principle stamped on its plate, pushing the ones before it up the stack."""
    items = F.f.principles[:6]
    out = [F.bg("paper"), F.pop(t0, 50, 90, F.text(0, 0, "HOW WE WORK", 52, "k"), 1.6, 0.3),
           f'<rect x="50" y="108" height="12" class="red">{F.anim("width", [(0, 0), *tween(t0 + 0.1, 0.4, 0.0, 200.0, "out", 4)])}</rect>']
    step = (t1 - t0 - 0.4) / max(len(items), 1)
    for i, s in enumerate(items):
        ti = t0 + 0.3 + step * i
        size = min(40.0, 820 / max(capw(s.upper(), 1), 1e-6))
        w = capw(s.upper(), size) + 50
        plate = ("red", "ink")[i % 2]
        body = (f'<rect x="{n(-w / 2)}" y="{n(-size * 0.95)}" width="{n(w)}" height="{n(size * 1.5)}" class="{plate}"/>'
                + F.text(0, size * 0.3, s.upper(), size, "k", "paper", "middle", f' textLength="{n(w - 50)}" lengthAdjust="spacingAndGlyphs"'))
        ys = [(0, (0.0, 0.0))]
        sc = [(0, (0.0, 0.0)), (ti, (0.0, 0.0)), *tween(ti, 0.25, (1.8, 1.8), (1.0, 1.0), "back", 5)]
        for j in range(i + 1, len(items)):
            tj = t0 + 0.3 + step * j
            k = j - i
            ys += tween(tj, 0.25, (0.0, -68.0 * (k - 1)), (0.0, -68.0 * k), "out", 4)
            sc += tween(tj, 0.25, (0.86 ** (k - 1),) * 2, (0.86 ** k,) * 2, "out", 4)
        rot = -2.0 if i % 2 else 2.0
        out.append(F.at(500, 470, f'<g transform="rotate({n(rot)})">{body}</g>', F.tf("translate", ys), F.tf("scale", sc)))
    return "".join(out)


def shot_outro(F: Film, t0: float, t1: float) -> str:
    """Red. The H in paper, the site's name slammed down, the ball drops home -- then an ink plane
    sweeps the frame, and it all begins again."""
    c = F.c
    out = [F.bg("red")]
    hx, hy, hh = 210.0, 250.0, 260.0
    if 'id="hshape"' not in "".join(F.sh.defs):
        mark_defs(F.sh, F.f.logo, HEIGHT_H)
    sx, sy, sr = _slot(F, hh)
    Ts = 10.0
    frames = [swing(u, 30, -10) for u in P.loop_frames(48)]
    css, slab = P.extrude("ho", "hshape", frames, Ts, (0, 0), hh * 0.28, 20, (c["ink"], P.mix(c["ink"], c["red"], .5)), "paper")
    F.sh.css.append(css)
    out.append(F.at(hx, hy, f'<g transform="scale({n(hh / HEIGHT_H)})">{slab}</g>', F.tf("scale", [(0, (0.3, 0.3)), *tween(t0, 0.4, (0.3, 0.3), (1.0, 1.0), "back", 6)])))
    site = SITE.split("//", 1)[-1].upper()
    size = min(96.0, 560 / capw(site, 1))
    out.append(F.pop(t0 + 0.3, 400, 260, blockword(F, 0, 0, site, size, t0 + 0.5, "paper", (c["ink"], P.mix(c["ink"], c["red"], .4)), length=capw(site, size)), 1.8, 0.3))
    out.append(F.reveal(t0 + 0.7, 400, 280, 560, 40, F.text(404, 312, "GITHUB.COM/HUMANFIA", 24, "t", "ink"), 0.4))
    for j, (what, href) in enumerate(F.f.contact[:3]):
        where = href.split("//", 1)[-1].rstrip("/")
        ti = t0 + 1.2 + 0.15 * j
        x = 40 + j * 312
        out.append(f'<g>{F.slide(ti, 0, 220, 0.35, "back")}<rect x="{n(x)}" y="400" width="300" height="110" class="ink"/>'
                   + "".join(F.text(x + 16, 432 + 22 * k, ln, 17, "b", "paper") for k, ln in enumerate(wrap(what, 17, 270, 2)))
                   + F.text(x + 16, 494, fit(where.upper(), 13, 270), 13, "t", "red") + "</g>")

    def slot(t: float) -> tuple[float, float]:
        m = swing(((t - t0) / Ts) % 1.0, 30, -10)
        x, y, _ = P.apply(m, (sx * hh / HEIGHT_H, sy * hh / HEIGHT_H, 8.0))
        return hx + x, hy + y

    rr = sr * hh / HEIGHT_H
    land = t0 + 1.0
    pts = [(land - 0.4, slot(land)[0], -60, rr), *[(t, slot(t)[0], y, rr) for t, y in tween(land - 0.4, 0.4, -60.0, slot(land)[1], "in", 5)][1:]]
    t = land
    while t < t1 - 0.1:
        t += 0.15
        pts.append((t, *slot(t), rr))
    F.ball([(t_, x, y, r_) for t_, x, y, r_ in pts])
    F.ball_ink = (land - 0.4, t1)
    out.append(f'<g>{F.tf("translate", [(0, (1500.0, 0.0)), (t1 - 0.45, (1500.0, 0.0)), (t1, (0.0, 0.0))])}'
               f'<polygon points="{n(-200)},0 {n(W + 200)},0 {n(W + 200)},{n(H)} {n(-200 - H * SLOPE * 2)},{n(H)}" class="ink"/></g>')
    return "".join(out)


def _slot(F: Film, hh: float) -> tuple[float, float, float]:
    vx, vy, vw, vh = F.f.logo.viewbox
    s = HEIGHT_H / vh
    dx, dy, dr = F.f.logo.dot if F.f.logo.dot else (vx + vw * 0.875, vy + vh * 0.11, vw * 0.125)
    return (dx - vx - vw / 2) * s, (dy - vy - vh / 2) * s, dr * s


def storyboard(f: Facts) -> list[Shot]:
    """The cut: a section is in only if the site gave it something to say."""
    s = [Shot("drop", 2.8, shot_drop), Shot("mark", 3.6, shot_mark)]
    if f.headline:
        s.append(Shot("headline", 3.4, shot_headline, "whip"))
    for i, act in enumerate(f.acts[:5]):
        s.append(Shot(f"act{i}", 2.5, shot_act(i, act, i == len(f.acts[:5]) - 1), "punch"))
    num = 0

    def bump(title: str) -> None:
        nonlocal num
        num += 1
        s.append(Shot(f"bump-{title}", 1.5, shot_bumper(num, title)))

    if f.bands:
        bump("The runtime")
        s.append(Shot("humanize", 2.4, shot_humanize))
        s.append(Shot("tower", 1.4 + 1.3 * len(f.bands[:4]), shot_tower, "whip"))
        env = next((b.chips for b in f.bands if b.title.lower().startswith("environment")), [])
        for i, (h3, p) in enumerate(f.features[:3]):
            s.append(Shot(f"feature{i}", 2.6, shot_feature(i, h3, p, env), "punch"))
    if f.flows:
        bump("The flows")
        s.append(Shot("flows", 2.2, shot_count("Flows", len(f.flows), "loops around the agents")))
        for i, fl in enumerate(f.flows):
            s.append(Shot(f"flow{i}", 1.1, shot_flow(i, len(f.flows), fl)))
    if f.projects:
        bump("Projects")
        for i, p in enumerate(f.projects[:6]):
            s.append(Shot(f"project{i}", 2.8, shot_project(i, p), "whip"))
    if f.results:
        bump("Results")
        for i, r in enumerate(f.results[:12]):
            s.append(Shot(f"result{i}", 1.6, shot_result(i, r), "punch"))
    if f.posts:
        bump("Latest")
        for i, p in enumerate(f.posts[:5]):
            s.append(Shot(f"post{i}", 2.2, shot_post(i, p), "rise"))
    if f.people:
        bump("The people")
        s.append(Shot("people", 5.6, shot_people))
    if f.principles:
        s.append(Shot("principles", 1.0 + 1.3 * len(f.principles[:6]), shot_principles, "whip"))
    s.append(Shot("outro", 6.5, shot_outro))
    return s


def film(theme: str, f: Facts) -> str:
    """The banner: every shot on one clock, cut together, with the ball on top of them all."""
    plan = storyboard(f)
    T = sum(s.seconds for s in plan)
    F = Film(theme, f, T)
    F.ball_ink = None
    layers, t = [], 0.0
    nexts = [s.enter for s in plan[1:]] + ["cut"]
    for s, nxt in zip(plan, nexts):
        t0, t1 = t, t + s.seconds
        body = s.draw(F, t0, t1)
        a, b = t0, t1
        moves = []
        if s.enter == "whip":
            a = t0 - 0.16
            moves.append(F.tf("translate", [(0, (W + 40, 0.0)), *tween(a, 0.34, (W + 40, 0.0), (0.0, 0.0), "out", 6)]))
        elif s.enter == "punch":
            moves.append(F.tf("scale", [(0, (1.18, 1.18)), *tween(t0, 0.22, (1.18, 1.18), (1.0, 1.0), "out", 4)]))
        elif s.enter == "rise":
            moves.append(F.tf("translate", [(0, (0.0, H)), *tween(t0, 0.3, (0.0, H), (0.0, 0.0), "out", 5)]))
        if nxt == "whip":
            moves.append(F.tf("translate", [(0, (0.0, 0.0)), *tween(t1 - 0.16, 0.16, (0.0, 0.0), (-W - 40, 0.0), "in", 4)]))
            b = t1 + 0.18
        inner = body
        for m in moves:
            inner = (f'<g transform="translate({n(W / 2)} {n(H / 2)})"><g>{m}<g transform="translate({n(-W / 2)} {n(-H / 2)})">{inner}</g></g></g>'
                     if "scale" in m[:80] else f"<g>{m}{inner}</g>")
        layers.append(f'<g display="{"inline" if a <= 0 else "none"}">{F.show(a, b)}{inner}</g>')
        if nxt == "whip":  # the whip's speed lines
            streaks = "".join(f'<rect x="0" y="{n(60 + 90 * k)}" width="{n(300 + 120 * (k % 3))}" height="{n(6 + 4 * (k % 2))}" class="{"red" if k % 2 else "ink"}"/>'
                              for k in range(5))
            layers.append(f'<g display="none">{F.show(t1 - 0.2, t1 + 0.2)}<g>{F.tf("translate", [(0, (W, 0.0)), (t1 - 0.2, (W, 0.0)), (t1 + 0.2, (-700.0, 0.0))])}{streaks}</g></g>')
        t = t1
    # The ball: one actor, on top of every shot it is in.
    keys = sorted(F.ball_keys, key=lambda k: k[0])
    on = [(0.0, "0")]
    for a, b in sorted(F.ball_on):
        on += [(a, "1"), (b, "0")]
    xs = [(tt, v[0]) for tt, v in keys]
    ys = [(tt, v[1]) for tt, v in keys]
    rs = [(tt, v[2]) for tt, v in keys]
    fill = F.sh.ball()
    motion = F.anim("cx", xs) + F.anim("cy", ys) + F.anim("r", rs)
    if F.ball_ink:  # at the end the ball is ink, on red
        a, b = F.ball_ink
        red_on = [(tt, v if not (a <= tt < b) else "0") for tt, v in on] + [(a, "0"), (b, "0")]
        red_on = sorted(red_on, key=lambda k: k[0])
        ink_on = [(0.0, "0"), (a, "1"), (b, "0")]
        ball = (f'<circle r="0" fill="{fill}">{motion}{F.anim("opacity", red_on, True)}</circle>'
                f'<circle r="0" class="ink">{motion}{F.anim("opacity", ink_on, True)}</circle>')
    else:
        ball = f'<circle r="0" fill="{fill}">{motion}{F.anim("opacity", on, True)}</circle>'
    return F.sh.render("".join(layers) + ball)

README = """<a href="{site}">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./humanfia-portfolio-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./humanfia-portfolio-light.svg">
    <img src="./humanfia-portfolio-light.svg" width="100%" alt="{alt}" />
  </picture>
</a>
"""


def readme(f: Facts) -> str:
    alt = (f"Humanfia: {f.headline or 'we build the flow around the agents'} A tour, in one shot, of the mark, "
           "the projects, the runtime, the flows, the results, the latest news and the people, generated from humanfia.ai.")
    return README.format(site=SITE, alt=esc(" ".join(alt.split())))


# ----------------------------------------------------------------------------------------- main

def main() -> None:
    themes = [os.environ["THEME"]] if os.environ.get("THEME") else ["light", "dark"]
    facts = gather()
    for theme in themes:
        out = PROFILE / f"humanfia-portfolio-{theme}.svg"
        out.write_text(film(theme, facts), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    (PROFILE / "README.md").write_text(readme(facts), encoding="utf-8")
    if (PROFILE / ART).exists():
        shutil.rmtree(PROFILE / ART)  # the poster wall this replaced


if __name__ == "__main__":
    main()
