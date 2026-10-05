"""Offline tests for gen_portfolio.py: how it reads the site, and the banner it draws.

    python3 -m unittest discover -s tools -p 'test_*.py'
"""

import io
import re
import unittest
import urllib.error
from unittest import mock
from xml.etree import ElementTree as ET

import gen_portfolio as g

NAV = """<nav class="VPNavBarMenu menu"><span>Main Navigation</span>
<div class="VPFlyout VPNavBarMenuGroup"><button type="button" class="button"><span class="text"><span>Projects</span></span></button>
<div class="menu"><div class="VPMenu"><div class="items">
<div class="VPMenuLink"><a class="VPLink link" href="/projects/humanize"><span>Humanize 2: Agent Flow System</span></a></div>
<div class="VPMenuLink"><a class="VPLink link" href="/projects/kda"><span>KDA</span></a></div>
</div></div></div></div>
<div class="VPFlyout VPNavBarMenuGroup"><button type="button" class="button"><span class="text"><span>Flows</span></span></button>
<div class="menu"><div class="VPMenu"><div class="items">
<div class="VPMenuGroup"><p class="title">Every flow</p><div class="VPMenuLink"><a class="VPLink link" href="/flows/"><span>The catalogue</span></a></div></div>
<div class="VPMenuGroup"><p class="title">A relay</p><div class="VPMenuLink"><a class="VPLink link" href="/flows/flame-chase"><span>flame_chase</span></a></div></div>
<div class="VPMenuGroup"><p class="title">Maker and checker</p><div class="VPMenuLink"><a class="VPLink link" href="/flows/rlar"><span>rlar</span></a></div>
<div class="VPMenuLink"><a class="VPLink link" href="/flows/aot"><span>aot</span></a></div></div>
</div></div></div></div>
<a class="VPLink link VPNavBarMenuLink" href="/blog/"><span>Blog</span></a>
<a class="VPLink link VPNavBarMenuLink" href="/about/"><span>About</span></a>
</nav><nav class="VPNavBarMenu"><a class="VPNavBarMenuLink" href="/x/">Second nav, ignored</a></nav>"""

HOME = """<html><head><title>Humanfia — we build the flow around the agents</title></head><body>
<section class="h-hero"><p class="h-kicker">Open-source agent flows</p><h1>We build the flow around the agents.</h1></section>
<section><p class="h-manifesto-text"><span>Models get better. </span><span>The flow is what lasts.</span></p></section>
<div class="h-feature"><h3>A budget it keeps</h3><p>Stop on time.</p></div>
<a class="h-tile"><span class="h-tile-label">IMO 2026</span><span class="h-tile-num">6/6</span></a></body></html>"""

DOCS = """<div class="arch"><div class="stack">
<section class="band"><header><h3>Flows</h3><p>what the work is</p></header><ul class="chips"><li><span>chat</span></li></ul></section>
<p class="down"><span class="arrow"></span> a turn: a prompt, on one conversation, at a model and an effort</p>
<section class="band"><header><h3>Coding agents</h3><p>the model</p></header>
<ul class="chips"><li><span>claude</span></li><li><span>dsh<small>SDK</small></span></li><li><span>litellm<small>a model call</small></span></li></ul></section>
</div></div>"""

FLOW = """<main><h1>rlar</h1><p>Have every round reviewed. More words.</p><table><thead><tr><th>Role</th><th>What it is</th><th>How</th><th>Does</th></tr></thead>
<tbody><tr><td>actor</td><td>agent, required</td><td>-a actor=</td><td>Does the work.</td></tr>
<tr><td>reviewer</td><td>agent, required</td><td>-a reviewer=</td><td>Reads the repository.</td></tr>
<tr><td>budget</td><td>param</td><td>-p</td><td>Stops.</td></tr></tbody></table></main>"""

ABOUT = """<main><p class="lede">We build. These are the people who do it.</p>
<li class="person"><a class="person-face" href="https://github.com/futrime"><img src="https://example.com/a.png"></a>
<p class="person-name">Zijian Zhang <span class="lead">Lead</span></p><p class="person-handle"><a href="https://github.com/futrime">@futrime</a></p></li>
<p>The bet. We think the loop is what lasts — models are rented.</p>
<ul class="principles"><li><b>The builder is not the judge.</b> More.</li></ul>
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
    f.flows = [("Maker and checker", ["rlar", "aot"])]
    f.loop = g.parse_loop("rlar", g.dom(FLOW))
    f.projects = [g.Project("KDA", "Kernel Design Agents", "1.39×", "Past the best human entries")]
    f.posts = [g.Post("NEWS", "Title & <more>", "https://x", 0, "Oct 2, 2026", "Ann")]
    f.people = [g.Person("Zijian Zhang", "futrime")]
    f.principles, f.contact = ["The builder is not the judge."], [("A question", "github.com/humanfia")]
    return f


class Reading(unittest.TestCase):
    def test_nav_groups_and_links_from_the_first_nav_only(self) -> None:
        nav = g.parse_nav(g.dom(NAV))
        self.assertEqual([m.label for m in nav], ["Projects", "Flows", "Blog", "About"])
        self.assertEqual(nav[0].items, [("Humanize 2: Agent Flow System", "/projects/humanize"), ("KDA", "/projects/kda")])
        self.assertEqual([t for t, _ in nav[1].groups], ["Every flow", "A relay", "Maker and checker"])
        self.assertEqual(g.find(nav, "about").href, "/about/")

    def test_flows_skip_the_catalogue_and_run_a_maker_and_checker(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        pages = {"/flows/rlar": FLOW}
        with mock.patch.object(g, "fetch", side_effect=lambda p: pages.get(p, "<main></main>")):
            g.flow_facts(f, g.parse_nav(g.dom(NAV)))
        self.assertEqual(f.flows, [("A relay", ["flame_chase"]), ("Maker and checker", ["rlar", "aot"])])
        self.assertEqual(f.loop, g.Loop("rlar", "Have every round reviewed.",
                                        [("actor", "Does the work."), ("reviewer", "Reads the repository.")]))

    def test_home_and_docs(self) -> None:
        f = facts()
        self.assertEqual((f.kicker, f.headline), ("Open-source agent flows", "We build the flow around the agents."))
        self.assertEqual(f.manifesto, ["Models get better.", "The flow is what lasts."])
        self.assertEqual(f.features, [("A budget it keeps", "Stop on time.")])
        self.assertEqual(f.results, [("IMO 2026", "6/6")])
        self.assertEqual([b.title for b in f.bands], ["Flows", "Coding agents"])
        self.assertEqual(f.bands[0].down, "a turn: a prompt, on one conversation, at a model and an effort")
        self.assertEqual(f.bands[1].chips, [("claude", ""), ("dsh", "SDK"), ("litellm", "a model call")])

    def test_people_principles_contact_and_the_bet(self) -> None:
        f = g.Facts(g.parse_logo(LOGO))
        with mock.patch.object(g, "fetch", return_value=ABOUT), mock.patch.object(g, "avatar", return_value=""):
            g.people_facts(f, [g.Menu("About", "/about/")])
        self.assertEqual([(p.name, p.handle) for p in f.people], [("Zijian Zhang", "futrime")])
        self.assertEqual(f.principles, ["The builder is not the judge."])
        self.assertEqual(f.contact, [("A question", "github.com/humanfia")])
        self.assertEqual(f.bet, "We think the loop is what lasts — models are rented.")

    def test_project_stat_strip_and_lede(self) -> None:
        page = ('<main><p class="lede">Kernel Design Agents. More.</p><div class="stat-strip"><div><b>1.39×</b>'
                "<span>Past the best human entries</span><em>Contest</em></div></div></main>")
        f = g.Facts(g.parse_logo(LOGO))
        with mock.patch.object(g, "fetch", return_value=page):
            g.project_facts(f, g.parse_nav(g.dom(NAV)))
        self.assertEqual(f.projects[1], g.Project("KDA", "Kernel Design Agents", "1.39×", "Past the best human entries"))
        self.assertEqual(f.projects[0].lede, "Kernel Design Agents")

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


class Banner(unittest.TestCase):
    def test_well_formed_in_both_themes_with_every_chapter(self) -> None:
        for theme in ("light", "dark"):
            ET.fromstring(g.banner(theme, facts()))
        self.assertEqual([s.kicker for s in g.scenes(facts())],
                         ["Humanfia", "The thesis", "Humanize, the runtime", "A turn, and what it keeps", "Flows",
                          "A flow, running: rlar", "Projects", "News and blog", "The people", "Find us"])

    def test_chapters_without_a_source_are_dropped_and_the_clock_still_runs_120s(self) -> None:
        bare = g.Facts(g.parse_logo(LOGO))
        self.assertEqual([s.kicker for s in g.scenes(bare)], ["Humanfia", "Find us"])
        svg = g.banner("light", bare)
        ET.fromstring(svg)
        self.assertEqual(set(re.findall(r'dur="([^"]+)"', svg)), {"120s"})

    def test_every_animation_is_on_one_clock_with_valid_key_times(self) -> None:
        svg = g.banner("dark", facts())
        for values, times in re.findall(r'values="([^"]*)" keyTimes="([^"]*)"', svg):
            ts = [float(t) for t in times.split(";")]
            self.assertEqual((ts[0], ts[-1]), (0.0, 1.0))
            self.assertEqual(ts, sorted(ts))
            self.assertEqual(len(ts), len(values.split(";")))

    def test_no_text_under_14px(self) -> None:
        sizes = [float(s) for s in re.findall(r"font-size:([\d.]+)px", g.banner("light", facts()))]
        self.assertGreaterEqual(min(sizes), 14)

    def test_the_runtime_marks_the_native_model_call(self) -> None:
        self.assertIn("litellm: a model call", g.banner("light", facts()))

    def test_the_i_dot_sits_over_the_dotless_i(self) -> None:
        _, (cx, cy, r), _ = g.wordmark(0, 100, 1.0)
        self.assertAlmostEqual(cx, sum(w + 8 for _, w in g._glyphs()[:6]) + g.S / 2)
        self.assertLess(cy + r, 100 - g.XH)


if __name__ == "__main__":
    unittest.main()
