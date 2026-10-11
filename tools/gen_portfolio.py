#!/usr/bin/env python3
"""Generate the Humanfia org profile banner from humanfia.ai: a constructivist film of about a minute.

Nothing about Humanfia is written down here. Every run reads the live sites and cuts what it finds
into short shots, flat and geometric -- discs, wedges, bars on the logo's one-in-three diagonal,
block capitals -- in the site's own colours. Words are kept to names and numbers; the rest is said
by things moving:

    the mark          /logo.svg: a pink wedge drives into an ink disc, the ball drops into it and
                      swells; the H lands, the wordmark draws itself, the ball dots the i; the
                      headline slams down a word at a time with the ball as its full stop
    the runtime       the Humanize docs' bands: a stair of bars the ball falls through
    the flows         the /flows/ catalogue: a counter, then each kind of loop acted out by shapes
    the projects      the nav's Projects menu: each name cut deep across a colour
    the achievements  every result humanfia.ai has announced (see below): a counter, then each
                      number spun onto a counter and drawn as shapes, new ones stamped NEW; the
                      rest stamped onto a wall
    the people        About's roster bursting out of the ball onto turning rings
    the address       on green: the H, the site's name, the ball dropping home

The achievements are kept in profile/achievements.json. Each run adds every news post and home-page
tile it has not seen, keeps those the site has only stopped featuring, and drops one only when its
post is gone; nothing has to be told which to track.

A section whose source the site does not have (a 404 or 410, or markup without the parts it needs)
is left out. Any other failure -- a 403, a 5xx, a timeout -- stops the run, so a bad fetch never
overwrites a good profile.

GitHub shows README images through <img>: no JavaScript, no web fonts, nothing loaded. So the film
plays on one SMIL clock; type is the system's heaviest sans, avatars are inlined.

    python3 tools/gen_portfolio.py              # both banners
    THEME=dark python3 tools/gen_portfolio.py   # one banner (light|dark)
    SITE=http://localhost:4173 DOCS=http://localhost:5173/humanize python3 tools/gen_portfolio.py
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import http.client
import json
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

SITE = os.environ.get("SITE", "https://humanfia.ai").rstrip("/")
DOCS = os.environ.get("DOCS", "https://docs.humanfia.ai/humanize").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
ART = "art"  # where the poster wall this replaced lived; removed on sight
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

THEMES = {  # humanfia.ai's own, used the way the site uses them: paper and ink nearly everywhere, green
    # as the one loud colour, cyan as its quiet second, pink only to stamp what is new. `slab` is the
    # contrasting ground (ink in light, a deep slate in dark, so the dark film never flashes white),
    # `onslab` what reads on it, and `night` what reads on green or cyan.
    "light": {"paper": "#f4f8f9", "alt": "#e8f0f2", "ink": "#141a1f", "mute": "#5d6a72", "night": "#141a1f",
              "slab": "#141a1f", "onslab": "#f4f8f9", "green": "#76b900", "cyan": "#1fb3c7", "pink": "#ec6fa3"},
    "dark": {"paper": "#0f1418", "alt": "#172026", "ink": "#e8f0f2", "mute": "#82939a", "night": "#141a1f",
             "slab": "#1d2a31", "onslab": "#e8f0f2", "green": "#76b900", "cyan": "#4fd8ea", "pink": "#ff94c2"},
}
ACCENTS = ("green", "cyan")
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
    news: list[Post] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    people_href: str = "/about/"
    people_intro: str = ""
    principles: list[str] = field(default_factory=list)
    contact: list[tuple[str, str]] = field(default_factory=list)  # (what for, href)
    achievements: list[Achievement] = field(default_factory=list)   # from the ledger, newest first


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
    f.news = feed("/news/feed.rss", "NEWS")
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


def n(v: float) -> str:
    """A number as an SVG attribute: two decimals at most, no trailing zeros."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


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

    def render(self, body: str) -> str:
        c = self.c
        fills = "".join(f".{k}{{fill:{v}}}" for k, v in c.items())
        stroke = f".glyph{{fill:none;stroke:{c['ink']};stroke-width:13}}"
        fonts = "".join(f".{k}{n(s).replace('.', '_')}{{{KINDS[k]};font-size:{n(s)}px}}" for k, s in sorted(self.sizes))
        calm = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {n(self.w)} {n(self.h)}" width="{n(self.w)}" height="{n(self.h)}" '
                f'role="img" aria-labelledby="t"><title id="t">{esc(self.title)}</title>'
                f'<style>{fills}{stroke}{fonts}{"".join(self.css)}{calm}</style>'
                f'<defs>{"".join(self.defs)}</defs><rect width="{n(self.w)}" height="{n(self.h)}" class="paper"/>{body}</svg>\n')


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




# --------------------------------------------------------------------------------- achievements

# Every news post on humanfia.ai announces a result, and the home page's tiles feature some of them.
# The ledger, profile/achievements.json, remembers every one this profile has seen: each run adds
# what is new, keeps what the site has merely stopped featuring, and drops only a post that is gone.

LEDGER = PROFILE / "achievements.json"
FRESH_DAYS = 14  # how long an achievement is announced as new, from the day it was published

_NUM = re.compile(r"(?<![\w.])(#\d[\d,]*|[+-]?\d[\d,]*(?:\.\d+)?(?:%|×|\+)?(?:/\d[\d,]*)?)(?=[\s,:;)]|$)")


@dataclass
class Achievement:
    href: str                                  # its post, as a path on the site
    num: str                                   # the number it is about: "6/6", "78.2%", "#1", or ""
    label: str
    date: str = ""                             # the ISO day it was published, or first seen
    added: str = ""                            # the ISO day this profile first saw it
    featured: int = -1                         # its place among the home page's tiles; -1 if not there

    def record(self) -> dict[str, str]:
        return {"href": self.href, "num": self.num, "label": self.label, "date": self.date, "added": self.added}


def headline_number(title: str) -> tuple[str, str]:
    """A news title's headline number and what it is about: "78.2% MLE-bench medal rate in 6 hours"
    -> ("78.2%", "MLE-bench medal rate in 6 hours"). After an arrow, the number it arrives at; a
    number inside the title leaves the title whole."""
    _, arrow, after = title.rpartition("→")
    m = _NUM.search(after if arrow else title)
    if not m:
        return "", title
    if not arrow and m.start() == 0 and title[m.end():].strip(" ,:;"):
        return m.group(1), title[m.end():].strip(" ,:;")
    return m.group(1), title


def path_of(href: str) -> str:
    p = re.sub(r"^https?://[^/]+", "", href).split("#", 1)[0].split("?", 1)[0].rstrip("/")
    return p or "/"


def load_ledger(path: Path = LEDGER) -> list[dict[str, str]]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except ValueError:
        sys.exit(f"gen_portfolio: {path.name} is not JSON; leaving the profile as it is")
    return [r for r in rows if isinstance(r, dict) and r.get("href")]


def achievements(f: Facts, old: list[dict[str, str]], today: dt.date,
                 exists: Callable[[str], bool]) -> list[Achievement]:
    """Every achievement the site announces now -- each news post, and each tile on the home page,
    whose words win -- plus those it announced before and still publishes. Newest first."""
    now: dict[str, Achievement] = {}
    for p in f.news:
        num, label = headline_number(p.title)
        now[path_of(p.href)] = Achievement(path_of(p.href), num, label,
                                           dt.datetime.fromtimestamp(p.when, dt.timezone.utc).date().isoformat())
    for i, r in enumerate(f.results):
        key = path_of(r.href) if r.href else "#" + r.label
        a = now.setdefault(key, Achievement(key, "", ""))
        a.num, a.label, a.featured = r.num, r.label, i
    prior = {r["href"]: r for r in old}
    out = []
    for key, a in now.items():
        was = prior.get(key, {})
        a.added = was.get("added") or today.isoformat()
        a.date = a.date or was.get("date") or a.added
        out.append(a)
    for key, was in prior.items():
        if key not in now and key.startswith("/") and exists(key):
            out.append(Achievement(key, was.get("num", ""), was.get("label", ""), was.get("date", ""), was.get("added", "")))
    return sorted(out, key=lambda a: (a.date, a.href), reverse=True)


def save_ledger(items: list[Achievement], path: Path = LEDGER) -> None:
    path.write_text(json.dumps([a.record() for a in items], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def fresh(a: Achievement, today: dt.date) -> bool:
    try:
        return dt.date.fromisoformat(a.date) >= today - dt.timedelta(days=FRESH_DAYS)
    except ValueError:
        return False


def lineup(items: list[Achievement], today: dt.date) -> list[Achievement]:
    """The order of the broadcast: what is new, then what the home page features, then the rest."""
    new = [a for a in items if fresh(a, today)]
    feat = sorted((a for a in items if a.featured >= 0 and a not in new), key=lambda a: a.featured)
    return new + feat + [a for a in items if a not in new and a not in feat]


# ------------------------------------------------------------------------------------- the spot

# One minute, cut on the beat, in flat planes: discs, wedges, bars on the logo's one-in-three
# diagonal, block capitals, and the site's five colours. Words are kept to names and numbers;
# everything else is said by things moving. The green ball -- the dot of the H -- is the one actor
# all the way through.

W, H = 1000.0, 560.0       # the frame; shown ~830 px wide on GitHub
BALL = 30.0                # the ball's radius, most of the time
HEIGHT_H = 300.0           # the H, as #hshape is drawn


def mark_defs(sh: Sheet, logo: Logo) -> tuple[float, float, float]:
    """The H, centred on the origin, HEIGHT_H tall, as #hshape (once). Returns the dot's place
    (x, y, r) relative to the centre."""
    vx, vy, vw, vh = logo.viewbox
    s = HEIGHT_H / vh
    if not any('id="hshape"' in d for d in sh.defs):
        sh.defs.append(f'<g id="hshape" transform="scale({n(s)}) translate({n(-vx - vw / 2)} {n(-vy - vh / 2)})">{logo.body}</g>')
    dx, dy, dr = logo.dot if logo.dot else (vx + vw * 0.875, vy + vh * 0.11, vw * 0.125)
    return (dx - vx - vw / 2) * s, (dy - vy - vh / 2) * s, dr * s


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
        self.ball_ink: tuple[float, float] | None = None   # when the ball is night, not green

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

    def spin(self, t0: float, t1: float, a0: float, a1: float) -> str:
        return self.tf("rotate", [(0, a0), (t0, a0), (t1, a1)])

    def grow(self, attr: str, t: float, a: float, b: float, d: float = 0.4, ease: str = "out") -> str:
        return self.anim(attr, [(0, a), *tween(t, d, a, b, ease, 6)])

    def text(self, x: float, y: float, s: str, size: float, kind: str = "k", ink: str = "ink", anchor: str = "",
             extra: str = "") -> str:
        return self.sh.text(x, y, s, size, kind, ink, anchor, extra)

    def ball(self, pts: list[tuple[float, float, float, float]]) -> None:
        """The ball's path for a stretch of the film, (t, x, y, r); it is shown over that stretch."""
        self.ball_keys += [(t, (x, y, r)) for t, x, y, r in pts]
        self.ball_on.append((pts[0][0], pts[-1][0]))

    def bg(self, ink: str) -> str:
        return f'<rect x="-40" y="-40" width="{n(W + 80)}" height="{n(H + 80)}" class="{ink}"/>'


def flip(ground: str) -> str:
    """The ink that reads on a ground: ink on paper, onslab on the slab, night on a colour."""
    return {"paper": "ink", "alt": "ink", "ink": "paper", "slab": "onslab"}.get(ground, "night")


def accent(i: int) -> str:
    return ACCENTS[i % len(ACCENTS)]


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


def slam(F: Film, t: float, x: float, base: float, s: str, size: float, ink: str, k0: float = 2.2) -> str:
    """Block capitals slammed down from large, about their own middle."""
    ww = capw(s, size)
    body = F.text(0, 0, s, size, "k", ink, extra=f' textLength="{n(ww)}" lengthAdjust="spacingAndGlyphs"')
    return F.at(x + ww / 2, base - size * 0.35, f'<g transform="translate({n(-ww / 2)} {n(size * 0.35)})">{body}</g>',
                F.tf("scale", [(0, (k0, k0)), *tween(t, 0.3, (k0, k0), (1.0, 1.0), "back", 6)]),
                F.anim("opacity", [(0, 0), (t, 0), (t + 0.05, 1)]))


def words_in(F: Film, t: float, x: float, y: float, lines: list[str], size: float, ink: str = "ink",
             lead: float = 1.08, gap: float = 0.09, hot: Callable[[str], bool] = lambda w: False) -> tuple[str, float, float]:
    """Lines of block capitals, word by word, each slammed down. A hot word lands on a green plate.
    Returns the svg and where the last word ends (x, baseline)."""
    out, k, end = [], 0, (x, y)
    for j, line in enumerate(lines):
        cx = x
        by = y + j * size * lead
        for w_ in line.split():
            ww = capw(w_, size)
            ti = t + gap * k
            if hot(w_):
                out.append(f'<rect x="{n(cx - 8)}" y="{n(by - size * 0.86)}" width="0" height="{n(size * 1.04)}" class="green">'
                           f'{F.grow("width", ti, 0.0, ww + 16, 0.25)}</rect>')
            out.append(slam(F, ti, cx, by, w_, size, "night" if hot(w_) else ink, 2.4))
            end = (cx + ww, by)
            cx += ww + size * 0.28
            k += 1
    return "".join(out), end[0], end[1]


def odo(F: Film, x: float, base: float, s: str, size: float, ink: str, t: float) -> tuple[str, float]:
    """Digits that spin into place like a mechanical counter, from t; anything else springs up.
    Returns the svg and its width."""
    adv = size * 0.74
    cid = F.uid("odo")
    wide = sum(adv * (0.45 if ch in ".,:" else 1.0) for ch in s)
    line = size * 1.2
    out = [f'<clipPath id="{cid}"><rect x="{n(x - 10)}" y="{n(base - size * 0.95)}" width="{n(wide + 20)}" height="{n(size * 1.2)}"/></clipPath>',
           f'<g clip-path="url(#{cid})">']
    cx, k = x, 0
    for ch in s:
        w = adv * (0.45 if ch in ".,:" else 1.0)
        if ch.isdigit():
            land = 10 + int(ch)
            strip = "".join(F.text(cx + w / 2, base + line * i, str(i % 10), size, "k", ink, "middle") for i in range(land + 1))
            ti = t + 0.05 * k
            out.append(f'<g>{F.tf("translate", [(0, (0.0, 0.0)), *tween(ti, 0.55 + 0.06 * k, (0.0, 0.0), (0.0, -line * land), "out", 8)])}{strip}</g>')
            k += 1
        else:
            out.append(F.pop(t + 0.35, cx + w / 2, base, F.text(0, 0, ch, size, "k", ink, "middle"), 0.2, 0.3))
        cx += w
    out.append("</g>")
    return "".join(out), wide


def disc(cx: float, cy: float, r: float, cls: str, extra: str = "") -> str:
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" class="{cls}"{extra}/>'


def bar(x: float, y: float, w: float, h: float, cls: str, extra: str = "") -> str:
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" class="{cls}"{extra}/>'


def tilt(x: float, y: float, inner: str, a: float = -ANGLE) -> str:
    """On the logo's diagonal, about (x, y)."""
    return f'<g transform="translate({n(x)} {n(y)}) rotate({n(a)})">{inner}</g>'


def ring(cx: float, cy: float, r: float, stroke: float, color: str, extra: str = "") -> str:
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="none" stroke="{color}" stroke-width="{n(stroke)}"{extra}/>'


# ------------------------------------------------------------------------------------- the shots

Draw = Callable[[Film, float, float], str]


@dataclass
class Shot:
    name: str
    seconds: float
    draw: Draw
    enter: str = "cut"     # cut | whip | punch | rise


def shot_open(F: Film, t0: float, t1: float) -> str:
    """Beat the whites with the wedge: an ink disc swells, a green wedge drives into it, bars fly in
    on the diagonal, and the ball drops into the disc's heart -- then swells to fill the frame."""
    c = F.c
    out = [F.bg("paper")]
    out.append(F.at(690, 290, disc(0, 0, 210, "ink") + bar(-210, -9, 420, 18, "paper"),
                    F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.05, 0.45, (0.0, 0.0), (1.0, 1.0), "back", 6)]),
                    F.spin(t0 + 0.5, t1, 0.0, 70.0)))
    wedge = f'<polygon points="0,-70 560,0 0,70" class="green"/>'
    out.append(tilt(130, 450, f'<g>{F.tf("translate", [(0, (-900.0, 0.0)), (t0 + 0.4, (-900.0, 0.0)), *tween(t0 + 0.4, 0.35, (-900.0, 0.0), (0.0, 0.0), "in", 5)[1:], *tween(t0 + 0.75, 0.25, (-30.0, 0.0), (0.0, 0.0), "back", 4)])}{wedge}</g>'))
    for i, (x, y, w, h, cls, dx) in enumerate(((40, 120, 620, 16, "cyan", 1400), (380, 470, 600, 30, "ink", -1400),
                                                (60, 500, 260, 8, "ink", 1400), (560, 70, 380, 6, "mute", -1400))):
        ti = t0 + 0.25 + 0.08 * i
        out.append(tilt(x + w / 2, y, f'<g>{F.slide(ti, dx, 0, 0.32, "back")}{bar(-w / 2, -h / 2, w, h, cls)}</g>'))
    out.append(F.at(170, 220, bar(-50, -50, 100, 100, "cyan"),
                    F.tf("rotate", [(0, -90.0), *tween(t0 + 0.6, 0.5, -90.0, ANGLE, "back", 6), (t1, ANGLE + 30)]),
                    F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.6, 0.35, (0.0, 0.0), (1.0, 1.0), "back", 5)])))
    for k in range(3):
        out.append(f'<rect x="90" y="{n(300 + 22 * k)}" width="0" height="8" class="ink">{F.grow("width", t0 + 0.9 + 0.08 * k, 0.0, 200.0 - 50 * k, 0.35)}</rect>')
    out.append(ring(690, 290, 260, 2, c["ink"], f' stroke-dasharray="4 10" opacity=".5"'))
    land = 290.0
    F.ball([(t0 + 0.9, 690, -60, BALL), *[(t, 690, y, BALL) for t, y in tween(t0 + 0.9, 0.45, -60.0, land, "in", 5)][1:],
            *[(t, 690, land, r) for t, r in tween(t0 + 1.35, 0.25, BALL * 1.3, BALL, "back", 3)],
            (t1 - 0.4, 690, land, BALL), *[(t, 690, land, r) for t, r in tween(t1 - 0.4, 0.4, BALL, 1300.0, "in", 6)][1:]])
    return "".join(out)


def shot_mark(F: Film, t0: float, t1: float) -> str:
    """The green frame shrinks into the H's slot; planes slide in behind it; the wordmark draws
    itself, stroke by stroke; the ball hops over to dot the i."""
    hx, hy = 270.0, 280.0
    sx, sy, sr = mark_defs(F.sh, F.f.logo)
    out = [F.bg("paper")]
    out.append(f'<g>{F.slide(t0 + 0.2, 0, -700, 0.4, "back")}{bar(440, -20, 36, 400, "green")}</g>')
    out.append(f'<g>{F.slide(t0 + 0.3, -500, 0, 0.4, "back")}{bar(60, 60, 150, 150, "cyan")}</g>')
    out.append(f'<g>{F.slide(t0 + 0.4, 0, 400, 0.4, "back")}{ring(880, 470, 110, 14, F.c["ink"])}</g>')
    out.append(tilt(700, 420, f'<rect x="-260" y="-5" width="0" height="6" class="mute">{F.grow("width", t0 + 0.9, 0.0, 520.0, 0.5)}</rect>'))
    out.append(F.at(hx, hy, '<use href="#hshape" class="ink"/>',
                    F.tf("scale", [(0, (0.6, 0.6)), *tween(t0, 0.45, (0.6, 0.6), (1.0, 1.0), "back", 6)])))
    x0, base, k = 520.0, 330.0, 1.06
    paths, xx, dot = [], 0.0, (0.0, 0.0, 0.0)
    for i, (d, w) in enumerate(_glyphs()):
        ti = t0 + 0.6 + 0.1 * i
        paths.append(f'<path transform="translate({n(xx)} 0)" d="{d}" pathLength="1" stroke-dasharray="1 1">'
                     f'{F.anim("stroke-dashoffset", [(0, 1), *tween(ti, 0.4, 1.0, 0.0, "out", 4)])}</path>')
        if i == 6:
            dot = (x0 + (xx + _H) * k, base - (XH + 10 + S * 0.62) * k, S * 0.62 * k)
        xx += w + 8
    out.append(f'<g transform="translate({n(x0)} {n(base)}) scale({n(k)})" class="glyph">{"".join(paths)}</g>')
    slot = (hx + sx, hy + sy, sr)
    hop = t0 + 1.9
    pts = [(t, *_lerp((690.0, 290.0, 1300.0), slot, u)) for t, u in tween(t0, 0.5, 0.0, 1.0, "io", 6)]
    pts.append((hop, *slot))
    for i in range(1, 9):
        u = i / 8
        e = EASE["io"](u)
        pts.append((hop + 0.55 * u, slot[0] + (dot[0] - slot[0]) * e, slot[1] + (dot[1] - slot[1]) * e - 130 * math.sin(math.pi * u),
                    slot[2] + (dot[2] - slot[2]) * e))
    pts.append((t1 - 0.02, *dot))
    F.ball(pts)
    return "".join(out)


def shot_headline(F: Film, t0: float, t1: float) -> str:
    """The headline, a word at a time, slammed down; the ball lands as its full stop."""
    head = F.f.headline.upper().rstrip(".")
    size, lines = fitlines(head, 860, 96, 40, 3)
    top = (H - size * 1.08 * len(lines)) / 2 + size * 0.8
    out = [F.bg("paper"),
           F.at(W, H, disc(0, 0, 300, "slab") + bar(-300, -12, 300, 24, "paper"),
                F.tf("scale", [(0, (0.0, 0.0)), *tween(t0, 0.5, (0.0, 0.0), (1.0, 1.0), "back", 6)]), F.spin(t0, t1, 0.0, -50.0)),
           f'<g>{F.slide(t0 + 0.1, 0, -300, 0.35, "back")}{bar(60, 0, 18, top - size * 0.95, "cyan")}</g>']
    body, ex, ey = words_in(F, t0 + 0.15, 60, top, lines, size, hot=lambda w: w.startswith("FLOW"))
    out.append(body)
    out.append(f'<rect x="60" y="{n(ey + size * 0.3)}" width="0" height="12" class="ink">{F.grow("width", t0 + 0.9, 0.0, 300.0)}</rect>')
    nwords = sum(len(ln.split()) for ln in lines)
    r = size * 0.16
    bx, by = ex + r * 1.6, ey - r
    tl = t0 + 0.15 + 0.09 * nwords + 0.25
    F.ball([(tl - 0.3, bx, -60, r), *[(t, bx, y, r) for t, y in tween(tl - 0.3, 0.3, -60.0, by, "in", 5)][1:],
            *[(t, bx, by, rr) for t, rr in tween(tl, 0.16, r, r * 1.3, "out", 2)][1:],
            *[(t, bx, by, rr) for t, rr in tween(tl + 0.16, 0.2, r * 1.3, r, "back", 3)][1:], (t1, bx, by, r)])
    return "".join(out)


def shot_wipe(num: int, title: str, ground: str) -> Draw:
    """A section's name: a colour floods in on the diagonal, the word slams down on it."""
    def draw(F: Film, t0: float, t1: float) -> str:
        word = title.upper()
        ink = flip(ground)
        band, plate, onplate = ("night", "onslab", "night") if ground == "green" else ("green", "green", "night")
        size = min(170.0, 860 / max(capw(word, 1), 1e-6))
        ww = capw(word, size)
        out = [F.bg(ground),
               tilt(W / 2, H - 70, f'<g>{F.slide(t0, -1500, 0, 0.35)}{bar(-800, -36, 1600, 72, band)}</g>', -ANGLE / 2),
               slam(F, t0 + 0.12, (W - ww) / 2, H / 2 + size * 0.35, word, size, ink, 2.6),
               f'<g>{F.slide(t0 + 0.2, 0, -160, 0.3, "back")}{bar(40, 40, 64, 64, plate)}'
               + F.text(72, 85, f"{num:02d}", 30, "k", onplate, "middle") + "</g>",
               F.at(900, 140, ring(0, 0, 44, 10, F.c[ink]), F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.3, 0.3, (0.0, 0.0), (1.0, 1.0), "back", 5)]))]
        return "".join(out)
    return draw


def shot_runtime(F: Film, t0: float, t1: float) -> str:
    """The runtime as a stair of bars, one per band, each landing in turn; the ball falls through
    them, and each bar gives as it passes."""
    bands = F.f.bands[:5]
    out = [F.bg("paper")]
    hb, gap = min(96.0, (H - 120) / max(len(bands), 1) - 22), 22.0
    top = (H - len(bands) * hb - (len(bands) - 1) * gap) / 2
    bx = 850.0
    tb = t0 + 0.35 + 0.18 * len(bands)
    pts: list[tuple[float, float, float, float]] = [(tb - 0.2, bx, -60, BALL * 0.8)]
    t = tb
    for k, band in enumerate(bands):
        x = 60 + 36 * k
        w = 900 - 36 * k - 60
        y = top + k * (hb + gap)
        cls = "green" if band.title.lower() == "humanize" else "slab"
        ti = t0 + 0.1 + 0.18 * k
        word = band.title.upper()
        size = min(hb * 0.62, (bx - x - 70) / max(capw(word, 1), 1e-6))
        land = y - BALL * 0.8
        hit = t + 0.22
        give = F.tf("translate", [(0, (0.0, 0.0)), (hit, (0.0, 0.0)), *tween(hit, 0.25, (0.0, 12.0), (0.0, 0.0), "back", 4)])
        out.append(f'<g>{F.slide(ti, 1100 if k % 2 else -1100, 0, 0.35, "back")}<g>{give}{bar(x, y, w, hb, cls)}'
                   + F.text(x + 24, y + hb / 2 + size * 0.36, word, size, "k", flip(cls)) + "</g></g>")
        pts += [(tt, bx, yy, BALL * 0.8) for tt, yy in tween(t, 0.22, pts[-1][2], land, "in", 4)][1:]
        pts.append((hit + 0.12, bx, land, BALL * 0.8))
        t = hit + 0.12
    pts += [(tt, bx, yy, BALL * 0.8) for tt, yy in tween(t, 0.35, pts[-1][2], H + 80, "in", 4)][1:]
    F.ball(pts)
    out.append(ring(bx, H / 2, 240, 2, F.c["ink"], ' stroke-dasharray="3 9" opacity=".45"'))
    return "".join(out)


def shot_count(word: str, count: int, ground: str) -> Draw:
    """A number, spun into place on a counter, and what it counts."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ink = flip(ground)
        s = str(count)
        out = [F.bg(ground), F.at(870, 470, disc(0, 0, 120, "night" if ground == "green" else "green"),
                                   F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.15, 0.4, (0.0, 0.0), (1.0, 1.0), "back", 5)]))]
        digits, wide = odo(F, 70, 360, s, 250, ink, t0 + 0.05)
        out.append(digits)
        x = 100 + wide
        size = min(96.0, (W - 40 - x) / max(capw(word.upper(), 1), 1e-6))
        out.append(f'<rect x="{n(x)}" y="306" width="0" height="12" class="{ink}">{F.grow("width", t0 + 0.3, 0.0, W - 40 - x)}</rect>')
        out.append(slam(F, t0 + 0.35, x, 280, word.upper(), size, ink))
        return "".join(out)
    return draw


def kind_of(fl: Flow) -> str:
    """What kind of loop a flow is, from its catalogue tag (or, failing that, its name)."""
    s = f"{fl.tag} {fl.name}".lower()
    for key, words in (("lanes", ("lane", "parallel")), ("cleaner", ("clean",)), ("checker", ("check", "review")),
                       ("relay", ("relay", "chase")), ("divide", ("divide", "recursive", "conquer"))):
        if any(w in s for w in words):
            return key
    return "loop"


def glyph(F: Film, kind: str, gx: float, gy: float, col: str, ink: str, t0: float, t1: float) -> str:
    """A kind of loop, acted out by shapes in a box of about 320 around (gx, gy)."""
    out = []
    hot = "cyan" if col == "green" else "green"   # the one thing that moves, against col
    if kind == "relay":   # two agents; the work goes back and forth between them
        out += [disc(gx - 110, gy, 60, col), disc(gx + 110, gy, 60, ink)]
        pts = []
        for j in range(4):
            a, b = (-110.0, 110.0) if j % 2 == 0 else (110.0, -110.0)
            for i in range(7):
                u = i / 6
                pts.append((t0 + 0.1 + 0.25 * (j + u), (a + (b - a) * EASE["io"](u), -150 * math.sin(math.pi * u))))
        out.append(f'<g>{F.tf("translate", pts)}{disc(gx - 110, gy, 18, hot)}</g>')
    elif kind == "checker":   # a maker hands its work to a checker, which signs it off
        out.append(f'<g>{F.tf("translate", [(0, (0.0, 0.0)), *tween(t0 + 0.15, 0.35, (0.0, 0.0), (120.0, 0.0), "back", 5)])}'
                   f'{bar(gx - 200, gy - 60, 120, 120, col)}</g>')
        out.append(f'<polygon points="{n(gx + 160)},{n(gy - 130)} {n(gx + 160)},{n(gy + 130)} {n(gx - 10)},{n(gy)}" class="{ink}"/>')
        out.append(f'<path d="M{n(gx - 160)} {n(gy + 110)}l60 60l130 -170" fill="none" stroke="{F.c[hot]}" stroke-width="22" '
                   f'pathLength="1" stroke-dasharray="1 1">{F.anim("stroke-dashoffset", [(0, 1), *tween(t0 + 0.55, 0.3, 1.0, 0.0, "out", 4)])}</path>')
    elif kind == "lanes":   # lanes at once, each at its own pace, to one line
        for j in range(4):
            out.append(f'<rect x="{n(gx - 170)}" y="{n(gy - 125 + 66 * j)}" width="0" height="46" class="{col if j % 2 == 0 else ink}">'
                       f'{F.anim("width", [(0, 0), *tween(t0 + 0.1 + 0.07 * j, 0.5 + 0.12 * j, 0.0, 330.0, "out", 6)])}</rect>')
        out.append(bar(gx + 168, gy - 150, 8, 300, hot))
    elif kind == "cleaner":   # a sweep clears the leftovers
        for i in range(6):
            for j in range(4):
                x = gx - 170 + 60 * i
                ts = t0 + 0.2 + 0.1 * i
                out.append(f'<rect x="{n(x)}" y="{n(gy - 115 + 60 * j)}" width="44" height="44" class="{col if (i + j) % 3 else ink}">'
                           f'{F.anim("opacity", [(0, 1), (ts, 1), (ts + 0.08, 0)], True)}</rect>')
        out.append(f'<g>{F.tf("translate", [(0, (0.0, 0.0)), (t0 + 0.15, (0.0, 0.0)), (t0 + 0.85, (370.0, 0.0))])}'
                   f'{bar(gx - 200, gy - 150, 18, 300, hot)}</g>')
    elif kind == "divide":   # a problem split, and split again
        for qx in (-1, 1):
            for qy in (-1, 1):
                ox, oy = gx + (55 * qx - 55), gy + (55 * qy - 55)
                mv = F.tf("translate", [(0, (0.0, 0.0)), *tween(t0 + 0.2, 0.3, (0.0, 0.0), (24.0 * qx, 24.0 * qy), "back", 5)])
                split = t0 + 0.6 + 0.05 * (qx + 1 + (qy + 1) // 2)
                whole = (f'<rect x="{n(ox)}" y="{n(oy)}" width="108" height="108" class="{col}">'
                         f'{F.anim("opacity", [(0, 1), (split, 1), (split + 0.04, 0)], True)}</rect>')
                cells = "".join(f'<rect x="{n(ox + 56 * a)}" y="{n(oy + 56 * b)}" width="52" height="52" '
                                f'class="{col if (a + b) % 2 == (qx > 0) else ink}" opacity="0">'
                                f'{F.anim("opacity", [(0, 0), (split, 0), (split + 0.04, 1)], True)}</rect>'
                                for a in (0, 1) for b in (0, 1))
                out.append(f"<g>{mv}{whole}{cells}</g>")
    else:   # a loop: round and round until it is done
        out.append(ring(gx, gy, 120, 26, F.c[col]))
        out.append(F.at(gx, gy, disc(120, 0, 30, ink), F.spin(t0, t1, -90.0, 630.0)))
    return "".join(out)


def shot_flowkind(i: int, kind: str, tag: str, count: int) -> Draw:
    """One kind of loop: its shapes acting it out, its name, one square per flow of the kind."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("paper", "slab")[i % 2]
        ink = flip(ground)
        col = accent(i // 2)
        out = [F.bg(ground)]
        out.append(F.at(0, 0, glyph(F, kind, 280, 290, col, ink, t0, t1),
                        F.tf("scale", [(0, (1.0, 1.0))])))
        size, lines = fitlines(tag.upper(), 430, 66, 28, 2)
        for j, ln in enumerate(lines):
            out.append(slam(F, t0 + 0.1 + 0.08 * j, 520, 250 + size * 1.05 * j, ln, size, ink))
        y = 250 + size * 1.05 * (len(lines) - 1) + 40
        for k in range(count):
            out.append(F.pop(t0 + 0.35 + 0.06 * k, 532 + 40 * k, y + 12, bar(-12, -12, 24, 24, col), 0.0, 0.25))
        return "".join(out)
    return draw


def shot_project(i: int, p: Project) -> Draw:
    """A project: its name cut deep on the left, a figure turning on the right -- green for the
    runtime, paper and slab by turns for the rest."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = "green" if p.name.lower() == "humanize" else ("paper", "slab")[i % 2]
        ink = flip(ground)
        shape = "night" if ground == "green" else accent(i // 2)
        shade = "onslab" if ground == "green" else shape
        word = p.name.upper()
        size = min(180.0, 500 / max(capw(word, 1), 1e-6))
        ww = capw(word, size)
        out = [F.bg(ground)]
        v = i % 3
        if v == 0:
            out.append(F.at(790, 280, disc(0, 0, 190, shape) + bar(-190, -9, 380, 18, ground), F.spin(t0, t1, -20.0, 40.0),
                            F.tf("scale", [(0, (0.0, 0.0)), *tween(t0, 0.4, (0.0, 0.0), (1.0, 1.0), "back", 6)])))
        elif v == 1:
            out.append(f'<g>{F.slide(t0, 600, 0, 0.4, "back")}<polygon points="{n(W)},0 {n(W)},{n(H)} {n(W - 330)},{n(H)}" class="{shape}"/></g>')
            out.append(F.at(780, 150, ring(0, 0, 56, 12, F.c[ink]), F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.3, 0.3, (0.0, 0.0), (1.0, 1.0), "back", 5)])))
        else:
            for k in range(4):
                out.append(f'<g>{F.slide(t0 + 0.06 * k, 1100, 0, 0.35, "back")}{bar(W - 120 - 70 * k, 120 + 60 * k, 70 + 70 * k, 26, shape if k % 2 == 0 else ink)}</g>')
        out.append(tilt(60, 300, f'<g>{F.tf("translate", [(0, (-1200.0, 0.0)), *tween(t0 + 0.08, 0.38, (-1200.0, 0.0), (0.0, 0.0), "back", 6), (t1, (24.0, 0.0))])}'
                    + F.text(8, size * 0.35 + 8, word, size, "k", shade, extra=f' textLength="{n(ww)}" lengthAdjust="spacingAndGlyphs"')
                    + F.text(0, size * 0.35, word, size, "k", ink, extra=f' textLength="{n(ww)}" lengthAdjust="spacingAndGlyphs"')
                    + "</g>", -ANGLE / 2))
        return "".join(out)
    return draw


def figure(num: str) -> tuple[str, tuple[float, ...]]:
    """What a headline number is, so it can be drawn: a share, a rank, a multiple, a count..."""
    s = num.replace(",", "")
    for kind, pat in (("frac", r"(\d+)/(\d+)"), ("rank", r"#(\d+)"), ("lift", r"\+(\d+(?:\.\d+)?)%"),
                      ("pct", r"(\d+(?:\.\d+)?)%"), ("times", r"(\d+(?:\.\d+)?)×"), ("count", r"(\d+)\+?"), ("score", r"(\d*\.\d+)")):
        m = re.fullmatch(pat, s)
        if m:
            return kind, tuple(float(g_) for g_ in m.groups())
    return "mark", ()


def chart(F: Film, kind: str, v: tuple[float, ...], x: float, y: float, w: float, h: float, col: str, ink: str, t: float) -> str:
    """A number drawn as shapes, in the box (x, y, w, h), building from t."""
    cx, cy = x + w / 2, y + h / 2
    if kind == "frac" and 0 < v[1] <= 64:
        a, b = int(v[0]), int(v[1])
        cols = max(1, math.ceil(math.sqrt(b * w / h)))
        rows = math.ceil(b / cols)
        cell = min(w / cols, h / rows)
        out = []
        for i in range(b):
            px, py = x + (i % cols) * cell + cell / 2, y + (i // cols) * cell + cell / 2
            sq = bar(-cell * 0.42, -cell * 0.42, cell * 0.84, cell * 0.84, col if i < a else ink,
                     "" if i < a else ' opacity=".18"')
            out.append(F.pop(t + 0.7 * i / b, px, py, sq, 0.0, 0.25))
        return "".join(out)
    if kind in ("frac", "score"):
        share = min(1.0, v[0] / v[1]) if kind == "frac" and v[1] else min(1.0, v[0])
        r = min(w, h) / 2 - 20
        return (ring(cx, cy, r, 34, F.c[ink], ' opacity=".15"')
                + f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="none" stroke="{F.c[col]}" stroke-width="34" pathLength="1" '
                  f'stroke-dasharray="1 1" transform="rotate(-90 {n(cx)} {n(cy)})">{F.anim("stroke-dashoffset", [(0, 1), *tween(t, 0.8, 1.0, 1 - share, "out", 8)])}</circle>'
                + F.pop(t + 0.7, cx, cy, disc(0, 0, r * 0.35, col), 0.0, 0.3))
    if kind == "pct":
        bw = w * 0.42
        hh = h * min(1.0, v[0] / 100)
        return (bar(cx - bw / 2, y, bw, h, ink, ' opacity=".15"') + bar(cx - bw / 2 - 20, y - 6, bw + 40, 6, ink)
                + f'<rect x="{n(cx - bw / 2)}" y="{n(y + h)}" width="{n(bw)}" height="0" class="{col}">'
                  f'{F.anim("y", [(0, y + h), *tween(t, 0.7, y + h, y + h - hh, "back", 6)])}{F.anim("height", [(0, 0), *tween(t, 0.7, 0.0, hh, "back", 6)])}</rect>')
    if kind in ("times", "lift"):
        k = v[0] if kind == "times" else 1 + v[0] / 100
        hi = h
        lo = h / max(k, 1.0)
        out = []
        for j, (hh, cls) in enumerate(((lo, ink), (hi, col))):
            bx = x + w * (0.1 + 0.48 * j)
            out.append(f'<rect x="{n(bx)}" y="{n(y + h)}" width="{n(w * 0.34)}" height="0" class="{cls}"{"" if j else " opacity=\".35\""}>'
                       f'{F.anim("y", [(0, y + h), *tween(t + 0.15 * j, 0.6, y + h, y + h - hh, "back", 6)])}'
                       f'{F.anim("height", [(0, 0), *tween(t + 0.15 * j, 0.6, 0.0, hh, "back", 6)])}</rect>')
        out.append(F.pop(t + 0.7, x + w * 0.75, y - 30, f'<polygon points="-26,16 0,-22 26,16" class="{col}"/>', 0.0, 0.3))
        return "".join(out)
    if kind == "rank" and v[0] <= 3:
        out = []
        steps = ((2, 0.62), (1, 1.0), (3, 0.42))
        sw = w / 3
        for j, (place, k) in enumerate(steps):
            hh = h * 0.7 * k
            cls = col if place == v[0] else ink
            out.append(f'<g>{F.slide(t + 0.08 * j, 0, h + 60, 0.4, "back")}{bar(x + sw * j, y + h - hh, sw - 6, hh, cls, "" if place == v[0] else " opacity=\".3\"")}</g>')
            if place == v[0]:
                top = y + h - hh
                out.append(f'<circle cx="{n(x + sw * j + sw / 2 - 3)}" cy="-60" r="26" class="{ink}">'
                           f'{F.anim("cy", [(0, -60), *tween(t + 0.4, 0.35, -60.0, top - 26, "in", 5), *tween(t + 0.75, 0.2, top - 50, top - 26, "in", 3)[1:]])}</circle>')
        return "".join(out)
    if kind == "count" and 1 <= v[0] <= 120:
        return chart(F, "frac", (v[0], v[0]), x, y, w, h, col, ink, t)
    if kind in ("count", "rank"):
        out = [F.pop(t, cx, cy, disc(0, 0, min(w, h) * 0.18, col), 0.0, 0.3)]
        for j in range(24):
            a = 360 * j / 24
            out.append(f'<g transform="translate({n(cx)} {n(cy)}) rotate({n(a)})"><rect x="{n(min(w, h) * 0.22)}" y="-5" height="10" width="0" class="{col if j % 3 == 0 else ink}">'
                       f'{F.anim("width", [(0, 0), *tween(t + 0.02 * j, 0.4, 0.0, min(w, h) * (0.18 + 0.1 * (j % 3)), "back", 5)])}</rect></g>')
        return "".join(out)
    return (F.pop(t, cx, cy, disc(0, 0, min(w, h) * 0.42, col), 0.0, 0.35)
            + f'<path d="M{n(cx - 70)} {n(cy)}l50 50l100 -110" fill="none" stroke="{F.c["night"]}" stroke-width="24" pathLength="1" '
              f'stroke-dasharray="1 1">{F.anim("stroke-dashoffset", [(0, 1), *tween(t + 0.3, 0.3, 1.0, 0.0, "out", 4)])}</path>')


def stamp(F: Film, t: float, x: float, y: float) -> str:
    """NEW, stamped on at an angle."""
    body = bar(-62, -26, 124, 52, "pink") + F.text(0, 13, "NEW", 34, "k", "night", "middle")
    return F.at(x, y, f'<g transform="rotate(-12)">{body}</g>',
                F.tf("scale", [(0, (0.0, 0.0)), (t, (3.0, 3.0)), *tween(t, 0.25, (3.0, 3.0), (1.0, 1.0), "back", 5)[1:]]))


def shot_achievement(i: int, a: Achievement, new: bool) -> Draw:
    """One achievement: its number spun onto a counter, drawn as shapes beside it, one line of what
    it is -- and, if it is new, stamped so."""
    def draw(F: Film, t0: float, t1: float) -> str:
        ground = ("paper", "slab")[i % 2]
        ink = flip(ground)
        col = accent(i // 2)
        out = [F.bg(ground), tilt(-40, 548, f'<g>{F.slide(t0, -1200, 0, 0.35)}{bar(0, 0, 1300, 14, col)}</g>', -3)]
        num = a.num
        if num:
            room = 560.0
            size = min(210.0, room / max(0.74 * sum(0.45 if ch in ".,:" else 1.0 for ch in num), 1e-6))
            digits, _ = odo(F, 60, 120 + size * 0.8, num, size, ink, t0 + 0.05)
            out.append(digits)
            kind, v = figure(num)
            out.append(chart(F, kind, v, 650, 80, 290, 290, col, ink, t0 + 0.2))
            lines = wrap(a.label, 30, 860, 2, True)
            for j, ln in enumerate(lines):
                out.append(f'<g>{F.slide(t0 + 0.4 + 0.08 * j, -900, 0, 0.35, "out")}' + F.text(60, 425 + 38 * j, ln, 30, "b", ink) + "</g>")
        else:
            size, lines = fitlines(a.label.upper(), 560, 64, 30, 4)
            for j, ln in enumerate(lines):
                out.append(slam(F, t0 + 0.1 + 0.08 * j, 60, 140 + size * 1.05 * j, ln, size, ink))
            out.append(chart(F, "mark", (), 650, 80, 290, 290, col, ink, t0 + 0.2))
        if new:
            out.append(stamp(F, t0 + 0.55, 860, 470))
        return "".join(out)
    return draw


def shot_wall(page: list[Achievement], first: int) -> Draw:
    """The rest of the achievements, slabs stamped onto a wall: a number in green and a line each."""
    def draw(F: Film, t0: float, t1: float) -> str:
        cols = 4 if len(page) > 6 else 3
        rows = math.ceil(len(page) / cols)
        gap = 14.0
        pw = (W - 80 - gap * (cols - 1)) / cols
        ph = min(150.0, (H - 80 - gap * (rows - 1)) / rows)
        y0 = (H - rows * ph - (rows - 1) * gap) / 2
        out = [F.bg("paper")]
        for k, a in enumerate(page):
            x, y = 40 + (k % cols) * (pw + gap), y0 + (k // cols) * (ph + gap)
            num = a.num or "✓"
            size = min(52.0, (pw - 40) / max(capw(num, 1), 1e-6))
            body = (bar(0, 0, pw, ph, "slab") + bar(0, 0, 8, ph, "green") + F.text(22, 16 + size * 0.8, num, size, "k", "green")
                    + "".join(F.text(22, 16 + size + 14 + 18 * j, ln, 14, "b", "onslab")
                              for j, ln in enumerate(wrap(a.label, 14, pw - 36, 2, True))))
            ti = t0 + 0.08 + 0.07 * k
            rot = 4.0 if k % 2 else -4.0
            out.append(F.at(x + pw / 2, y + ph / 2, f'<g transform="translate({n(-pw / 2)} {n(-ph / 2)})">{body}</g>',
                            F.tf("rotate", [(0, rot), *tween(ti, 0.35, rot, 0.0, "back", 5)]),
                            F.tf("scale", [(0, (0.0, 0.0)), *tween(ti, 0.3, (0.0, 0.0), (1.0, 1.0), "back", 5)])))
        return "".join(out)
    return draw


def shot_people(F: Film, t0: float, t1: float) -> str:
    """The people burst out of the ball onto rings, and the rings turn; nobody is singled out."""
    people = F.f.people
    cx, cy = W / 2, H / 2
    out = [F.bg("paper"), tilt(cx, cy, f'<g>{F.slide(t0, 1400, 0, 0.4)}{bar(-700, -30, 1400, 60, "cyan")}</g>'),
           F.at(cx, cy, disc(0, 0, 70, "ink"), F.tf("scale", [(0, (0.0, 0.0)), *tween(t0 + 0.05, 0.3, (0.0, 0.0), (1.0, 1.0), "back", 5)]))]
    radii, left, R = [], len(people), 240.0
    while left > 0 and R > 80:
        cap = max(1, int(2 * math.pi * R / 78))
        radii.append((R, min(cap, left)))
        left -= min(cap, left)
        R -= 85
    k = 0
    for ri, (R, m) in enumerate(radii):
        spin = 30.0 if ri % 2 == 0 else -30.0
        items = []
        for j in range(m):
            if k >= len(people):
                break
            p = people[k]
            a = 2 * math.pi * j / m - math.pi / 2 + ri * 0.3
            px, py = R * math.cos(a), R * math.sin(a)
            cid = F.uid("face")
            if p.face:
                face = (f'<clipPath id="{cid}"><circle r="32"/></clipPath>'
                        f'<image href="{p.face}" x="-32" y="-32" width="64" height="64" clip-path="url(#{cid})"/>')
            else:
                initials = "".join(w[0] for w in p.name.split()[:2]).upper() or p.handle[:2].upper()
                face = disc(0, 0, 32, "alt") + F.text(0, 7, initials, 20, "k", "ink", "middle")
            face += ring(0, 0, 32, 4, F.c["ink"])
            ti = t0 + 0.25 + 0.04 * k
            moved = F.tf("translate", [(0, (0.0, 0.0)), *tween(ti, 0.4, (0.0, 0.0), (px, py), "back", 6)])
            upright = F.tf("rotate", [(0, 0.0), (t0 + 1.2, 0.0), (t1, -spin)])
            items.append(f'<g>{moved}<g>{upright}{face}</g></g>')
            k += 1
        out.append(F.at(cx, cy, "".join(items), F.tf("rotate", [(0, 0.0), (t0 + 1.2, 0.0), (t1, spin)])))
    F.ball([(t0, cx, cy, 0.0), *[(t, cx, cy, r) for t, r in tween(t0, 0.25, 0.0, 40.0, "back", 4)][1:],
            (t0 + 0.4, cx, cy, 40.0), (t1, cx, cy, 40.0)])
    return "".join(out)


def shot_outro(F: Film, t0: float, t1: float) -> str:
    """Green. The H in night, the site's name slammed down, the ball drops home in night -- then a
    paper plane sweeps the frame, and it all begins again."""
    sx, sy, sr = mark_defs(F.sh, F.f.logo)
    hx, hy, k = 210.0, 260.0, 0.8
    out = [F.bg("green"),
           f'<g>{F.slide(t0 + 0.2, 0, 500, 0.4, "back")}{bar(380, 340, 560, 26, "night")}</g>',
           f'<g>{F.slide(t0 + 0.3, 500, 0, 0.4, "back")}{ring(880, 110, 60, 12, F.c["night"])}</g>',
           tilt(700, 470, f'<g>{F.slide(t0 + 0.4, -1200, 0, 0.4, "back")}{bar(-300, -5, 600, 10, "onslab")}</g>'),
           F.at(hx, hy, f'<use href="#hshape" class="night" transform="scale({n(k)})"/>',
                F.tf("scale", [(0, (0.3, 0.3)), *tween(t0, 0.4, (0.3, 0.3), (1.0, 1.0), "back", 6)]))]
    site = SITE.split("//", 1)[-1].upper()
    size = min(92.0, 560 / max(capw(site, 1), 1e-6))
    out.append(slam(F, t0 + 0.3, 380, 300, site, size, "night"))
    slot = (hx + sx * k, hy + sy * k, sr * k)
    land = t0 + 0.9
    F.ball([(land - 0.4, slot[0], -60, slot[2]), *[(t, slot[0], y, slot[2]) for t, y in tween(land - 0.4, 0.4, -60.0, slot[1], "in", 5)][1:],
            *[(t, slot[0], slot[1], r) for t, r in tween(land, 0.2, slot[2] * 1.4, slot[2], "back", 3)], (t1, *slot)])
    F.ball_ink = (land - 0.4, t1)
    out.append(f'<g>{F.tf("translate", [(0, (1500.0, 0.0)), (t1 - 0.45, (1500.0, 0.0)), (t1, (0.0, 0.0))])}'
               f'<polygon points="{n(-200)},0 {n(W + 200)},0 {n(W + 200)},{n(H)} {n(-200 - H * SLOPE * 2)},{n(H)}" class="paper"/></g>')
    return "".join(out)


SOLO = 8      # achievements with a shot of their own, at least: every new one gets one
PAGE = 12     # achievements on a wall


def storyboard(f: Facts, today: dt.date | None = None) -> list[Shot]:
    """The cut: a section is in only if the site gave it something to show."""
    today = today or dt.date.today()
    s = [Shot("open", 3.2, shot_open), Shot("mark", 3.2, shot_mark)]
    if f.headline:
        s.append(Shot("headline", 3.0, shot_headline, "whip"))
    num = 0

    def wipe(title: str, ground: str) -> None:
        nonlocal num
        num += 1
        s.append(Shot(f"wipe-{title}", 1.1, shot_wipe(num, title, ground), "whip"))

    if f.bands:
        wipe("Runtime", "slab")
        s.append(Shot("runtime", 1.4 + 0.5 * len(f.bands[:5]), shot_runtime, "punch"))
    if f.flows:
        num += 1
        s.append(Shot("flows", 1.6, shot_count("Flows", len(f.flows), "green"), "whip"))
        kinds: dict[str, list[Flow]] = {}
        for fl in f.flows:
            kinds.setdefault(kind_of(fl), []).append(fl)
        for i, (kind, fls) in enumerate(kinds.items()):
            tag = next((fl.tag for fl in fls if fl.tag), kind)
            s.append(Shot(f"kind-{kind}", 1.2, shot_flowkind(i, kind, tag, len(fls)), "punch"))
    if f.projects:
        wipe("Projects", "green")
        for i, p in enumerate(f.projects[:8]):
            s.append(Shot(f"project{i}", 1.4, shot_project(i, p), "whip"))
    if f.achievements:
        num += 1
        s.append(Shot("achievements", 1.6, shot_count("Achievements", len(f.achievements), "slab"), "whip"))
        order = lineup(f.achievements, today)
        new = sum(fresh(a, today) for a in order)
        solo = order[:max(SOLO, new)]
        for i, a in enumerate(solo):
            s.append(Shot(f"achievement{i}", 1.5, shot_achievement(i, a, fresh(a, today)), "punch"))
        rest = order[len(solo):]
        per = math.ceil(len(rest) / math.ceil(len(rest) / PAGE)) if rest else PAGE
        for k in range(0, len(rest), per):
            page = rest[k:k + per]
            s.append(Shot(f"wall{k // per}", 1.3 + 0.08 * len(page), shot_wall(page, k), "rise"))
    if f.people:
        wipe("People", "slab")
        s.append(Shot("people", 3.4, shot_people, "punch"))
    s.append(Shot("outro", 3.4, shot_outro))
    return s


def film(theme: str, f: Facts, today: dt.date | None = None) -> str:
    """The banner: every shot on one clock, cut together, with the ball on top of them all."""
    plan = storyboard(f, today)
    T = sum(s.seconds for s in plan)
    F = Film(theme, f, T)
    layers, t = [], 0.0
    nexts = [s.enter for s in plan[1:]] + ["cut"]
    for s, nxt in zip(plan, nexts):
        t0, t1 = t, t + s.seconds
        body = s.draw(F, t0, t1)
        a, b = t0, t1
        moves = []
        if s.enter == "whip":
            a = t0 - 0.16
            moves.append(F.tf("translate", [(0, (W + 40, 0.0)), *tween(a, 0.3, (W + 40, 0.0), (0.0, 0.0), "out", 6)]))
        elif s.enter == "punch":
            moves.append(F.tf("scale", [(0, (1.15, 1.15)), *tween(t0, 0.2, (1.15, 1.15), (1.0, 1.0), "out", 4)]))
        elif s.enter == "rise":
            moves.append(F.tf("translate", [(0, (0.0, H)), *tween(t0, 0.3, (0.0, H), (0.0, 0.0), "out", 5)]))
        if nxt == "whip":
            moves.append(F.tf("translate", [(0, (0.0, 0.0)), *tween(t1 - 0.16, 0.16, (0.0, 0.0), (-W - 40, 0.0), "in", 4)]))
            b = t1 + 0.16
        inner = body
        for m in moves:
            inner = (f'<g transform="translate({n(W / 2)} {n(H / 2)})"><g>{m}<g transform="translate({n(-W / 2)} {n(-H / 2)})">{inner}</g></g></g>'
                     if "scale" in m[:80] else f"<g>{m}{inner}</g>")
        layers.append(f'<g display="{"inline" if a <= 0 else "none"}">{F.show(a, b)}{inner}</g>')
        if nxt == "whip":  # the whip's speed lines, in every colour
            streaks = "".join(bar(0, 50 + 95 * k, 260 + 120 * (k % 3), 8 + 6 * (k % 2), ("green", "ink")[k % 2]) for k in range(5))
            layers.append(f'<g display="none">{F.show(t1 - 0.2, t1 + 0.2)}<g>{F.tf("translate", [(0, (W, 0.0)), (t1 - 0.2, (W, 0.0)), (t1 + 0.2, (-700.0, 0.0))])}{streaks}</g></g>')
        t = t1
    # The ball: one actor, on top of every shot it is in.
    keys = sorted(F.ball_keys, key=lambda k: k[0])
    on = [(0.0, "0")]
    for a, b in sorted(F.ball_on):
        on += [(a, "1"), (b, "0")]
    motion = (F.anim("cx", [(tt, v[0]) for tt, v in keys]) + F.anim("cy", [(tt, v[1]) for tt, v in keys])
              + F.anim("r", [(tt, v[2]) for tt, v in keys]))
    if F.ball_ink:  # at the end the ball is night, on green
        a, b = F.ball_ink
        green_on = sorted([(tt, v if not (a <= tt < b) else "0") for tt, v in on] + [(a, "0"), (b, "0")], key=lambda k: k[0])
        ball = (f'<circle r="0" class="green">{motion}{F.anim("opacity", green_on, True)}</circle>'
                f'<circle r="0" class="night">{motion}{F.anim("opacity", [(0.0, "0"), (a, "1"), (b, "0")], True)}</circle>')
    else:
        ball = f'<circle r="0" class="green">{motion}{F.anim("opacity", on, True)}</circle>'
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
    alt = (f"Humanfia: {f.headline or 'we build the flow around the agents'} A one-minute constructivist film of "
           f"the mark, the runtime, the flows, the projects, {len(f.achievements)} achievements and the people, "
           "generated from humanfia.ai.")
    return README.format(site=SITE, alt=esc(" ".join(alt.split())))


# ----------------------------------------------------------------------------------------- main

def main() -> None:
    themes = [os.environ["THEME"]] if os.environ.get("THEME") else ["light", "dark"]
    facts = gather()
    today = dt.date.today()
    old = load_ledger()
    facts.achievements = achievements(facts, old, today, lambda path: fetch(path) is not None)
    added = {a.href for a in facts.achievements} - {r["href"] for r in old}
    for theme in themes:
        out = PROFILE / f"humanfia-portfolio-{theme}.svg"
        out.write_text(film(theme, facts, today), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    (PROFILE / "README.md").write_text(readme(facts), encoding="utf-8")
    save_ledger(facts.achievements)
    print(f"{len(facts.achievements)} achievements, {len(added)} new: {', '.join(sorted(added)) or 'none'}")
    if (PROFILE / ART).exists():
        shutil.rmtree(PROFILE / ART)  # the poster wall this replaced


if __name__ == "__main__":
    main()
