"""A small Proun engine: real 3D for SVGs that GitHub shows through <img>.

An <img> runs no JavaScript, so nothing here is computed in the browser. The geometry is rotated
and projected in Python, frame by frame, and the browser only plays the frames back: SMIL
<animate> for a face's outline and shade, CSS keyframes for a layer's affine matrix. Lissitzky's
Prouns were axonometric, so most of this is too -- parallel projection, hard edges, flat planes
lit from one side.

Coordinates are the screen's: x right, y down, z toward the viewer.
"""

from __future__ import annotations

import math
from typing import Sequence

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]


def n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def rot(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> Mat:
    """Yaw about y, then pitch about x, then roll about z; degrees."""
    a, b, c = (math.radians(v) for v in (yaw, pitch, roll))
    ry = ((math.cos(a), 0, math.sin(a)), (0, 1, 0), (-math.sin(a), 0, math.cos(a)))
    rx = ((1, 0, 0), (0, math.cos(b), -math.sin(b)), (0, math.sin(b), math.cos(b)))
    rz = ((math.cos(c), -math.sin(c), 0), (math.sin(c), math.cos(c), 0), (0, 0, 1))
    return _mm(rz, _mm(rx, ry))


def _mm(p: Sequence[Sequence[float]], q: Sequence[Sequence[float]]) -> Mat:
    return tuple(tuple(sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def apply(m: Mat, v: Vec) -> Vec:
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a: Vec) -> Vec:
    k = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / k, a[1] / k, a[2] / k)


def mix(c0: str, c1: str, t: float) -> str:
    """#rrggbb between c0 (t=0) and c1 (t=1)."""
    t = min(max(t, 0.0), 1.0)
    a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def ease(u: float) -> float:
    return u * u * (3 - 2 * u)


def loop_frames(count: int) -> list[float]:
    """count + 1 phases from 0 to 1 inclusive: the last frame is the first, so the loop has no seam."""
    return [i / count for i in range(count + 1)]


def smil(attr: str, values: Sequence[str], dur: float, discrete: bool = False, begin: float = 0.0) -> str:
    """Evenly spaced values over dur, forever."""
    mode = ' calcMode="discrete"' if discrete else ""
    start = f' begin="{n(begin)}s"' if begin else ""
    return (f'<animate attributeName="{attr}" dur="{n(dur)}s"{start} repeatCount="indefinite"{mode} '
            f'values="{";".join(values)}"/>')


def smil_keys(attr: str, keys: Sequence[tuple[float, str]], dur: float, discrete: bool = False) -> str:
    """(phase 0..1, value) keyframes over dur, forever."""
    keys = sorted(keys)
    if keys[0][0] > 0:
        keys = [(0.0, keys[0][1]), *keys]
    if keys[-1][0] < 1:
        keys = [*keys, (1.0, keys[-1][1])]
    mode = ' calcMode="discrete"' if discrete else ""
    return (f'<animate attributeName="{attr}" dur="{n(dur)}s" repeatCount="indefinite"{mode} '
            f'values="{";".join(v for _, v in keys)}" keyTimes="{";".join(f"{t:.4f}".rstrip("0").rstrip(".") or "0" for t, _ in keys)}"/>')


def smil_move(keys: Sequence[tuple[float, float, float]], dur: float, kind: str = "translate", begin: float = 0.0) -> str:
    """An animateTransform through (phase, a, b) keyframes: translate a b, or scale a b."""
    keys = sorted(keys)
    if keys[0][0] > 0:
        keys = [(0.0, keys[0][1], keys[0][2]), *keys]
    if keys[-1][0] < 1:
        keys = [*keys, (1.0, keys[-1][1], keys[-1][2])]
    start = f' begin="{n(begin)}s"' if begin else ""
    return (f'<animateTransform attributeName="transform" type="{kind}" dur="{n(dur)}s"{start} repeatCount="indefinite" '
            f'values="{";".join(f"{n(a)} {n(b)}" for _, a, b in keys)}" '
            f'keyTimes="{";".join(f"{t:.4f}".rstrip("0").rstrip(".") or "0" for t, _, _ in keys)}"/>')


# ----------------------------------------------------------------------------------------- solids

class Solid:
    """A convex polyhedron: vertices and faces (vertex indices, in either winding)."""

    def __init__(self, verts: list[Vec], faces: list[list[int]]) -> None:
        self.verts = verts
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        cz = sum(v[2] for v in verts) / len(verts)
        self.faces = []
        self.normals = []
        for f in faces:
            a, b, c = (verts[i] for i in f[:3])
            nrm = _unit(_cross(_sub(b, a), _sub(c, a)))
            fc = tuple(sum(verts[i][k] for i in f) / len(f) for k in range(3))
            if _dot(nrm, _sub(fc, (cx, cy, cz))) < 0:  # type: ignore[arg-type]
                nrm = (-nrm[0], -nrm[1], -nrm[2])
            self.faces.append(f)
            self.normals.append(nrm)

    def draw(self, frames: Sequence[Mat], dur: float, at: tuple[float, float], scale: float,
             light: str, dark: str, accent: dict[int, tuple[str, str]] | None = None,
             persp: float = 0.0, stroke: str = "") -> str:
        """Each face as a path whose outline, shade and visibility are played back frame by frame.

        A convex solid needs no sorting: the faces turned toward the viewer never overlap.
        """
        lamp = _unit((-0.55, -0.7, 0.75))
        out = []
        for fi, (face, nrm) in enumerate(zip(self.faces, self.normals)):
            lo, hi = (accent or {}).get(fi, (dark, light))
            ds, fills, shown = [], [], []
            for m in frames:
                pts = [apply(m, self.verts[i]) for i in face]
                pr = []
                for x, y, z in pts:
                    k = persp / (persp - z * scale) if persp else 1.0
                    pr.append((at[0] + x * scale * k, at[1] + y * scale * k))
                ds.append("M" + "L".join(f"{n(x)} {n(y)}" for x, y in pr) + "Z")
                nw = apply(m, nrm)
                fills.append(mix(lo, hi, 0.18 + 0.82 * max(0.0, _dot(nw, lamp))))
                shown.append("1" if nw[2] > 0.02 else "0")
            line = f' stroke="{stroke}" stroke-width="1.5" stroke-linejoin="round"' if stroke else ""
            out.append(f'<path d="{ds[0]}" fill="{fills[0]}"{line}>{smil("d", ds, dur)}{smil("fill", fills, dur)}'
                       f'{smil("opacity", shown, dur, discrete=True) if len(set(shown)) > 1 else ""}</path>'
                       if "1" in shown else "")
        return "".join(out)


def box(w: float, h: float, d: float) -> Solid:
    x, y, z = w / 2, h / 2, d / 2
    v = [(sx * x, sy * y, sz * z) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    return Solid(v, [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])


def prism(sides: int, r: float, h: float, axis: str = "y") -> Solid:
    """A regular prism (a cylinder, with enough sides) standing on its axis."""
    ring = [(r * math.cos(2 * math.pi * i / sides), r * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    def put(a: float, b: float, c: float) -> Vec:
        return {"y": (a, c, b), "x": (c, a, b), "z": (a, b, c)}[axis]  # type: ignore[return-value]
    v = [put(a, b, -h / 2) for a, b in ring] + [put(a, b, h / 2) for a, b in ring]
    faces = [list(range(sides)), list(range(sides, 2 * sides))]
    faces += [[i, (i + 1) % sides, sides + (i + 1) % sides, sides + i] for i in range(sides)]
    return Solid(v, faces)


def pyramid(sides: int, r: float, h: float) -> Solid:
    ring = [(r * math.cos(2 * math.pi * i / sides), h / 3, r * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    v = ring + [(0.0, -2 * h / 3, 0.0)]
    return Solid(v, [list(range(sides))] + [[i, (i + 1) % sides, sides] for i in range(sides)])


def wedge(w: float, h: float, d: float) -> Solid:
    """A triangular prism: the site's one diagonal, made solid."""
    x, y, z = w / 2, h / 2, d / 2
    v = [(-x, y, -z), (x, y, -z), (x, -y, -z), (-x, y, z), (x, y, z), (x, -y, z)]
    return Solid(v, [[0, 1, 2], [3, 5, 4], [0, 3, 4, 1], [1, 4, 5, 2], [0, 2, 5, 3]])


def octahedron(r: float) -> Solid:
    v = [(r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)]
    return Solid(v, [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])


# ---------------------------------------------------------------------------------- extrusions

def extrude(name: str, ref: str, frames: Sequence[Mat], dur: float, at: tuple[float, float], depth: float,
            layers: int, side: tuple[str, str], front_cls: str) -> tuple[str, str]:
    """A flat shape pushed back into a slab: copies stacked along z, deepest first, each copy's
    affine matrix keyframed in CSS. As long as the slab never turns edge-on (R[2][2] > 0) the
    painter's order holds. Returns (css, svg); `ref` is the id of the shape to <use>."""
    css, svg = [], []
    for k in range(layers, -1, -1):
        z = -depth * k / layers
        keys = []
        for i, m in enumerate(frames):
            pct = 100 * i / (len(frames) - 1)
            keys.append(f"{pct:.2f}%{{transform:matrix({n(m[0][0] * 1000 / 1000)},{n(m[1][0])},{n(m[0][1])},{n(m[1][1])},"
                        f"{n(at[0] + z * m[0][2])},{n(at[1] + z * m[1][2])})}}")
        css.append(f"@keyframes {name}{k}{{{''.join(keys)}}}"
                   f".{name}{k}{{animation:{name}{k} {n(dur)}s linear infinite}}")
        if k == 0:
            svg.append(f'<use href="#{ref}" class="{name}{k} {front_cls}"/>')
        else:
            svg.append(f'<use href="#{ref}" class="{name}{k}" fill="{mix(side[0], side[1], k / layers)}"/>')
    return "".join(css), "".join(svg)


def matrix_frames(frames: Sequence[Mat], at: tuple[float, float], name: str, dur: float, z: float = 0.0) -> str:
    """CSS keyframes that put a flat group on the plane z of a rotating frame."""
    keys = []
    for i, m in enumerate(frames):
        pct = 100 * i / (len(frames) - 1)
        keys.append(f"{pct:.2f}%{{transform:matrix({n(m[0][0])},{n(m[1][0])},{n(m[0][1])},{n(m[1][1])},"
                    f"{n(at[0] + z * m[0][2])},{n(at[1] + z * m[1][2])})}}")
    return f"@keyframes {name}{{{''.join(keys)}}}.{name}{{animation:{name} {n(dur)}s linear infinite}}"


# ------------------------------------------------------------------------------------- odometer

def odometer(x: float, base: float, s: str, size: float, cls: str, dur: float, delay: float,
             advance: float, uid: str) -> tuple[str, float]:
    """A number that spins into place like a mechanical counter, holds, and rolls on to zero for the
    next go. Digits are strips of 0-9 behind a window; anything else stands still. Returns the svg
    and its width."""
    out = [f'<clipPath id="{uid}"><rect x="{n(x - 4)}" y="{n(base - size * 0.95)}" width="2000" height="{n(size * 1.22)}"/></clipPath>',
           f'<g clip-path="url(#{uid})">']
    cx, digit = x, 0
    for ch in s:
        w = advance * (0.42 if ch in ".,:" else 1.0)
        if ch.isdigit():
            d = int(ch)
            line = size * 1.22
            strip = "".join(f'<text x="{n(cx + w / 2)}" y="{n(base + line * i)}" class="{cls}" text-anchor="middle">{i % 10}</text>'
                            for i in range(31))
            land = 20 + d
            b = min(0.84, delay / dur + 0.2 + 0.07 * digit)   # landed before the hold at 0.86
            a = min(delay / dur + 0.04 * digit, b - 0.1)
            keys = [(0.0, 0, 0), (a, 0, 0), (b, 0, -line * land), (0.86, 0, -line * land), (0.97, 0, -line * 30), (1.0, 0, -line * 30)]
            out.append(f"<g>{smil_move(keys, dur)}{strip}</g>")
            digit += 1
        else:
            out.append(f'<text x="{n(cx + w / 2)}" y="{n(base)}" class="{cls}" text-anchor="middle">{_esc(ch)}</text>')
        cx += w
    out.append("</g>")
    return "".join(out), cx - x


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
