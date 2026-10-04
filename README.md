# humanfia/.github

Org profile for [github.com/humanfia](https://github.com/humanfia).

- `profile/README.md` — the page GitHub shows on the org's overview tab.
- `profile/humanfia-portfolio.svg` — 48 s looping banner (pure SVG + SMIL, no JS, renders inside GitHub's `<img>`).
- `tools/gen_portfolio.py` — generates the banner. All 3D (particles, icosahedron, heat-grid, bars, globe) is projected
  in Python and baked into keyframes. Edit the numbers/scenes there, then:

```bash
python3 tools/gen_portfolio.py
```
