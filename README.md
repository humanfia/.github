# humanfia/.github

Org profile for [github.com/humanfia](https://github.com/humanfia), generated from [humanfia.ai](https://humanfia.ai).

## Background

- `profile/README.md` — the page GitHub shows on the org's overview tab. The banner and the link row sit between
  `<!-- BEGIN gen_portfolio.py -->` and `<!-- END gen_portfolio.py -->` and are rewritten on every run; anything
  outside the markers is kept.
- `profile/humanfia-portfolio-{dark,light}.svg` — a 10 s looping banner (pure SVG + SMIL, no JS, system fonts), one
  per colour scheme; the README picks one with `<picture>` + `prefers-color-scheme`.
- `tools/gen_portfolio.py` — reads the live site and writes all three: the H mark from `/logo.svg` and
  `/logo-dark.svg`, the projects and flows from the nav (and `/flows/`), the tagline from the home page's `<title>`,
  the latest posts from `/news/feed.rss` and `/blog/feed.rss`. A section the site doesn't have yet is left out; if
  the home page or the logo can't be read, it exits non-zero and changes nothing.
- `.github/workflows/profile.yml` — runs the generator daily, on a `humanfia-ai-deployed` `repository_dispatch` sent
  by humanfia.ai's deploy, and by hand; it commits only when the output changed.

## Usage

```bash
python3 tools/gen_portfolio.py                    # both banners and profile/README.md
THEME=dark python3 tools/gen_portfolio.py         # one banner (light|dark), README untouched
SITE=http://localhost:4173 python3 tools/gen_portfolio.py   # against a local preview of the site
python3 -m unittest discover -s tools -p 'test_*.py'
```

The dispatch from humanfia.ai needs a fine-grained token with **Contents: read and write** on `humanfia/.github`,
stored as the `ORG_PROFILE_TOKEN` secret in `humanfia/humanfia.ai`. Without it the daily run still keeps the profile
current, a day late at most.
