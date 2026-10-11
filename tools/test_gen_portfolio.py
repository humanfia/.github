"""Offline tests for gen_portfolio.py: how the site is read, the achievements kept, and the film cut.

    python3 -m unittest discover -s tools -p 'test_*.py'
"""

import io
import re
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

import gen_portfolio as g

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
<g transform="translate(2 0) scale(2)"><circle id="dot" cx="25" cy="4" r="3" fill="#76b900"/></g></svg>"""

RSS = ('<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>A</title><link>https://h/news/a</link>'
       "<pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate><dc:creator>Ann, Bo</dc:creator></item></channel></rss>")


def facts() -> g.Facts:
    f = g.Facts(g.parse_logo(LOGO))
    g.home_facts(f, g.dom(HOME))
    g.docs_facts(f, g.dom(DOCS))
    with mock.patch.object(g, "fetch", return_value=FLOWS):
        g.flow_facts(f, g.parse_nav(g.dom(NAV)))
    f.projects = [g.Project("KDA", "https://humanfia.ai/projects/kda", "Kernel Design Agents", "An agent workflow.")]
    f.achievements = [g.Achievement("/news/imo", "6/6", "IMO 2026 & <more>", "2026-07-18"),
                      g.Achievement("/news/lean", "#1", "on Lean-Eval", "2026-10-04")]
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
        self.assertEqual([g.kind_of(fl) for fl in f.flows], ["relay", "lanes"])

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
            posts = g.feed("/news/feed.rss", "NEWS")
            self.assertEqual(g.feed("/blog/feed.rss", "BLOG"), [])
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


class Achievements(unittest.TestCase):
    TODAY = date(2026, 10, 11)

    def test_a_titles_headline_number(self) -> None:
        cases = {
            "78.2% MLE-bench medal rate in 6 hours": ("78.2%", "MLE-bench medal rate in 6 hours"),
            "#1 on Lean-Eval v1 first solves": ("#1", "on Lean-Eval v1 first solves"),
            "30/30 IPhO, 6/6 IOI, 100/100 IBO": ("30/30", "IPhO, 6/6 IOI, 100/100 IBO"),
            "17,520 QCode definitions across 21 lattices": ("17,520", "QCode definitions across 21 lattices"),
            "40+ agent-tuned operators in SGLang": ("40+", "agent-tuned operators in SGLang"),
            "0% + 0.5% → 3.5% on ProgramBench": ("3.5%", "0% + 0.5% → 3.5% on ProgramBench"),
            "Biohub final: #188 of 3,947, top 5%": ("#188", "Biohub final: #188 of 3,947, top 5%"),
            "A 567-file CMake port of gem5": ("", "A 567-file CMake port of gem5"),
        }
        for title, want in cases.items():
            self.assertEqual(g.headline_number(title), want, title)

    def test_what_each_number_is(self) -> None:
        self.assertEqual(g.figure("672/672"), ("frac", (672.0, 672.0)))
        self.assertEqual(g.figure("#1"), ("rank", (1.0,)))
        self.assertEqual(g.figure("+8.7%"), ("lift", (8.7,)))
        self.assertEqual(g.figure("78.2%"), ("pct", (78.2,)))
        self.assertEqual(g.figure("6.5×"), ("times", (6.5,)))
        self.assertEqual(g.figure("17,520"), ("count", (17520.0,)))
        self.assertEqual(g.figure("0.7639"), ("score", (0.7639,)))
        self.assertEqual(g.figure("✓"), ("mark", ()))

    def facts(self) -> g.Facts:
        f = g.Facts(g.parse_logo(LOGO))
        f.news = [g.Post("NEWS", "6/6 at IMO 2026, Lean-checked", "https://humanfia.ai/news/imo", 1784332800, ""),   # Jul 18
                  g.Post("NEWS", "#1 on Lean-Eval", "https://humanfia.ai/news/lean/", 1791072000, "")]            # Oct 4
        f.results = [g.Result("IMO 2026", "6/6", "Every problem.", "https://humanfia.ai/news/imo")]
        return f

    def test_every_post_and_tile_is_added_and_tiles_word_it(self) -> None:
        got = g.achievements(self.facts(), [], self.TODAY, lambda p: True)
        self.assertEqual([(a.href, a.num, a.label, a.date, a.added, a.featured) for a in got],
                         [("/news/lean", "#1", "on Lean-Eval", "2026-10-04", "2026-10-11", -1),
                          ("/news/imo", "6/6", "IMO 2026", "2026-07-18", "2026-10-11", 0)])

    def test_the_ledger_remembers_and_only_forgets_what_is_gone(self) -> None:
        old = [{"href": "/news/imo", "num": "6/6", "label": "x", "date": "2026-07-18", "added": "2026-07-20"},
               {"href": "/news/old", "num": "71", "label": "Kept", "date": "2026-06-22", "added": "2026-06-23"},
               {"href": "/news/pulled", "num": "1", "label": "Gone", "date": "2026-06-01", "added": "2026-06-02"}]
        asked = []
        got = g.achievements(self.facts(), old, self.TODAY, lambda p: asked.append(p) or p != "/news/pulled")
        self.assertEqual([a.href for a in got], ["/news/lean", "/news/imo", "/news/old"])
        self.assertEqual(sorted(asked), ["/news/old", "/news/pulled"])
        self.assertEqual(got[1].added, "2026-07-20")   # first seen then, not now
        self.assertEqual(got[0].added, "2026-10-11")

    def test_the_ledger_round_trips(self) -> None:
        got = g.achievements(self.facts(), [], self.TODAY, lambda p: True)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "achievements.json"
            self.assertEqual(g.load_ledger(path), [])
            g.save_ledger(got, path)
            self.assertEqual(g.load_ledger(path), [a.record() for a in got])

    def test_new_first_then_featured_then_the_rest(self) -> None:
        a = [g.Achievement("/a", "1", "a", "2026-10-05"), g.Achievement("/b", "1", "b", "2026-09-01"),
             g.Achievement("/c", "1", "c", "2026-08-01", featured=0)]
        self.assertEqual([x.href for x in g.lineup(a, self.TODAY)], ["/a", "/c", "/b"])
        self.assertTrue(g.fresh(a[0], self.TODAY))
        self.assertFalse(g.fresh(a[1], self.TODAY))


class Spot(unittest.TestCase):
    TODAY = date(2026, 10, 11)

    def setUp(self) -> None:
        self.f = facts()
        self.films = {theme: g.film(theme, self.f, self.TODAY) for theme in ("light", "dark")}

    def film_of(self, shot: str) -> str:
        """One shot's svg, drawn on a clock of the whole cut."""
        plan = g.storyboard(self.f, self.TODAY)
        F = g.Film("light", self.f, sum(s.seconds for s in plan))
        t = 0.0
        for s in plan:
            if s.name == shot:
                return s.draw(F, t, t + s.seconds)
            t += s.seconds
        raise KeyError(shot)

    def test_well_formed_in_both_themes_with_every_section(self) -> None:
        for svg in self.films.values():
            ET.fromstring(svg)
        names = [s.name for s in g.storyboard(self.f, self.TODAY)]
        self.assertEqual(names[:3], ["open", "mark", "headline"])
        for part in ("wipe-Runtime", "runtime", "flows", "kind-relay", "kind-lanes", "wipe-Projects", "project0",
                     "achievements", "achievement0", "wipe-People", "people"):
            self.assertIn(part, names)
        self.assertEqual(names[-1], "outro")

    def test_about_a_minute_however_much_the_site_says(self) -> None:
        f = self.f
        f.flows = f.flows * 7
        f.projects = [f.projects[0]] * 5
        f.people = f.people * 9
        f.achievements = [g.Achievement(f"/news/{i}", f"{i}/40", f"Result {i}", "2026-01-01") for i in range(30)]
        plan = g.storyboard(f, self.TODAY)
        self.assertLessEqual(sum(s.seconds for s in plan), 75)
        self.assertLessEqual(max(s.seconds for s in plan), 3.5)        # no shot lingers

    def test_every_achievement_is_broadcast_and_every_new_one_alone(self) -> None:
        f = self.f
        f.achievements = ([g.Achievement(f"/news/n{i}", f"{i + 1}/9", f"New {i}", "2026-10-0" + str(i + 1)) for i in range(9)]
                          + [g.Achievement(f"/news/o{i}", f"#{i + 1}", f"Old {i}", "2025-01-01") for i in range(20)])
        plan = g.storyboard(f, self.TODAY)
        solo = [s for s in plan if s.name.startswith("achievement") and s.name != "achievements"]
        walls = [s for s in plan if s.name.startswith("wall")]
        self.assertEqual(len(solo), 9)                                   # more than SOLO: all nine are new
        self.assertEqual(len(walls), 2)                                  # twenty more, on two walls
        svg = g.film("light", f, self.TODAY)
        for a in f.achievements:
            self.assertIn(f">{a.label}<", svg)
        self.assertEqual(svg.count(">NEW<"), 9)

    def test_sections_without_a_source_are_left_out(self) -> None:
        bare = g.Facts(g.parse_logo(LOGO))
        self.assertEqual([s.name for s in g.storyboard(bare, self.TODAY)], ["open", "mark", "outro"])
        ET.fromstring(g.film("dark", bare, self.TODAY))

    def test_one_clock_and_valid_key_times(self) -> None:
        svg = self.films["dark"]
        T = sum(s.seconds for s in g.storyboard(self.f, self.TODAY))
        self.assertEqual({float(d) for d in re.findall(r'dur="([\d.]+)s"', svg)}, {round(T, 2)})
        for values, times in re.findall(r'values="([^"]*)" keyTimes="([^"]*)"', svg):
            ts = [float(t) for t in times.split(";")]
            self.assertEqual((ts[0], ts[-1]), (0.0, 1.0))
            self.assertEqual(ts, sorted(ts))
            self.assertEqual(len(ts), len(values.split(";")))

    def test_flat_and_in_the_sites_colours(self) -> None:
        for theme, svg in self.films.items():
            self.assertNotIn("@keyframes", svg)       # no extruded solids
            self.assertNotIn("Gradient", svg)         # flat colour only
            colours = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", svg)}
            self.assertLessEqual(colours, set(g.THEMES[theme].values()), theme)

    def test_ids_are_unique(self) -> None:
        ids = re.findall(r'\bid="([^"]+)"', self.films["light"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_text_under_13px(self) -> None:
        sizes = [float(s) for s in re.findall(r"font-size:([\d.]+)px", self.films["light"])]
        self.assertGreaterEqual(min(sizes), 13)

    def test_nothing_is_loaded_and_nothing_runs(self) -> None:
        svg = self.films["light"]
        self.assertNotIn("<script", svg)
        self.assertIsNone(re.search(r'href="(?!#|data:)', svg))

    def test_no_one_is_marked_out_among_the_people(self) -> None:
        shot = self.film_of("people")
        self.assertNotIn('class="green"', shot)
        self.assertNotIn("saturate", shot)  # faces in their own colours
        self.assertIn("data:image/png;base64,AAAA", shot)

    def test_the_runtime_is_green_where_humanize_is(self) -> None:
        f = self.f
        f.bands[1].title = "humanize"
        self.assertRegex(self.film_of("runtime"), r'class="green"/><text[^>]*>HUMANIZE<')

    def test_the_readme_is_the_film_linked_to_the_site(self) -> None:
        md = g.readme(self.f)
        self.assertIn('<a href="https://humanfia.ai">', md)
        for theme in ("light", "dark"):
            self.assertIn(f"./humanfia-portfolio-{theme}.svg", md)


class Wordmark(unittest.TestCase):
    def test_the_i_dot_sits_over_the_dotless_i(self) -> None:
        _, (cx, cy, r), _ = g.wordmark(0, 100, 1.0)
        self.assertAlmostEqual(cx, sum(w + 8 for _, w in g._glyphs()[:6]) + g.S / 2)
        self.assertLess(cy + r, 100 - g.XH)


if __name__ == "__main__":
    unittest.main()
