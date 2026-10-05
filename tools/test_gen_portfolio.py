"""Offline tests for gen_portfolio.py: the parsers it reads the site with, and the README splice.

    python3 -m unittest discover -s tools -p 'test_*.py'
"""

import unittest
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
<div class="VPMenuLink"><a class="VPLink link" href="/flows/"><span>All flows</span></a></div>
<div class="VPMenuLink"><a class="VPLink link" href="/flows/aot"><span>AoT</span></a></div>
</div></div></div></div>
<a class="VPLink link VPNavBarMenuLink" href="/blog/"><span>Blog</span></a>
<a class="VPLink link VPNavBarMenuLink" href="/news/"><span>News</span></a>
<a class="VPLink link VPNavBarMenuLink" href="/about/"><span>About</span></a>
</nav><nav class="VPNavBarMenu"><a class="VPNavBarMenuLink" href="/x/">Second nav, ignored</a></nav>"""

LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><title id="t">H</title>
<rect x="6" y="4" width="13" height="56"/>
<g transform="translate(2 0) scale(2)"><circle id="dot" cx="25" cy="4" r="3" fill="#d6331f"/></g></svg>"""


class Nav(unittest.TestCase):
    def test_reads_groups_and_links_in_order_from_the_first_nav_only(self) -> None:
        nav = g.parse_nav(NAV)
        self.assertEqual([e.label for e in nav], ["Projects", "Flows", "Blog", "News", "About"])
        self.assertEqual(nav[0].items, [("Humanize 2: Agent Flow System", "/projects/humanize"), ("KDA", "/projects/kda")])
        self.assertEqual(g.find(nav, "news").href, "/news/")
        self.assertEqual(g.find(nav, "AoT").href, "/flows/aot")
        self.assertIsNone(g.find(nav, "Team"))

    def test_flows_skip_the_index_entry(self) -> None:
        with mock.patch.object(g, "fetch", return_value="<html></html>"):
            items, url = g.flows(g.parse_nav(NAV))
        self.assertEqual([i.title for i in items], ["AoT"])
        self.assertEqual(url, g.SITE + "/flows/")

    def test_flows_absent_until_the_site_has_them(self) -> None:
        with mock.patch.object(g, "fetch", return_value=None):
            self.assertEqual(g.flows([g.Entry("Blog", "/blog/")]), ([], None))

    def test_links_follow_the_nav_and_drop_what_is_missing(self) -> None:
        full = [t for t, _ in g.links(g.parse_nav(NAV), g.SITE + "/flows/")]
        self.assertEqual(full, ["humanfia.ai", "Docs", "Humanize", "Flows", "Flowverse", "KDA", "Blog", "News", "About"])
        today = [t for t, _ in g.links([g.Entry("Blog", "/blog/"), g.Entry("Team", "/team/")], None)]
        self.assertEqual(today, ["humanfia.ai", "Docs", "Humanize", "Flowverse", "KDA", "Blog"])


class Text(unittest.TestCase):
    def test_blurb_takes_the_first_clause_without_the_name(self) -> None:
        self.assertEqual(g.blurb("HOA", "HOA — Humanize Olympic Agents. Competition maths."), "Humanize Olympic Agents")
        self.assertEqual(g.blurb("FlowBench", "FlowBench is our benchmark for long-horizon agent work — a way."),
                         "Our benchmark for long-horizon agent work")

    def test_fit_and_wrap_stay_inside_the_room(self) -> None:
        s = "A very long title that will certainly not fit in the room it is given here"
        self.assertTrue(g.fit(s, 17, 200, True).endswith("…"))
        lines = g.wrap(s, 17, 200, 2, True)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(g.width(x, 17, True) <= 200 for x in lines))


class Logo(unittest.TestCase):
    def test_finds_the_dot_through_transforms_and_removes_it(self) -> None:
        logo = g.parse_logo(LOGO)
        self.assertEqual(logo.viewbox, (0, 0, 64, 64))
        self.assertEqual(logo.dot, (52, 8, 6))
        self.assertEqual(logo.dot_fill, "#d6331f")
        self.assertNotIn("circle", logo.body)
        self.assertNotIn("<title", logo.body)

    def test_a_mark_without_a_dot_is_kept_whole(self) -> None:
        logo = g.parse_logo('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 51 57"><path id="p" d="M0 0h1z"/></svg>')
        self.assertIsNone(logo.dot)
        self.assertIn('id="logo-p"', logo.body)

    def test_banner_is_well_formed_svg(self) -> None:
        posts = [g.Post("NEWS", "Title & <more>", "https://x", 0, "Oct 2, 2026")]
        svg = g.banner("dark", g.parse_logo(LOGO), "we build", [g.Item("KDA", "Kernels", "")],
                       [g.Item("AoT", "", "")], posts)
        ET.fromstring(svg)


class Feed(unittest.TestCase):
    def test_reads_items_and_survives_a_missing_feed(self) -> None:
        rss = ("<rss><channel><item><title>A</title><link>https://h/news/a</link>"
               "<pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>")
        with mock.patch.object(g, "fetch", side_effect=lambda p: rss if "news" in p else None):
            posts = g.latest()
        self.assertEqual([(p.kind, p.title, p.date) for p in posts], [("NEWS", "A", "Oct 2, 2026")])


class Readme(unittest.TestCase):
    def test_only_the_marked_block_is_replaced(self) -> None:
        old = f"intro\n{g.BEGIN}\nstale\n{g.END}\noutro\n"
        new = g.readme(old, "alt", [("humanfia.ai", g.SITE), ("Blog", g.SITE + "/blog/")])
        self.assertTrue(new.startswith("intro\n") and new.endswith("\noutro\n"))
        self.assertNotIn("stale", new)
        self.assertIn('<a href="https://humanfia.ai/blog/">Blog</a>', new)


if __name__ == "__main__":
    unittest.main()
