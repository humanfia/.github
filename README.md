# humanfia/.github

Org profile for [github.com/humanfia](https://github.com/humanfia), generated from [humanfia.ai](https://humanfia.ai).

## Background

- `profile/README.md` is the page GitHub shows on the org's overview tab. It holds only the banner, a `<picture>`
  that picks the light or dark SVG with `prefers-color-scheme`, linked to humanfia.ai. It is written by hand and
  does not change.
- `profile/humanfia-portfolio-{light,dark}.svg` is a 120-second explainer in constructivist style, one per colour
  scheme. It uses flat planes, bars, wedges and one red circle, a single 17° diagonal and heavy block type. The
  wordmark is built from geometry. It is pure SVG + SMIL on one clock, with no JavaScript, no web fonts and avatars
  inlined. Its chapters:
  1. the H assembling and the dot hopping to the i
  2. the thesis
  3. the Humanize runtime
  4. a turn and the runtime's features
  5. the flows
  6. one maker-and-checker flow, running
  7. the projects with their headline numbers
  8. the latest news and blog posts
  9. the people
  10. the address
- `tools/gen_portfolio.py` reads the live sites and writes both SVGs:
  - from humanfia.ai: the logo, the home page's headline, manifesto, features and results, the Projects and Flows
    menus and their pages, `/news/feed.rss` and `/blog/feed.rss`, and About (and Team) for the people
  - from docs.humanfia.ai: the "how it fits together" bands

  A chapter whose source is missing (a 404 or 410, or markup without the parts it needs) is dropped, and the others
  share its time. Any other failure exits non-zero and changes nothing.
- `.github/workflows/profile.yml` runs the generator daily, on the `humanfia-ai-deployed` `repository_dispatch`
  that humanfia.ai's deploy sends, and by hand. It commits only when an SVG changed.

## Usage

```bash
python3 tools/gen_portfolio.py                    # both banners
THEME=dark python3 tools/gen_portfolio.py         # one banner (light|dark)
SITE=http://localhost:4173 DOCS=http://localhost:5173/humanize python3 tools/gen_portfolio.py   # local previews
python3 -m unittest discover -s tools -p 'test_*.py'
```

The dispatch from humanfia.ai needs a fine-grained token with **Contents: read and write** on `humanfia/.github`.
Store it as the `ORG_PROFILE_TOKEN` secret in `humanfia/humanfia.ai`. Without it, the daily run still keeps the
profile current, at most a day late.
