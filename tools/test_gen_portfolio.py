"""Offline tests for gen_portfolio.py and proun.py: how the site is read, and the posters drawn.

    python3 -m unittest discover -s tools -p 'test_*.py'
"""

import io
import re
import unittest
import urllib.error
from unittest import mock
from xml.etree import ElementTree as ET

import gen_portfolio as g
import proun as P

NAV = """<nav class="VPNavBarMenu menu"><span>Main Navigation</span>
<div class="VPFlyout VPNavBarMenuGroup"><button type="button" class="button"><span class="text"><span>Projects</span></span></button>
<div class="menu"><div class="VPMenu"><div class="items">
<div class="VPMenuLink"><a class="VPLink link" href="/projects/humanize"><span>Humanize</span></a></div>
<div class="VPMenuLink"><a class="VPLink link" href="/projects/kda"><span>KDA</span></a></div>
</div></div></div></div>
<a class="VPLink link VPNavBarMenuLink" href="/flows/"><span>Flows</span></a>
<a class="VPLink link VPNavBarMenuLink" href="/blog/"><span>Blog</span></a>
<a class="VPLink link VPNavBarMenuLink" href="/about/"><span>About</span></a>
</nav><nav class="VPNavBarMenu"><a class="VPNavBarMenuLink" href="/x/">Second nav, ignored</a></nav>"""

HOME = """<html><head><title>Humanfia — we build the flow around the agents</title></head><body>
<section class="h-hero"><p class="h-kicker">Open-source agent flows</p><h1>We build the flow around the agents.</h1>
<p class="h-lead">The runtime, the flows and the referee.</p></section>
<section class="h-manifesto"><ol class="h-manifesto-acts"><li>Models improve.</li><li class="last">We build the flow.</li></ol></section>
<div class="h-feature"><h3>A budget it keeps</h3><p>Stop on time.</p></div>
<a class="h-tile w4" href="/news/imo"><span class="h-tile-label">IMO 2026</span><span class="h-tile-num">6/6</span>
<span class="h-tile-body">Every problem.</span></a></body></html>"""

DOCS = """<div class="arch"><div class="stack">
<section class="band"><header><h3>Flows</h3><p>what the work is</p></header><ul class="chips"><li><span>chat</span></li></ul></section>
<p class="down"><span class="arrow"></span> a turn: a prompt, on one conversation, at a model and an effort</p>
<section class="band"><header><h3>Coding agents</h3><p>the model</p></header>
<ul class="chips"><li><span>claude</span></li><li><span>dsh<small>SDK</small></span></li><li><span>litellm<small>a model call</small></span></li></ul></section>
</div></div>"""

FLOWS = """<main><div class="mosaic">
<a class="xl wash tile" href="/flows/flame-chase"><div class="pic"><svg></svg></div><p class="tile-meta"><span class="tile-tag">A relay</span>
<span>ships with humanize</span></p><h3>flame_chase</h3><p class="tile-blurb">Two agents take turns.</p>
<div class="tile-foot"><dl><div><dt>-a</dt><dd>first_chaser · second_chaser</dd></div><div><dt>ends</dt><dd>3 failed turns</dd></div></dl></div></a>
<a class="sm tile" href="/flows/parallel"><p class="tile-meta"><span class="tile-tag">Lanes at once</span><span>flowverse · v0.1.0</span></p>
<h3>flame_chasoid:<wbr>parallel</h3><p class="tile-blurb">Three lanes.</p></a>
<a class="sm tile" href="/flows/parallel"><h3>a duplicate</h3></a>
<a class="other" href="/flows/x"><h3>not a tile</h3></a></div></main>"""

PROJECT = """<main><p class="hz-kicker">Humanize · the agent flow system</p><h1 class="hero-title">One flow.<br>Every agent.</h1>
<p class="hz-lead">Humanize drives the CLI you log into. More.</p></main>"""

KDA = """<main><p class="hero-status kd-kicker"><span>Project</span>Open research · built with a lab</p>
<h1 class="hero-title"><span class="hero-main">KDA</span><span class="hero-sub">Kernel Design Agents</span></h1>
<p class="hero-stand">An agent workflow for kernels. More.</p></main>"""

ABOUT = """<main><p class="lede">We build. These are the people who do it.</p>
<li class="person"><a class="person-face" href="https://github.com/futrime"><img src="https://example.com/a.png"></a>
<p class="person-name">Zijian Zhang <span class="lead">Lead</span></p><p class="person-handle"><a href="https://github.com/futrime">@futrime</a></p></li>
<p>The bet. We think the loop is what lasts — models are rented.</p>
<ul class="principles"><li><b>The builder is not the judge.</b> More.</li><li><b>Build in public.</b></li></ul>
<div class="contact"><a href="https://github.com/humanfia"><b>A question</b><span>Open an issue.</span></a></div></main>"""

LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><title id="t">H</title>
<rect x="6" y="4" width="13" height="56" fill="#000"/>
<g transform="translate(2 0) scale(2)"><circle id="dot" cx="25" cy="4" r="3" fill="#d6331f"/></g></svg>"""

RSS = ('<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>A</title><link>https://h/news/a</link>'
       "<pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate><dc:creator>Ann, Bo</dc:creator></item></channel></rss>")


def facts() -> g.Facts:
    f = g.Facts(g.parse_logo(LOGO))
    g.home_facts(f, g.dom(HOME))
    g.docs_facts(f, g.dom(DOCS))
    with mock.patch.object(g, "fetch", return_value=FLOWS):
        g.flow_facts(f, g.parse_nav(g.dom(NAV)))
    f.projects = [g.Project("KDA", "https://humanfia.ai/projects/kda", "Kernel Design Agents", "An agent workflow.")]
    f.posts = [g.Post("NEWS", "Title & <more>", "https://x", 0, "Oct 2, 2026", "Ann")]
    f.people = [g.Person("Zijian Zhang", "futrime"), g.Person("Ann Bo", "annbo", "data:image/png;base64,AAAA")]
    f.principles, f.contact = ["The builder is not the judge.", "Build in public."], [("A question", "https://github.com/humanfia")]
    return f


class Reading(unittest.TestCase):
    def test_nav_flyouts_and_links_from_the_first_nav_only(self) -> None:
        nav = g.parse_nav(g.dom(NAV))
        self.assertEqual([m.label for m in nav], ["Projects", "Flows", "Blog", "About"])
        self.assertEqual(nav[0].items, [("Humanize", "/projects/humanize"), ("KDA", "/projects/kda")])
        self.assertEqual(g.find(nav, "flows").href, "/flows/")

    def test_home_and_docs(self) -> None:
        f = facts()
        self.assertEqual((f.kicker, f.headline), ("Open-source agent flows", "We build the flow around the agents."))
        self.assertEqual(f.lead, "The runtime, the flows and the referee.")
        self.assertEqual(f.acts, ["Models improve.", "We build the flow."])
        self.assertEqual(f.features, [("A budget it keeps", "Stop on time.")])
        self.assertEqual(f.results, [g.Result("IMO 2026", "6/6", "Every problem.", "https://humanfia.ai/news/imo")])
        self.assertEqual([b.title for b in f.bands], ["Flows", "Coding agents"])
        self.assertEqual(f.bands[0].down, "a turn: a prompt, on one conversation, at a model and an effort")
        self.assertEqual(f.bands[1].chips, [("claude", ""), ("dsh", "SDK"), ("litellm", "a model call")])

    def test_the_old_one_paragraph_manifesto_still_reads(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        g.home_facts(f, g.dom('<p class="h-manifesto-text"><span>Models get better. </span><span>The flow lasts.</span></p>'))
        self.assertEqual(f.acts, ["Models get better.", "The flow lasts."])

    def test_flows_come_from_the_catalogue_tiles_once_each(self) -> None:
        f = facts()
        self.assertEqual([(fl.name, fl.tag, fl.href) for fl in f.flows],
                         [("flame_chase", "A relay", "https://humanfia.ai/flows/flame-chase"),
                          ("flame_chasoid:parallel", "Lanes at once", "https://humanfia.ai/flows/parallel")])
        self.assertEqual((f.flows[0].roles, f.flows[0].ends, f.flows[0].source),
                         (["first_chaser", "second_chaser"], "3 failed turns", "ships with humanize"))
        self.assertEqual([g.pattern(fl.tag, fl.name) for fl in f.flows], ["relay", "lanes"])

    def test_a_project_says_what_it_is_from_its_subtitle_or_its_kicker(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        pages = {"/projects/humanize": PROJECT, "/projects/kda": KDA}
        with mock.patch.object(g, "fetch", side_effect=lambda p: pages.get(p)):
            g.project_facts(f, g.parse_nav(g.dom(NAV)))
        self.assertEqual([(p.name, p.sub, p.lede) for p in f.projects],
                         [("Humanize", "the agent flow system", "Humanize drives the CLI you log into."),
                          ("KDA", "Kernel Design Agents", "An agent workflow for kernels.")])

    def test_a_project_page_that_is_gone_still_counts(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        with mock.patch.object(g, "fetch", return_value=None):
            g.project_facts(f, g.parse_nav(g.dom(NAV)))
        self.assertEqual([(p.name, p.sub) for p in f.projects], [("Humanize", ""), ("KDA", "")])

    def test_people_principles_contact_and_the_bet(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        with mock.patch.object(g, "fetch", return_value=ABOUT), mock.patch.object(g, "avatar", return_value=""):
            g.people_facts(f, [g.Menu("About", "/about/")])
        self.assertEqual([(p.name, p.handle) for p in f.people], [("Zijian Zhang", "futrime")])
        self.assertEqual(f.principles, ["The builder is not the judge.", "Build in public."])
        self.assertEqual(f.contact, [("A question", "https://github.com/humanfia")])
        self.assertEqual(f.bet, "We think the loop is what lasts — models are rented.")

    def test_feed_reads_authors_and_survives_a_missing_feed(self) -> None:
        with mock.patch.object(g, "fetch", side_effect=lambda p: RSS if "news" in p else None):
            posts = g.latest()
        self.assertEqual([(p.kind, p.title, p.date, p.by) for p in posts], [("NEWS", "A", "Oct 2, 2026", "Ann, Bo")])


class Fetching(unittest.TestCase):
    def _http(self, code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO())  # type: ignore[arg-type]

    def test_only_404_and_410_mean_absent(self) -> None:
        for code in (404, 410):
            with mock.patch("urllib.request.urlopen", side_effect=self._http(code)):
                self.assertIsNone(g.fetch("/news/feed.rss"))

    def test_other_failures_stop_the_run_after_retrying(self) -> None:
        for err in (self._http(403), self._http(429), self._http(503), TimeoutError(), ConnectionResetError()):
            with mock.patch("urllib.request.urlopen", side_effect=err) as urlopen, \
                    mock.patch("time.sleep"), self.assertRaises(SystemExit):
                g.fetch("/")
            self.assertEqual(urlopen.call_count, 3)


class Logo(unittest.TestCase):
    def test_finds_the_dot_through_transforms_and_removes_it(self) -> None:
        logo = g.parse_logo(LOGO)
        self.assertEqual(logo.viewbox, (0, 0, 64, 64))
        self.assertEqual(logo.dot, (52, 8, 6))
        self.assertNotIn("circle", logo.body)
        self.assertNotIn("<title", logo.body)
        self.assertNotIn("fill=", logo.body)

    def test_editor_namespaces_are_dropped_and_xlink_kept(self) -> None:
        src = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
               'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" viewBox="0 0 10 10">'
               '<defs><path id="p" d="M0 0h1z"/></defs><use xlink:href="#p" inkscape:label="x"/>'
               "<inkscape:thing/></svg>")
        logo = g.parse_logo(src)
        self.assertNotIn("inkscape", logo.body)
        self.assertIn('xlink:href="#logo-p"', logo.body)


class Geometry(unittest.TestCase):
    def test_rotations_are_orthonormal(self) -> None:
        m = P.rot(37, -21, 8)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(sum(m[i][k] * m[j][k] for k in range(3)), float(i == j))

    def test_a_solid_shows_each_face_only_while_it_faces_you(self) -> None:
        cube = P.box(10, 10, 10)
        front = P.rot(0, 0)
        svg = cube.draw([front, front], 1, (0, 0), 1, "#ffffff", "#000000")
        self.assertEqual(svg.count("<path"), 1)  # head on, a cube is one square

    def test_the_odometer_lands_on_each_digit(self) -> None:
        svg, _ = P.odometer(0, 50, "6/6", 40, "k", 10, 0.3, 30, "o")
        for values, times in re.findall(r'values="([^"]*)" keyTimes="([^"]*)"', svg):
            ys = [float(v.split()[1]) for v in values.split(";")]
            self.assertAlmostEqual(ys[2] / (-40 * 1.22), 26)  # 20 + 6: two turns, then the 6
            self.assertEqual([float(t) for t in times.split(";")], sorted(float(t) for t in times.split(";")))


class Posters(unittest.TestCase):
    def setUp(self) -> None:
        self.posters, self.readme = g.build(facts())

    def test_every_poster_is_well_formed_in_both_themes(self) -> None:
        for p in self.posters:
            for theme in ("light", "dark"):
                with self.subTest(poster=p.name, theme=theme):
                    ET.fromstring(p.draw(theme))

    def test_the_readme_shows_every_poster_in_both_themes(self) -> None:
        for p in self.posters:
            for theme in ("light", "dark"):
                self.assertIn(f"./art/{theme}/{p.name}.svg", self.readme)

    def test_every_card_is_a_link_to_its_page(self) -> None:
        for href in ("https://humanfia.ai/projects/kda", "https://humanfia.ai/flows/flame-chase", "https://humanfia.ai/news/imo",
                     "https://x", "https://github.com/futrime", "https://github.com/humanfia"):
            self.assertIn(f'<a href="{href}"><picture>', self.readme)

    def test_the_long_sections_fold(self) -> None:
        self.assertEqual(self.readme.count("<details"), 2)
        self.assertEqual(self.readme.count("</details>"), 2)

    def test_sections_without_a_source_are_left_out(self) -> None:
        posters, readme = g.build(g.Facts(g.parse_logo(LOGO)))
        self.assertEqual([p.name for p in posters], ["hero", "outro"])
        self.assertNotIn("<details", readme)
        for p in posters:
            ET.fromstring(p.draw("light"))

    def test_every_animation_has_valid_key_times(self) -> None:
        for p in self.posters:
            svg = p.draw("dark")
            for values, times in re.findall(r'values="([^"]*)" keyTimes="([^"]*)"', svg):
                ts = [float(t) for t in times.split(";")]
                self.assertEqual((ts[0], ts[-1]), (0.0, 1.0), p.name)
                self.assertEqual(ts, sorted(ts), p.name)
                self.assertEqual(len(ts), len(values.split(";")), p.name)

    def test_no_text_under_13px(self) -> None:
        for p in self.posters:
            sizes = [float(s) for s in re.findall(r"font-size:([\d.]+)px", p.draw("light"))]
            self.assertGreaterEqual(min(sizes, default=13), 13, p.name)

    def test_nothing_is_loaded_and_nothing_runs(self) -> None:
        for p in self.posters:
            svg = p.draw("light")
            self.assertNotIn("<script", svg)
            self.assertIsNone(re.search(r'href="(?!#|data:)', svg), p.name)

    def test_no_one_is_marked_out_on_the_wall(self) -> None:
        coins = [p.draw("light") for p in self.posters if p.name.startswith("person-")]
        red = g.THEMES["light"]["red"]
        for svg in coins:
            self.assertNotIn(red, svg.split("</style>", 1)[1])
            self.assertNotIn("saturate", svg)  # faces in their own colours

    def test_the_runtime_marks_the_native_model_call(self) -> None:
        runtime = next(p for p in self.posters if p.name == "runtime").draw("light")
        self.assertIn("litellm · a model call", runtime)
        self.assertRegex(runtime, r'class="red"/><text[^>]*>litellm · a model call')

    def test_the_i_dot_sits_over_the_dotless_i(self) -> None:
        _, (cx, cy, r), _ = g.wordmark(0, 100, 1.0)
        self.assertAlmostEqual(cx, sum(w + 8 for _, w in g._glyphs()[:6]) + g.S / 2)
        self.assertLess(cy + r, 100 - g.XH)


if __name__ == "__main__":
    unittest.main()
