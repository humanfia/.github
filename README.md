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
| [`tools/gen_portfolio.py`](tools/gen_portfolio.py) | Generates the banner, as below. |

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

`profile/humanfia-portfolio-{dark,light}.svg` is a 48 s looping banner (pure SVG + SMIL, no JS),
one per colour scheme; the profile picks one with `<picture>` + `prefers-color-scheme`, so it
follows the viewer's GitHub or system theme.

`tools/gen_portfolio.py` generates it. All 3D (particles, icosahedron, heat-grid, bars, globe) is
projected in Python and baked into keyframes. Edit the numbers or scenes there, then rebuild both
themes (or one, with `THEME=dark|light`):

```bash
python3 tools/gen_portfolio.py
```

The `banner` workflow checks the committed SVGs are what the generator makes.

## License

[Apache-2.0](LICENSE).
