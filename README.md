# humanfia/.github

The organization's own repository: the profile on [github.com/humanfia](https://github.com/humanfia),
and what every humanfia repository inherits rather than copies.

## What is here

| Path | What it is |
| --- | --- |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), [`SUPPORT.md`](SUPPORT.md), [`GOVERNANCE.md`](GOVERNANCE.md) | The default community health files. GitHub shows them for any repository of the organization that has no file of the same name. |
| [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/), [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) | The default issue forms and pull request template, for any repository without an `ISSUE_TEMPLATE` folder or a template of its own. |
| [`.github/workflows/uv-python-ci.yml`](.github/workflows/uv-python-ci.yml) | A reusable workflow: the CI of a Python repository built with uv, as below. |
| [`workflow-templates/`](workflow-templates/) | The starter workflow that calls it, offered under **Actions → New workflow** in every repository of the organization. |
| [`profile/`](profile/) | The page GitHub shows on the organization's overview tab, with its banner. |
| [`tools/gen_portfolio.py`](tools/gen_portfolio.py), [`tools/proun.py`](tools/proun.py) | Generate the profile from humanfia.ai, as below. |

A repository keeps its own copy of a health file only when what it says is particular to that
repository, as [humanize](https://github.com/humanfia/humanize)'s are. A LICENSE, a README, a
CODEOWNERS, a `dependabot.yml` and a `CITATION.cff` are not inherited: each repository has its
own.

## The shared CI

`uv-python-ci.yml` runs `uv lock --check`, `ruff check` and `ruff format --check`, then
`pytest` on Ubuntu and macOS, with every action pinned to a commit. A repository uses it from a
workflow of its own, which says when it runs:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  ci:
    uses: humanfia/.github/.github/workflows/uv-python-ci.yml@d74f9b62af6827996c0d0ad59808bedbb902a945 # main, 2026-10-05
```

The checks then show as `ci / lint`, `ci / test (ubuntu-latest)` and `ci / test (macos-latest)`.

The organization requires every `uses:` to be pinned to a full commit SHA, a shared workflow
included: a tag or `@main` fails the run before any step. So a caller names a commit of this
repository's `main`, and a change here reaches a caller only when that caller moves its SHA to a
newer commit, in a pull request of its own.

## The banner

- `profile/README.md` is the page GitHub shows on the org's overview tab. It holds only the banner, a `<picture>`
  that picks the light or dark SVG with `prefers-color-scheme`, linked to humanfia.ai.
- `profile/humanfia-portfolio-{light,dark}.svg` is a film of about two and a half minutes, in one shot, one per
  colour scheme. It keeps the constructivist look -- paper, ink and one red, hard-edged planes, wedges, discs and
  bars, the logo's one-in-three diagonal, heavy block type, a wordmark built from geometry -- and moves in real 3D:
  the chapters are boards hung along that diagonal in one world, and a camera holds on each, pans across the wide
  ones and pulls back between them, while the red ball rolls along the rail to the next. Its chapters:
  1. the mark: the H extruded into a slab turning over a receding floor, its ball orbiting it
  2. the projects, each a turning solid
  3. the Humanize runtime as a tower a turn falls through, and its features with working diagrams
  4. every flow in the catalogue, its loop acted out
  5. the results, on counters that spin into place
  6. the latest news and blog posts
  7. the people as coins that flip in a wave, and the principles on a turning prism
  8. the address and the contacts, then a pull-back over the whole world

  The geometry is rotated and projected by `tools/proun.py`; the browser only plays it back with SMIL and CSS
  keyframes. There is no JavaScript and no web font, and the avatars are inlined.
- `tools/gen_portfolio.py` reads the live sites and writes both SVGs and the README:
  - from humanfia.ai: the logo; the home page's headline, lead, manifesto, features and result tiles; the Projects
    menu and each project's page; the `/flows/` catalogue; `/news/feed.rss` and `/blog/feed.rss`; and About (and
    Team) for the people, the principles and the contacts
  - from docs.humanfia.ai: the "how it fits together" bands

  A chapter whose source is missing (a 404 or 410, or markup without the parts it needs) is left out. Any other
  failure exits non-zero and changes nothing.
- `.github/workflows/profile.yml` checks every half hour whether humanfia.ai has deployed a commit the profile was
  not built from (`profile/.source-sha`), reading the site's public `deploy` runs with its own token, and runs the
  generator only if so. A run by hand checks the same way unless `force` is set. It runs the generator regardless
  daily and on a `humanfia-ai-deployed` `repository_dispatch`. It commits only when something under `profile/` changed.

### Usage

```bash
python3 tools/gen_portfolio.py                    # both banners
THEME=dark python3 tools/gen_portfolio.py         # one banner (light|dark)
SITE=http://localhost:4173 DOCS=http://localhost:5173/humanize python3 tools/gen_portfolio.py   # local previews
python3 -m unittest discover -s tools -p 'test_*.py'
```

No secret is needed anywhere: the profile catches up with a deploy of humanfia.ai within about 40 minutes (the
half-hourly check, after the ten minutes it gives GitHub Pages to serve the deploy).

The `banner` workflow runs the generator's tests on every change to it.

## License

[Apache-2.0](LICENSE).
