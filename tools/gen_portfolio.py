#!/usr/bin/env python3
"""Generate the Humanfia org profile from humanfia.ai: a constructivist poster wall you can click.

Nothing about Humanfia is written down here. Every run reads the live sites and lays out what it
finds, as one README of many small posters, each a link:

    the mark        /logo.svg, extruded into a slab that turns in space, its red ball orbiting it
    the projects    the nav's Projects menu: a turning solid, the name and its line, per project
    the runtime     the Humanize docs' "how it fits together" bands, as a tower a turn falls through,
                    and the home page's features, each with a working diagram
    the flows       the /flows/ catalogue: one card per flow, its pattern acted out
    the results     the home page's tiles: counters that spin into place, each linked to its post
    the latest      /news/feed.rss and /blog/feed.rss, one strip per post
    the people      About's roster as coins that flip, its principles on a turning prism
    the address     About's contacts

A section whose source the site does not have (a 404 or 410, or markup without the parts it needs)
is left out. Any other failure -- a 403, a 5xx, a timeout -- stops the run, so a bad fetch never
overwrites a good profile.

GitHub shows README images through <img>: no JavaScript, no hover, no web fonts, nothing loaded.
So the interaction is the README's own -- every poster is a link, and the long sections fold into
<details> -- and the motion is SMIL and CSS keyframes, played back from geometry this script
rotates and projects itself (tools/proun.py). Each poster comes in a light and a dark version.

    python3 tools/gen_portfolio.py              # both themes
    THEME=dark python3 tools/gen_portfolio.py   # one theme (light|dark)
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
ART = "art"  # profile/art/<theme>/<poster>.svg
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


# ------------------------------------------------------------------------------------ the posters

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


def hero(theme: str, f: Facts) -> str:
    """The mark as a Proun: the H pushed back into a red slab, turning slowly over a floor that runs
    toward you; its ball leaves the slot, orbits the slab -- behind it, then in front -- and drops
    home. The wordmark, the headline and the manifesto stand beside it."""
    W, H, T = 1000.0, 520.0, 24.0
    sh = Sheet(theme, W, H, "Humanfia" + (f" — {f.headline}" if f.headline else ""))
    c = sh.c
    out = []
    hx, hy, hh = 236.0, 236.0, 290.0
    _, (sx, sy, sr) = mark_defs(sh, f.logo, hh)

    # The construction: a turning dashed circle, a red plane drifting on the diagonal, hairlines.
    out.append(f'<circle cx="840" cy="96" r="210" class="hair" stroke-dasharray="3 9" opacity=".5">'
               f'<animateTransform attributeName="transform" type="rotate" dur="{n(T * 2)}s" repeatCount="indefinite" '
               f'values="0 840 96;360 840 96"/></circle>')
    out.append(f'<g><polygon points="{n(W)},0 {n(W)},250 {n(W - 300)},0" class="red"/>'
               + P.smil_move([(0, 0, 0), (0.5, -18, 18 * SLOPE), (1, 0, 0)], T) + "</g>")
    for i, (x0, y0) in enumerate(((0, 182), (420, 516), (520, 0))):
        out.append(f'<line x1="{x0 - 400}" y1="{n(y0 + 400 * SLOPE)}" x2="{x0 + 900}" y2="{n(y0 - 900 * SLOPE)}" class="hair" opacity="{.18 + .06 * i}"/>')

    # The floor: rays to a vanishing point, and rungs that come toward you and fade.
    horizon, vp = 392.0, hx
    floor = [f'<clipPath id="floor"><rect x="0" y="{n(horizon + 12)}" width="{n(W)}" height="{n(H)}"/></clipPath>',
             '<g clip-path="url(#floor)" opacity=".5">']
    for k in range(-9, 10):
        floor.append(f'<line x1="{n(vp)}" y1="{n(horizon)}" x2="{n(vp + k * 140)}" y2="{n(H)}" class="hair"/>')
    phases = P.loop_frames(48)
    for i in range(8):
        ys, ops = [], []
        for u in phases:
            z = 1.0 - ((i / 8 + u * 2) % 1.0)          # 1 far .. 0 near
            depth = 1.2 + 9 * z
            ys.append(n(horizon + 120 / depth))
            ops.append(n(min(1.0, 4 * (1 - z)) * min(1.0, 5 * z)))
        floor.append(f'<line x1="0" x2="{n(W)}" y1="0" y2="0" class="hair">'
                     f'{P.smil("y1", ys, T)}{P.smil("y2", ys, T)}{P.smil("opacity", ops, T)}</line>')
    floor.append("</g>")
    out.append("".join(floor))

    # The slab's shadow, breathing with its turn.
    sh.defs.append('<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>')
    frames = [swing(u) for u in P.loop_frames(60)]
    rx = [n(100 + 46 * abs(m[0][0])) for m in frames]
    out.append(f'<ellipse cx="{n(hx + 16)}" cy="{n(horizon + 40)}" rx="140" ry="14" class="ink" opacity=".35" filter="url(#soft)">'
               f'{P.smil("rx", rx, T)}</ellipse>')

    # The slab: the H, pushed back.
    css, slab = P.extrude("hx", "hshape", frames, T, (hx, hy), hh * 0.3, 28, (c["red"], c["deep"]), "ink")
    sh.css.append(css)

    # The ball: in its slot, riding the turn; then out, round the slab on a tilted ring, and home.
    tilt = P.rot(0, -16)
    ring_r = 236.0

    def slot(u: float) -> P.Vec:
        x, y, z = P.apply(swing(u), (sx, sy, 10.0))
        return (hx + x, hy + y, z)

    def ring(th: float) -> P.Vec:
        x, y, z = P.apply(tilt, (ring_r * math.cos(th), 0, ring_r * math.sin(th)))
        return (hx + x, hy - 36 + y, z)

    def hop(a: P.Vec, b: P.Vec, e: float, lift: float = 90) -> P.Vec:
        return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e - lift * math.sin(math.pi * e), a[2] + (b[2] - a[2]) * e)

    def where(u: float) -> tuple[P.Vec, float]:
        if u < 0.30:
            return slot(u), 1.0
        if u < 0.38:
            return hop(slot(u), ring(0), P.ease((u - 0.30) / 0.08)), 1.0
        if u < 0.80:
            return ring(-2 * math.pi * P.ease((u - 0.38) / 0.42)), 1.0
        if u < 0.88:
            return hop(ring(0), slot(u), P.ease((u - 0.80) / 0.08)), 1.0
        k = (u - 0.88) / 0.12                        # the landing: a squash, mechanical not rubbery
        return slot(u), 1.0 - 0.12 * math.sin(math.pi * min(1.0, k * 4)) * (k < 0.25)

    bx, by, br, front, back, shx, sho = [], [], [], [], [], [], []
    for u in P.loop_frames(120):
        (x, y, z), squash = where(u)
        bx.append(n(x))
        by.append(n(y))
        br.append(n(sr * (1 + z / 900) * squash))
        in_slot = u < 0.30 or u >= 0.88
        ahead = in_slot or z >= 0
        front.append("1" if ahead else "0")
        back.append("0" if ahead else "1")
        shx.append(n(x))
        sho.append(n(max(0.0, 0.3 - (horizon + 40 - y) / 1200)))
    ball = sh.ball()

    def orb(vis: list[str], lag: float = 0.0, alpha: float = 1.0) -> str:
        # A lagging copy, fainter, is the ball's afterimage: motion read as a smear, as in print.
        return (f'<g opacity="{n(alpha)}"><circle cx="{bx[0]}" cy="{by[0]}" r="{br[0]}" fill="{ball}">{P.smil("cx", bx, T, begin=lag)}'
                f'{P.smil("cy", by, T, begin=lag)}{P.smil("r", br, T, begin=lag)}{P.smil("opacity", vis, T, True, lag)}</circle></g>')

    out.append(f'<ellipse cy="{n(horizon + 40)}" rx="26" ry="6" class="ink" filter="url(#soft)">'
               f'{P.smil("cx", shx, T)}{P.smil("opacity", sho, T)}</ellipse>')
    out.append(orb(back, .16, .14) + orb(back, .08, .3) + orb(back) + slab + orb(front, .16, .14) + orb(front, .08, .3) + orb(front))
    # A small red wedge floats between the mark and the words, turning on its own clock.
    spin = [P.rot(360 * u, 30 + 12 * math.sin(2 * math.pi * u), 20) for u in P.loop_frames(60)]
    out.append(f'<g>{P.smil_move([(0, 0, 0), (.5, 0, -16), (1, 0, 0)], T / 3)}'
               + P.wedge(64, 44, 40).draw(spin, T / 2, (452, 330), 1.0, c["red"], c["deep"], persp=700) + "</g>")

    # The words: the kicker on red, the wordmark printed twice a hair out of register, the headline.
    x0 = 520.0
    if f.kicker:
        k = f.kicker.upper()
        out.append(f'<rect x="{n(x0)}" y="64" width="{n(tracked(k, 15) + 22)}" height="28" class="red"/>'
                   + sh.text(x0 + 14, 84, k, 15, "t", "paper"))
    word, (dx, dy, dr), ww = wordmark(x0, 196, 1.08)
    redword, _, _ = wordmark(x0, 196, 1.08, "glyphr")
    out.append(f'<g opacity=".55">{P.smil_move([(0, 3, 2), (.25, -2, 3), (.5, 2, -2), (.75, -3, -1), (1, 3, 2)], 7)}{redword}</g>')
    out.append(word + f'<circle cx="{n(dx)}" cy="{n(dy)}" r="{n(dr)}" fill="{ball}"/>')
    y = 252.0
    for i, line in enumerate(wrap(f.headline.upper(), 30, W - x0 - 40, 3, True)):
        out.append(sh.text(x0, y, line, 30))
        y += 38
    out.append(f'<rect x="{n(x0)}" y="{n(y - 22)}" height="8" class="red">'
               + P.smil_keys("width", [(0, "0"), (.06, "0"), (.14, "220"), (.94, "220"), (1, "0")], T) + "</rect>")
    for line in wrap(f.lead, 16, W - x0 - 40, 3):
        out.append(sh.text(x0, y + 16, line, 16, "r", "mute"))
        y += 22

    # The manifesto, running along an ink band on a shallow diagonal at the foot.
    if f.acts:
        gap = "\u00a0\u00a0\u00a0■\u00a0\u00a0\u00a0"  # no-break spaces: SVG would collapse plain ones at the seam
        s = gap.join(a.upper() for a in f.acts) + gap
        run = width(s, 17, True)
        reps = math.ceil((W + 200) / run) + 1
        sh.css.append(f"@keyframes run{{to{{transform:translateX(-{n(run)}px)}}}}.run{{animation:run {n(run / 40)}s linear infinite}}")
        out.append(f'<g transform="rotate({n(-ANGLE / 3)} {n(W / 2)} {n(H - 30)})"><rect x="-80" y="{n(H - 56)}" width="{n(W + 160)}" height="40" class="ink"/>'
                   f'<g class="run">' + "".join(sh.text(-60 + i * run, H - 30, s, 17, "k", "paper", extra=f' textLength="{n(run)}" lengthAdjust="spacing"')
                                                for i in range(reps)) + "</g></g>")
    out.append(sh.grain())
    return sh.render("".join(out))


def header(theme: str, num: int, title: str, note: str) -> str:
    """A section's head: its number on a red block, its name, what to do with it, and a rule with
    a block travelling along it -- the poster's clock."""
    W, H = 1000.0, 92.0
    sh = Sheet(theme, W, H, title)
    out = [f'<rect x="0" y="18" width="58" height="58" class="red"/>', sh.text(29, 60, f"{num:02d}", 26, "k", "paper", "middle"),
           sh.text(78, 56, title.upper(), 32), sh.text(W, 56, fit(note, 16, W - width(title.upper(), 32, True) - 120), 16, "i", "mute", "end"),
           f'<rect x="78" y="74" width="{n(W - 78)}" height="2" class="ink" opacity=".25"/>',
           f'<rect y="72" width="56" height="6" class="red">{P.smil("x", ["78", n(W - 56)], 9)}</rect>']
    return sh.render("".join(out))


SOLIDS: list[Callable[[], P.Solid]] = [
    lambda: P.prism(6, 62, 120),   # a column: what the rest stands on
    lambda: P.box(110, 110, 110),
    lambda: P.octahedron(82),
    lambda: P.wedge(150, 104, 96),
    lambda: P.pyramid(4, 90, 140),
    lambda: P.prism(3, 80, 120, "z"),
]


def project_tile(theme: str, p: Project, i: int) -> str:
    """A project: a solid turning in space over its shadow, its name, and what it is."""
    W, H, T = 300.0, 400.0, 14.0
    sh = Sheet(theme, W, H, f"{p.name}: {p.sub}" if p.sub else p.name)
    c = sh.c
    red = i % 2 == 0
    solid = SOLIDS[i % len(SOLIDS)]()
    frames = [P.rot(360 * u + 25 * i, -24 + 10 * math.sin(2 * math.pi * u), 8 * math.sin(4 * math.pi * u)) for u in P.loop_frames(72)]
    lo, hi = (c["deep"], c["red"]) if red else (c["ink"], P.mix(c["ink"], c["paper"], .55))
    sh.defs.append('<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>')
    out = [f'<polygon points="{n(W)},0 {n(W)},{n(110)} {n(W - 110 / SLOPE * .5)},0" class="{"ink" if red else "red"}" opacity=".9"/>',
           f'<ellipse cx="150" cy="218" rx="74" ry="12" class="ink" opacity=".3" filter="url(#soft)"/>',
           f'<g>{P.smil_move([(0, 0, 0), (.5, 0, -10), (1, 0, 0)], T / 2)}{solid.draw(frames, T, (150, 128), 1.0, hi, lo, persp=900)}</g>',
           f'<rect x="24" y="252" width="40" height="8" class="red"/>',
           sh.text(24, 302, p.name.upper(), round(fitsize(p.name.upper(), 40, W - 48, least=26), 1))]
    for j, line in enumerate(wrap(p.sub or p.lede, 22, W - 48, 2, True)):
        out.append(sh.text(24, 336 + 27 * j, line, 22, "b", "mute"))
    out.append(f'<g>{P.smil_move([(0, 0, 0), (.08, 8, 0), (.16, 0, 0)], 4)}{sh.text(W - 22, H - 18, "OPEN →", 15, "t", "red", "end")}</g>')
    out.append(f'<rect x="1" y="1" width="{n(W - 2)}" height="{n(H - 2)}" class="hair" opacity=".35"/>')
    return sh.render("".join(out))


def runtime(theme: str, f: Facts) -> str:
    """The docs' bands as a tower of slabs that opens and closes; a turn -- the red ball -- drops
    from slab to slab, and each band lights on the right as it lands there."""
    W, T = 1000.0, 16.0
    bands = f.bands[:4]
    H = max(440.0, 40.0 + 118 * len(bands))
    sh = Sheet(theme, W, H, "Humanize: how it fits together")
    c = sh.c
    iso = P.rot(-36, -28)
    sw, sd, st = 300.0, 170.0, 36.0
    tx, ty = 250.0, 150.0
    phases = P.loop_frames(64)
    gap = [26 + 18 * math.sin(2 * math.pi * u) ** 2 for u in phases]
    out, slabs, panel = [], [], []
    for k, band in enumerate(bands):
        red = band.title.lower() == "humanize" or (k == 1 and not any(b.title.lower() == "humanize" for b in bands))
        lo, hi = (c["deep"], c["red"]) if red else (c["ink"], P.mix(c["ink"], c["paper"], .5))
        body = P.box(sw, st, sd).draw([iso], T, (0, 0), 1.0, hi, lo)
        fx = P.apply(iso, (-sw / 2 + 16, 8, sd / 2))
        label = (f'<g transform="matrix({n(iso[0][0])},{n(iso[1][0])},{n(iso[0][1])},{n(iso[1][1])},{n(fx[0])},{n(fx[1])})">'
                 + sh.text(0, 0, fit(band.title.upper(), 19, sw - 40, True), 19, "k", "paper") + "</g>")
        moves = [(u, *[v * (k * (st + g)) for v in (iso[0][1], iso[1][1])]) for u, g in zip(phases, gap)]
        slabs.append(f'<g transform="translate({n(tx)} {n(ty)})"><g>{P.smil_move(moves, T)}{body}{label}</g></g>')
    out.extend(reversed(slabs))  # the lowest slab first, so each one above covers it

    # The ball: a hop down to each slab in turn, then back up to the top on a red trace.
    def top(k: int, u: float) -> tuple[float, float]:
        g = 26 + 18 * math.sin(2 * math.pi * u) ** 2
        x, y, _ = P.apply(iso, (sw * 0.28, -st / 2 + k * (st + g), sd * 0.22))
        return tx + x, ty + y - 17

    stops = [0.06 + 0.2 * k for k in range(len(bands))]
    bxs, bys = [], []
    for u in P.loop_frames(128):
        k = max((j for j, s in enumerate(stops) if u >= s), default=-1)
        if k < 0:      # rising back to the top from the last slab
            a, b, e = top(len(bands) - 1, u), top(0, u), 0.5 + 0.5 * u / stops[0]
            lift = 0.0
        elif u < stops[k] + 0.06 and k > 0:
            a, b, e = top(k - 1, u), top(k, u), P.ease((u - stops[k]) / 0.06)
            lift = 50.0
        elif k == len(bands) - 1 and u > 0.92:
            a, b, e = top(k, u), top(0, u), 0.5 * (u - 0.92) / 0.08
            lift = 0.0
        else:
            a = b = top(k, u)
            e, lift = 0.0, 0.0
        bxs.append(n(a[0] + (b[0] - a[0]) * e))
        bys.append(n(a[1] + (b[1] - a[1]) * e - lift * math.sin(math.pi * e)))
    out.append(f'<circle r="15" fill="{sh.ball()}" cx="{bxs[0]}" cy="{bys[0]}">{P.smil("cx", bxs, T)}{P.smil("cy", bys, T)}</circle>')

    # The panel: each band's name, what it is, its parts; lit while the turn is on its slab.
    x0, y = 560.0, 34.0
    hot = lambda s: s.lower().startswith("litellm")  # noqa: E731 -- the runtime's own model call
    for k, band in enumerate(bands):
        on_ = stops[k] + (0.05 if k else 0.0)
        off = stops[k + 1] + 0.05 if k + 1 < len(bands) else 0.92
        lit = P.smil_keys("opacity", [(0, "0"), (on_, "1"), (off, "0")], T, discrete=True)
        panel.append(f'<rect x="{n(x0 - 22)}" y="{n(y)}" width="8" height="94" class="red" opacity="0">{lit}</rect>')
        panel.append(sh.text(x0, y + 20, band.title.upper(), 20) + sh.text(x0 + width(band.title.upper(), 20, True) * .92 + 12, y + 20,
                                                                         fit(band.about, 14, W - x0 - width(band.title.upper(), 20, True) - 40), 14, "r", "mute"))
        ch, _ = chips(sh, x0, y + 34, band.chips, W - x0 - 24, 2, hot, 13)
        panel.append(ch)
        dash = f'<line x1="{n(tx + 160)}" y1="{n(ty + k * (st + 30) + 10)}" x2="{n(x0 - 30)}" y2="{n(y + 14)}" class="wire" opacity=".35" stroke-width="1.5"/>'
        panel.append(dash)
        y += 118
    sh.css.append("@keyframes flow{to{stroke-dashoffset:-36}}.wire{animation:flow 1.2s linear infinite}")
    out.extend(panel)
    # What passes down from each band, said under the tower while the turn falls through it.
    for k, band in enumerate(bands):
        if not band.down:
            continue
        on_ = stops[k]
        off = stops[k + 1] if k + 1 < len(bands) else 0.92
        out.append(f'<g opacity="0">{P.smil_keys("opacity", [(0, "0"), (on_, "1"), (off, "0")], T, discrete=True)}'
                   f'<polygon points="40,{n(H - 44)} 58,{n(H - 44)} 49,{n(H - 30)}" class="red"/>'
                   + sh.text(70, H - 30, fit(band.down, 16, 470), 16, "i", "ink") + "</g>")
    out.append(sh.grain())
    return sh.render("".join(out))


def features(theme: str, f: Facts) -> str:
    """The runtime's promises, each with a working diagram: a budget meter that stops the run at
    its line, every turn on one clock under a sweeping cursor, and the places the work can land."""
    W, H, T = 1000.0, 330.0, 12.0
    sh = Sheet(theme, W, H, "What Humanize keeps")
    feats = f.features[:3]
    cw = (W - 64 - 40 * (len(feats) - 1)) / max(len(feats), 1)
    env = next((b.chips for b in f.bands if b.title.lower().startswith("environment")), [])
    out = []
    for i, (h3, p) in enumerate(feats):
        x = 32 + i * (cw + 40)
        out.append(f'<rect x="{n(x)}" y="20" width="{n(cw)}" height="6" class="ink"/>')
        out.extend(sh.text(x, 56 + 24 * j, ln, 19) for j, ln in enumerate(wrap(h3.upper(), 19, cw, 2, True)))
        out.extend(sh.text(x, 112 + 21 * j, ln, 15, "r", "mute") for j, ln in enumerate(wrap(p, 15, cw, 3)))
        dy, key = 200, (h3 + " " + p).lower()
        if "budget" in key:
            stop = x + cw * 0.84
            out += [f'<rect x="{n(x)}" y="{dy}" width="{n(cw)}" height="38" class="chip"/>',
                    f'<rect x="{n(x)}" y="{dy}" height="38" class="ink">{P.smil_keys("width", [(0, "0"), (.08, "0"), (.62, n(stop - x)), (.94, n(stop - x)), (1, "0")], T)}</rect>',
                    f'<rect x="{n(stop)}" y="{dy - 14}" width="6" height="66" class="red"/>',
                    f'<g opacity="0">{P.smil_keys("opacity", [(0, "0"), (.62, "1"), (.94, "0")], T, discrete=True)}'
                    f'<rect x="{n(stop - 90)}" y="{dy + 52}" width="96" height="32" class="red"/>{sh.text(stop - 78, dy + 75, "STOP", 19, "k", "paper")}</g>']
        elif "trace" in key or "clock" in key:
            for j, (a, w_, cls) in enumerate([(0.0, 0.3, "ink"), (0.32, 0.22, "red"), (0.56, 0.4, "ink"),
                                              (0.08, 0.18, "red"), (0.4, 0.25, "ink"), (0.7, 0.26, "red")]):
                out.append(f'<rect x="{n(x + a * cw)}" y="{dy + (j % 3) * 24}" height="18" class="{cls}">'
                           f'{P.smil_keys("width", [(0, "0"), (a * .8, "0"), (a * .8 + w_ * .8, n(w_ * cw)), (.94, n(w_ * cw)), (1, "0")], T)}</rect>')
            out.append(f'<rect y="{dy - 10}" width="3" height="92" class="ink" x="{n(x)}">{P.smil_keys("x", [(0, n(x)), (.94, n(x + cw)), (1, n(x))], T)}</rect>')
        elif env:
            for j, (name, _) in enumerate(env[:4]):
                a = 0.1 + 0.15 * j
                out.append(f'<g opacity="0">{P.smil_keys("opacity", [(0, "0"), (a, "1"), (.94, "0")], T, discrete=True)}'
                           f'<rect x="{n(x)}" y="{dy + j * 26}" width="14" height="18" class="red"/>'
                           + sh.text(x + 24, dy + j * 26 + 15, fit(name, 15, cw - 24), 15, "b") + "</g>")
    out.append(sh.grain())
    return sh.render("".join(out))


def pattern(tag: str, name: str) -> str:
    """What kind of loop a flow is, from its catalogue tag (or, failing that, its name)."""
    s = f"{tag} {name}".lower()
    for key, words in (("lanes", ("lane", "parallel")), ("cleaner", ("clean",)), ("checker", ("check", "review")),
                       ("relay", ("relay", "chase")), ("divide", ("divide", "recursive", "conquer"))):
        if any(w in s for w in words):
            return key
    return "loop"


def cube(sh: Sheet, x: float, y: float, s: float, red: bool) -> str:
    """A small axonometric block: an agent."""
    c = sh.c
    top, left, right = ((P.mix(c["red"], "#ffffff", .2), c["red"], c["deep"]) if red else
                        (P.mix(c["ink"], c["paper"], .55), P.mix(c["ink"], c["paper"], .25), c["ink"]))
    h = s * 0.5
    return (f'<polygon points="{n(x)},{n(y - h)} {n(x + s)},{n(y - h - s * .5)} {n(x + 2 * s)},{n(y - h)} {n(x + s)},{n(y - h + s * .5)}" fill="{top}"/>'
            f'<polygon points="{n(x)},{n(y - h)} {n(x + s)},{n(y - h + s * .5)} {n(x + s)},{n(y + s * .5 + s * .4)} {n(x)},{n(y + s * .4)}" fill="{left}"/>'
            f'<polygon points="{n(x + s)},{n(y - h + s * .5)} {n(x + 2 * s)},{n(y - h)} {n(x + 2 * s)},{n(y + s * .4)} {n(x + s)},{n(y + s * .5 + s * .4)}" fill="{right}"/>')


def flow_tile(theme: str, fl: Flow, i: int) -> str:
    """A flow: its kind on a plate, its name, its line, its roles, and its loop acted out by blocks
    and the red ball."""
    W, H, T = 340.0, 250.0, 8.0
    sh = Sheet(theme, W, H, f"{fl.name}: {fl.blurb}")
    ball = sh.ball()
    kind = pattern(fl.tag, fl.name)
    out = []
    # The stage, top right.
    ox, oy = 196.0, 70.0

    def orb(keys: list[tuple[float, float, float]], r: float = 9) -> str:
        return f'<circle r="{n(r)}" fill="{ball}">{P.smil_move(keys, T)}</circle>'

    if kind == "relay":
        a, b = (ox, oy + 22), (ox + 78, oy + 22)
        out += [cube(sh, a[0] - 18, a[1], 18, False), cube(sh, b[0] - 18, b[1], 18, True)]
        keys = []
        for j in range(9):
            e = j / 8
            keys.append((0.05 + 0.4 * e, a[0] + (b[0] - a[0]) * P.ease(e), a[1] - 22 - 48 * math.sin(math.pi * e)))
        for j in range(9):
            e = j / 8
            keys.append((0.55 + 0.4 * e, b[0] + (a[0] - b[0]) * P.ease(e), b[1] - 22 - 48 * math.sin(math.pi * e)))
        out.append(orb(keys))
    elif kind == "checker":
        a, b = (ox - 6, oy + 40), (ox + 84, oy + 40 - 90 * SLOPE)
        out += [cube(sh, a[0] - 16, a[1], 16, False), cube(sh, b[0] - 16, b[1], 16, True),
                f'<line x1="{n(a[0])}" y1="{n(a[1] - 20)}" x2="{n(b[0])}" y2="{n(b[1] - 20)}" class="wire" stroke-width="2" opacity=".5"/>']
        keys = []
        for rnd in range(3):
            s0 = rnd / 3
            keys += [(s0 + .02, a[0], a[1] - 22), (s0 + .14, b[0], b[1] - 22), (s0 + .2, b[0], b[1] - 22), (s0 + .31, a[0], a[1] - 22)]
        out.append(orb(keys))
        for rnd in range(3):
            s0 = rnd / 3
            last = rnd == 2
            out.append(f'<g opacity="0">{P.smil_keys("opacity", [(0, "0"), (s0 + .15, "1"), (s0 + .3 if not last else .98, "0")], T, discrete=True)}'
                       + sh.text(b[0] + 30, b[1] - 34, "✓ DONE" if last else "✗ NOT YET", 13, "t", "red" if last else "ink") + "</g>")
    elif kind == "lanes":
        out.append(f'<rect x="{n(ox - 20)}" y="{n(oy - 40)}" width="6" height="104" class="ink"/>')
        for j, speed in enumerate((1.0, 0.7, 1.35)):
            yy = oy - 26 + 34 * j
            out.append(f'<line x1="{n(ox - 14)}" y1="{n(yy)}" x2="{n(ox + 124)}" y2="{n(yy)}" class="wire" stroke-width="2" opacity=".45"/>')
            ks = [(0, ox - 4, yy), (min(.9, .7 / speed), ox + 116, yy), (min(.95, .7 / speed + .05), ox - 4, yy), (1, ox - 4, yy)]
            out.append(orb(ks, 7) if j != 1 else f'<rect x="-7" y="-7" width="14" height="14" class="ink">{P.smil_move(ks, T)}</rect>')
        out.append(f'<rect x="{n(ox + 128)}" y="{n(oy - 40)}" width="8" class="red">{P.smil_keys("height", [(0, "8"), (.5, "50"), (.9, "104"), (1, "8")], T)}</rect>')
    elif kind == "cleaner":
        out.append(cube(sh, ox - 20, oy + 40, 18, False))
        for j in range(4):
            yv = oy + 4 - 14 * j
            out.append(f'<rect x="{n(ox + 60)}" y="{n(yv)}" width="56" height="10" class="ink" opacity="0">'
                       f'{P.smil_keys("opacity", [(0, "0"), (.12 + .16 * j, "1"), (.78, "0")], T, discrete=True)}</rect>')
        out.append(f'<rect x="{n(ox + 60)}" y="{n(oy + 4)}" width="56" height="10" class="red" opacity="0">'
                   f'{P.smil_keys("opacity", [(0, "0"), (.78, "1"), (.98, "0")], T, discrete=True)}</rect>')
        out.append(f'<rect x="{n(ox + 52)}" width="72" height="5" class="red">{P.smil_keys("y", [(0, n(oy - 60)), (.66, n(oy - 60)), (.78, n(oy + 6)), (.9, n(oy - 60))], T)}</rect>')
        keys = [(0, ox, oy + 6), (.06, ox, oy + 6)]
        for j in range(4):
            keys += [(.08 + .16 * j, ox + 70, oy - 4 - 14 * j), (.16 + .16 * j, ox, oy + 6)]
        out.append(orb(keys, 7))
    elif kind == "divide":
        pts = [(ox + 60, oy - 40)]
        lv1 = [(ox + 20, oy + 6), (ox + 100, oy + 6)]
        lv2 = [(ox, oy + 50), (ox + 40, oy + 50), (ox + 80, oy + 50), (ox + 120, oy + 50)]
        for (x1, y1) in lv1:
            out.append(f'<line x1="{n(pts[0][0])}" y1="{n(pts[0][1])}" x2="{n(x1)}" y2="{n(y1)}" class="hair" opacity=".5"/>')
        for j, (x2, y2) in enumerate(lv2):
            p1 = lv1[j // 2]
            out.append(f'<line x1="{n(p1[0])}" y1="{n(p1[1])}" x2="{n(x2)}" y2="{n(y2)}" class="hair" opacity=".5"/>')
        for j, (x2, y2) in enumerate(lv2):
            p1 = lv1[j // 2]
            ks = [(0, *pts[0]), (.15, *pts[0]), (.3, *p1), (.45, x2, y2), (.65, x2, y2), (.8, *p1), (.95, *pts[0]), (1, *pts[0])]
            out.append(orb(ks, 7))
            out.append(f'<text x="{n(x2)}" y="{n(y2 + 26)}" class="k13 red" text-anchor="middle" opacity="0">'
                       f'{P.smil_keys("opacity", [(0, "0"), (.48 + .03 * j, "1"), (.8, "0")], T, discrete=True)}✓</text>')
            sh.sizes.add(("k", 13))
    else:  # one agent, looping: the ball orbits its block, behind it and then in front
        out.append(f'<ellipse cx="{n(ox + 50)}" cy="{n(oy + 10)}" rx="70" ry="22" class="hair" opacity=".4"/>')
        xs, ys, vis_b, vis_f = [], [], [], []
        for u in P.loop_frames(48):
            th = 2 * math.pi * u
            xs.append(n(ox + 50 + 70 * math.cos(th)))
            ys.append(n(oy + 10 + 22 * math.sin(th)))
            vis_f.append("1" if math.sin(th) >= 0 else "0")
            vis_b.append("0" if math.sin(th) >= 0 else "1")
        mk = lambda v: (f'<circle r="9" fill="{ball}">{P.smil("cx", xs, T / 2)}{P.smil("cy", ys, T / 2)}'  # noqa: E731
                        f'{P.smil("opacity", v, T / 2, discrete=True)}</circle>')
        out += [mk(vis_b), cube(sh, ox + 30, oy + 18, 20, i % 2 == 0), mk(vis_f)]
    # The words.
    tag = fl.tag.upper() or "A FLOW"
    out.insert(0, f'<rect x="20" y="20" width="{n(tracked(tag, 13) + 18)}" height="22" class="ink"/>' + sh.text(29, 36, tag, 13, "t", "paper"))
    if fl.source:
        out.append(sh.text(20, 62, fit(fl.source, 13, 150), 13, "r", "mute"))
    # A long name breaks after its colon, and shrinks until each part fits on its line.
    head, colon, rest = fl.name.partition(":")
    names = [head + colon, rest] if colon and width(fl.name, 22, True) > W - 40 else [fl.name]
    size = round(min(fitsize(ln, 22, W - 40, least=15) for ln in names), 1)
    y = 160.0 if len(names) == 1 else 140.0
    for ln in names:
        out.append(sh.text(20, y, ln, size))
        y += size + 5
    for ln in wrap(fl.blurb, 14, W - 40, 2):
        out.append(sh.text(20, y + 4, ln, 14, "r", "mute"))
        y += 19
    if fl.roles:
        out.append(sh.text(20, H - 14, fit("-a " + " · ".join(fl.roles), 13, W - 70), 13, "b", "red"))
    out.append(sh.text(W - 16, H - 14, "→", 18, "k", "ink", "end"))
    out.append(f'<rect x="1" y="1" width="{n(W - 2)}" height="{n(H - 2)}" class="hair" opacity=".3"/>')
    return sh.render("".join(out))


def result_tile(theme: str, r: Result, i: int) -> str:
    """A result: the number spins into place like a counter, then the claim, and where it was kept."""
    W, H, T = 300.0, 230.0, 11.0
    sh = Sheet(theme, W, H, f"{r.label}: {r.num}")
    red = i % 3 == 0
    out = []
    if red:
        out.append(f'<rect width="{n(W)}" height="{n(H)}" class="red"/>')
    ink, sub = ("paper", "paper") if red else ("ink", "mute")
    size = min(66.0, (W - 44) / max(len(r.num), 1) / 0.74)
    adv = size * 0.74
    od, _ = P.odometer(22, 32 + size * 0.95, r.num, size, f"k{n(size).replace('.', '_')} {ink}", T, 0.3 + 0.12 * (i % 4), adv, f"od{i}")
    sh.sizes.add(("k", size))
    out.append(od)
    out.append(f'<rect x="22" y="{n(40 + size)}" height="5" class="{"ink" if red else "red"}">'
               f'{P.smil_keys("width", [(0, "0"), (.12, "0"), (.3, "64"), (.9, "64"), (.98, "0")], T)}</rect>')
    y = 82 + size
    for ln in wrap(r.label, 17, W - 44, 3, True):
        out.append(sh.text(22, y, ln, 17, "b", ink))
        y += 22
    out.append(sh.text(W - 18, H - 16, "READ →", 15, "t", ink if red else "red", "end"))
    out.append(f'<rect x="1" y="1" width="{n(W - 2)}" height="{n(H - 2)}" class="hair" opacity=".3"/>')
    return sh.render("".join(out))


def post_strip(theme: str, p: Post, i: int) -> str:
    """A post on one line: its kind on a plate that flips over now and then, its date, its title."""
    W, H, T = 1000.0, 92.0, 9.0
    sh = Sheet(theme, W, H, p.title)
    out = []
    plate = "red" if p.kind == "NEWS" else "ink"
    flip = [(u, 1.0, max(.02, abs(math.cos(math.pi * min(1.0, max(0.0, (u - .8) / .1)))))) for u in P.loop_frames(40)]
    out.append(f'<g transform="translate(62 30)"><g>{P.smil_move(flip, T, "scale")}<rect x="-46" y="-16" width="92" height="32" class="{plate}"/>'
               + sh.text(0, 6, p.kind, 15, "t", "paper", "middle") + "</g></g>")
    out.append(sh.text(16, 72, p.date.upper(), 13, "t", "mute"))
    out.append(sh.text(140, 40, fit(p.title, 24, W - 240, True), 24))
    if p.by:
        out.append(sh.text(140, 68, fit(p.by, 15, W - 240), 15, "r", "mute"))
    out.append(f'<g>{P.smil_move([(0, 0, 0), (.1, 10, 0), (.2, 0, 0)], 3.2)}{sh.text(W - 24, 52, "→", 30, "k", "red", "end")}</g>')
    out.append(f'<rect x="0" y="{n(H - 3)}" width="{n(W)}" height="1.5" class="ink" opacity=".25"/>')
    out.append(f'<rect y="{n(H - 4)}" width="80" height="4" class="red">{P.smil("x", ["-80", n(W)], T, begin=-1.3 * i)}</rect>')
    return sh.render("".join(out))


def person_coin(theme: str, p: Person, i: int) -> str:
    """A person as a coin that turns over now and then -- face, then the ink side with their
    initials -- each a beat after the one before, so the wall ripples. Every coin is alike: no
    colour marks anyone out."""
    W, H, T = 180.0, 214.0, 12.0
    sh = Sheet(theme, W, H, f"{p.name} (@{p.handle})")
    c = sh.c
    cx, cy, r = 90.0, 86.0, 66.0
    sh.defs.append(f'<clipPath id="face"><circle r="{n(r)}"/></clipPath>')
    keys, face, back, rim = [], [], [], []
    for u in P.loop_frames(48):
        e = min(1.0, max(0.0, (u - .62) / .07))
        e2 = min(1.0, max(0.0, (u - .8) / .07))
        th = math.pi * (P.ease(e) + P.ease(e2))
        k = math.cos(th)
        keys.append((u, max(.03, abs(k)), 1.0))
        face.append("1" if k >= 0 else "0")
        back.append("0" if k >= 0 else "1")
        rim.append((u, -9 * math.sin(th), 0))
    initials = "".join(w[0] for w in p.name.split()[:2]).upper()
    pic = (f'<image href="{p.face}" x="{n(-r)}" y="{n(-r)}" width="{n(2 * r)}" height="{n(2 * r)}" clip-path="url(#face)"/>'
           if p.face else f'<circle r="{n(r)}" class="ink"/>' + sh.text(0, 14, initials, 40, "k", "paper", "middle"))
    begin = -0.7 * i
    out = [f'<g transform="translate({n(cx)} {n(cy)})">',
           f'<g>{P.smil_move(rim, T, begin=begin)}<circle r="{n(r)}" fill="{P.mix(c["ink"], c["paper"], .6)}"/></g>',
           f'<g>{P.smil_move(keys, T, "scale", begin)}',
           f'<g>{P.smil("opacity", face, T, True, begin)}{pic}<circle r="{n(r)}" fill="none" stroke="{c["ink"]}" stroke-width="4"/></g>',
           f'<g opacity="0">{P.smil("opacity", back, T, True, begin)}<circle r="{n(r)}" class="ink"/>'
           + sh.text(0, 14, initials, 40, "k", "paper", "middle") + "</g>",
           "</g></g>",
           sh.text(cx, 184, p.name, round(fitsize(p.name, 20, W - 10, False, 14), 1), "b", "ink", "middle"),
           sh.text(cx, 206, fit("@" + p.handle, 15, W - 10), 15, "r", "mute", "middle")]
    return sh.render("".join(out))


def principles(theme: str, f: Facts) -> str:
    """How they work, printed on the faces of a prism that turns a face at a time: an agitprop kiosk."""
    items = f.principles[:8]
    sides = max(3, len(items))
    W, H = 1000.0, 190.0
    T = 3.2 * sides
    sh = Sheet(theme, W, H, "How we work: " + " ".join(items))
    c = sh.c
    R = 62.0
    cy, x0, x1 = 100.0, 250.0, 976.0
    half = math.pi / sides
    times = []
    for k in range(sides):
        b = k / sides
        times += [b, b + 0.8 / sides] + [b + (0.8 + 0.2 * j / 8) / sides for j in range(1, 8)]
    times.append(1.0)

    def turn(u: float) -> float:
        k = min(int(u * sides), sides - 1)
        local = u * sides - k
        return 2 * math.pi / sides * (k + P.ease(max(0.0, (local - 0.8) / 0.2)))

    out = [sh.text(24, 74, "HOW", 34), sh.text(24, 112, "WE WORK", 34),
           f'<rect x="24" y="128" width="64" height="8" class="red"/>',
           f'<rect x="{n(x0 - 14)}" y="{n(cy - R - 8)}" width="10" height="{n(2 * R + 16)}" class="ink"/>',
           f'<rect x="{n(x1 + 4)}" y="{n(cy - R - 8)}" width="10" height="{n(2 * R + 16)}" class="ink"/>']
    lamp = -0.5
    for i in range(sides):
        ds, fills, vis, mv, sc = [], [], [], [], []
        for u in times:
            ph = 2 * math.pi * i / sides - turn(u)
            ya, yb = cy + R * math.sin(ph - half), cy + R * math.sin(ph + half)
            facing = math.cos(ph)
            ds.append(f"M{n(x0)} {n(ya)}H{n(x1)}V{n(yb)}H{n(x0)}Z")
            light = 0.25 + 0.75 * max(0.0, math.cos(ph - lamp))
            red = i % 2 == 1
            fills.append(P.mix(c["deep"] if red else c["ink"], c["red"] if red else P.mix(c["ink"], c["paper"], .35), light))
            vis.append("1" if facing > 0.01 else "0")
            mv.append((u, 0, R * math.cos(half) * math.sin(ph) + cy))
            sc.append((u, 1, max(.01, facing)))
        keyt = ";".join(f"{t:.4f}" for t in times)
        anim = lambda attr, vals, disc=False: (f'<animate attributeName="{attr}" dur="{n(T)}s" repeatCount="indefinite"'  # noqa: E731
                                               f'{" calcMode=" + chr(34) + "discrete" + chr(34) if disc else ""} values="{";".join(vals)}" keyTimes="{keyt}"/>')
        label = items[i] if i < len(items) else ""
        out.append(f'<g>{anim("opacity", vis, True)}<path d="{ds[0]}" fill="{fills[0]}">{anim("d", ds)}{anim("fill", fills)}</path>'
                   f'<g>{P.smil_move(mv, T)}<g>{P.smil_move(sc, T, "scale")}'
                   + sh.text(x0 + 28, 12, fit(label.upper(), 24, x1 - x0 - 56, True), 24, "k", "paper") + "</g></g></g>")
    out.append(sh.grain())
    return sh.render("".join(out))


def contact_tile(theme: str, what: str, href: str, i: int) -> str:
    W, H = 330.0, 150.0
    where = href.split("//", 1)[-1].rstrip("/")
    sh = Sheet(theme, W, H, f"{what}: {where}")
    fill, ink = (("red", "paper"), ("ink", "paper"), ("paper", "ink"))[i % 3]
    out = [f'<rect width="{n(W)}" height="{n(H)}" class="{fill}"/>']
    y = 42.0
    for ln in wrap(what, 19, W - 48, 2, True):
        out.append(sh.text(22, y, ln, 19, "b", ink))
        y += 25
    out.append(sh.text(22, H - 22, fit(where.upper(), 13, W - 70), 13, "t", ink))
    out.append(f'<g>{P.smil_move([(0, 0, 0), (.1, 8, 0), (.2, 0, 0)], 3)}{sh.text(W - 20, H - 18, "→", 28, "k", ink, "end")}</g>')
    out.append(f'<rect x="1" y="1" width="{n(W - 2)}" height="{n(H - 2)}" class="hair" opacity=".3"/>')
    return sh.render("".join(out))


def outro(theme: str, f: Facts) -> str:
    """The address, on red: the mark in paper, swinging a little, and the site's name."""
    W, H, T = 1000.0, 230.0, 16.0
    sh = Sheet(theme, W, H, SITE.split("//", 1)[-1])
    c = sh.c
    mark_defs(sh, f.logo, 150)
    frames = [swing(u, 26, -8) for u in P.loop_frames(48)]
    css, slab = P.extrude("ho", "hshape", frames, T, (130, 115), 34, 12, (c["ink"], P.mix(c["ink"], c["red"], .5)), "paper")
    sh.css.append(css)
    site = SITE.split("//", 1)[-1].upper()
    size = min(70.0, (W - 300) / width(site, 1, True))
    out = [f'<rect width="{n(W)}" height="{n(H)}" class="red"/>', slab,
           sh.text(250, 128, site, size, "k", "paper"),
           sh.text(254, 170, "GITHUB.COM/HUMANFIA", 18, "t", "ink"),
           f'<rect x="254" y="186" height="8" class="ink">{P.smil_keys("width", [(0, "0"), (.1, "0"), (.3, "380"), (.9, "380"), (1, "0")], T)}</rect>']
    out.append(sh.grain())
    return sh.render("".join(out))


# ---------------------------------------------------------------------------------- the profile

@dataclass
class Poster:
    name: str          # profile/art/<theme>/<name>.svg
    alt: str
    draw: Callable[[str], str]


def picture(p: Poster, width_: str = "100%", href: str = "") -> str:
    """A poster as GitHub shows it: the light or dark version by the viewer's theme, as a link."""
    pic = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="./{ART}/dark/{p.name}.svg">'
           f'<source media="(prefers-color-scheme: light)" srcset="./{ART}/light/{p.name}.svg">'
           f'<img src="./{ART}/light/{p.name}.svg" width="{width_}" alt="{esc(p.alt)}"></picture>')
    return f'<a href="{esc(href)}">{pic}</a>' if href else pic


def rows(cards: list[tuple[Poster, str]], per: int, gap: float = 0.6) -> str:
    """Cards in rows of `per`, each a link; no whitespace between them, so they sit edge to edge."""
    w = f"{(100 - gap * per) / per:.1f}%"
    lines = []
    for k in range(0, len(cards), per):
        lines.append("".join(picture(p, w, href) for p, href in cards[k:k + per]))
    return "<br>\n".join(lines)


def build(f: Facts) -> tuple[list[Poster], str]:
    """Every poster, and the README that places them."""
    posters: list[Poster] = []

    def add(name: str, alt: str, draw: Callable[[str], str]) -> Poster:
        p = Poster(name, alt, draw)
        posters.append(p)
        return p

    md = []
    num = 0

    def section(title: str, note: str) -> str:
        nonlocal num
        num += 1
        p = add(f"head-{num}", f"{num:02d} · {title}", lambda t, k=num, a=title, b=note: header(t, k, a, b))
        return f'<p>{picture(p)}</p>'

    lead = f.headline or "Humanfia"
    md.append(f'<p align="center">{picture(add("hero", f"Humanfia: {lead} {f.lead}".strip(), lambda t: hero(t, f)), href=SITE)}</p>')

    if f.projects:
        md.append(section("Projects", "Every project is open. Click one."))
        cards = [(add(f"project-{i}", f"{p.name}: {p.sub or p.lede}", lambda t, p=p, i=i: project_tile(t, p, i)), p.href)
                 for i, p in enumerate(f.projects[:6])]
        md.append(f'<p align="center">{rows(cards, len(cards))}</p>')

    if f.bands:
        md.append(section("The runtime", "Humanize: every turn, one clock. Unfold it."))
        inner = [f'<p>{picture(add("runtime", "Humanize, how it fits together: " + "; ".join(f"{b.title}, {b.about}" for b in f.bands[:4]), lambda t: runtime(t, f)), href=DOCS + "/")}</p>']
        if f.features:
            inner.append(f'<p>{picture(add("features", "; ".join(f"{h}: {p}" for h, p in f.features[:3]), lambda t: features(t, f)), href=DOCS + "/")}</p>')
        md.append("<details open>\n<summary><b>Humanize, how it fits together</b> — a turn falls through the stack</summary>\n\n"
                  + "\n".join(inner) + "\n\n</details>")

    if f.flows:
        md.append(section("Flows", f"{len(f.flows)} loops around the agents. Unfold, then pick one."))
        cards = [(add(f"flow-{i}", f"{fl.name} ({fl.tag}): {fl.blurb}", lambda t, fl=fl, i=i: flow_tile(t, fl, i)), fl.href)
                 for i, fl in enumerate(f.flows)]
        kinds = list(dict.fromkeys(fl.tag for fl in f.flows if fl.tag))
        md.append(f"<details>\n<summary><b>The flows</b> — {esc(', '.join(k.lower() for k in kinds[:6]))}</summary>\n\n"
                  f'<p align="center">{rows(cards, 3)}</p>\n\n</details>')

    if f.results:
        md.append(section("Results", "Measured where somebody else keeps the score."))
        cards = [(add(f"result-{i}", f"{r.label}: {r.num}. {r.body}", lambda t, r=r, i=i: result_tile(t, r, i)), r.href or SITE)
                 for i, r in enumerate(f.results[:12])]
        md.append(f'<p align="center">{rows(cards, 4)}</p>')

    if f.posts:
        md.append(section("Latest", "News and the blog, newest first."))
        strips = [picture(add(f"post-{i}", f"{p.kind} · {p.date} · {p.title}", lambda t, p=p, i=i: post_strip(t, p, i)), href=p.href)
                  for i, p in enumerate(f.posts)]
        md.append("<p>" + "<br>\n".join(strips) + "</p>")

    if f.people or f.principles:
        md.append(section("The people", fit(sentences(f.people_intro)[-1] if f.people_intro else "Who builds it.", 16, 600)))
        if f.people:
            cards = [(add(f"person-{i}", f"{p.name} (@{p.handle})", lambda t, p=p, i=i: person_coin(t, p, i)), f"https://github.com/{p.handle}")
                     for i, p in enumerate(f.people)]
            md.append(f'<p align="center">{rows(cards, 6 if len(cards) > 9 else len(cards))}</p>')
        if f.principles:
            md.append(f'<p>{picture(add("principles", "How we work: " + " ".join(f.principles), lambda t: principles(t, f)), href=absolute(f.people_href))}</p>')

    tail = [f'<p>{picture(add("outro", SITE.split("//", 1)[-1], lambda t: outro(t, f)), href=SITE)}</p>']
    if f.contact:
        cards = [(add(f"contact-{i}", f"{what}: {href}", lambda t, w=what, h=href, i=i: contact_tile(t, w, h, i)), href)
                 for i, (what, href) in enumerate(f.contact[:3])]
        tail.append(f'<p align="center">{rows(cards, len(cards))}</p>')
    md.extend(tail)

    readme = ("<!-- Generated from humanfia.ai by tools/gen_portfolio.py; edits here are overwritten. -->\n\n"
              + "\n\n".join(md) + "\n")
    return posters, readme


# ----------------------------------------------------------------------------------------- main

def main() -> None:
    themes = [os.environ["THEME"]] if os.environ.get("THEME") else ["light", "dark"]
    facts = gather()
    posters, readme = build(facts)
    for theme in themes:
        out = PROFILE / ART / theme
        if out.exists():
            shutil.rmtree(out)  # a section the site dropped takes its posters with it
        out.mkdir(parents=True)
        total = 0
        for p in posters:
            path = out / f"{p.name}.svg"
            path.write_text(p.draw(theme), encoding="utf-8")
            total += path.stat().st_size
        print(f"wrote {len(posters)} posters to {out.relative_to(ROOT)} ({total // 1024} KB)")
    (PROFILE / "README.md").write_text(readme, encoding="utf-8")
    for old in PROFILE.glob("humanfia-portfolio-*.svg"):  # the single banner this replaced
        old.unlink()
    print("wrote profile/README.md")


if __name__ == "__main__":
    main()
