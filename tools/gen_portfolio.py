#!/usr/bin/env python3
"""Generate the animated Humanfia org-profile banner (profile/humanfia-portfolio.svg).

GitHub renders README images through <img>, so no JavaScript and no external fonts. Every
3D effect here is computed in Python: particles, wireframes and extruded blocks are projected
through a perspective camera frame by frame, and the result is written out as SMIL keyframes on
one shared 48 s clock. Keyframes are thinned with Douglas-Peucker so the file stays small.

    python3 tools/gen_portfolio.py            # writes profile/humanfia-portfolio.svg
"""
import math
import os
import random
import re

W, H = 1200, 600
T = 48.0                    # loop length, seconds
FPS = 12                    # particle sampling rate before thinning
N = 400                     # particle count
rng = random.Random(20260720)

INK = "#0f172a"
BLUE = "#2e599e"
BLUE_MID = "#6e93cf"
BLUE_LIGHT = "#8daee2"
BLUE_PALE = "#b6cbec"
SLATE_PALE = "#e2e8f0"
AMBER = "#efb358"
AMBER_DARK = "#b45309"
WHITE = "#ffffff"         # hottest point of glows and highlight gradients
AMBER_HI = "#fff7e6"
TXT_STRONG, TXT_SUB, TXT_OK = "#f8fafc", "#94a3b8", "#86efac"
NEB = (BLUE, 0.35, "#24467c", 0.45, AMBER_DARK, 0.12)
GLASS = ("#ffffff", 0.07, 0.015)
VIGN = ("#000000", 0.55)
BG_STOPS = ("#070d1c", INK, "#0a1226")

THEME = os.environ.get("THEME", "dark")
if THEME == "light":
    BLUE_LIGHT, BLUE_PALE, SLATE_PALE = "#3b6ab5", "#24467c", "#1e293b"
    AMBER, AMBER_HI, WHITE = "#d97706", "#7c2d12", "#0f172a"
    TXT_STRONG, TXT_SUB, TXT_OK = "#0f172a", "#475569", "#15803d"
    NEB = ("#b6cbec", 0.5, "#dbe6f7", 0.7, "#fcd9a8", 0.35)
    GLASS = ("#ffffff", 0.85, 0.55)
    VIGN = ("#1e293b", 0.08)
    BG_STOPS = ("#f8fafc", "#f1f5fb", "#e8eef8")

SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# ----------------------------------------------------------------------------------- helpers

def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease(x):
    x = clamp(x)
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def lerp(a, b, u):
    return a + (b - a) * u


def f(v, nd=1):
    s = f"{v:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def kt(t):
    if t <= 0:
        return "0"
    if t >= T:
        return "1"
    return f"{t / T:.4f}".rstrip("0")[1:]


def anim(attr, pairs, calc="linear", extra=""):
    """<animate> on the global clock. pairs = [(time, value), ...]; times are clamped, padded."""
    pairs = sorted(pairs, key=lambda p: p[0])
    if pairs[0][0] > 0:
        pairs.insert(0, (0, pairs[0][1]))
    if pairs[-1][0] < T:
        pairs.append((T, pairs[-1][1]))
    keys = ";".join(kt(t) for t, _ in pairs)
    vals = ";".join(str(v) for _, v in pairs)
    return (f'<animate attributeName="{attr}" dur="{f(T)}s" repeatCount="indefinite" '
            f'calcMode="{calc}" keyTimes="{keys}" values="{vals}"{extra}/>')


def anim_tf(kind, pairs, additive=False):
    pairs = sorted(pairs, key=lambda p: p[0])
    if pairs[0][0] > 0:
        pairs.insert(0, (0, pairs[0][1]))
    if pairs[-1][0] < T:
        pairs.append((T, pairs[-1][1]))
    keys = ";".join(kt(t) for t, _ in pairs)
    vals = ";".join(str(v) for _, v in pairs)
    add = ' additive="sum"' if additive else ""
    return (f'<animateTransform attributeName="transform" type="{kind}" dur="{f(T)}s" '
            f'repeatCount="indefinite" keyTimes="{keys}" values="{vals}"{add}/>')


def window(t_in, t_out, fade=0.6, peak=1.0):
    return [(0, 0), (t_in, 0), (t_in + fade, peak), (t_out - fade, peak), (t_out, 0)]


def reveal(body, t_in, t_out, dy=14, fade=0.6, dx=0):
    """Fade + slide a block in at t_in and out at t_out."""
    op = anim("opacity", window(t_in, t_out, fade))
    mv = anim_tf("translate", [(0, f"{dx} {dy}"), (t_in, f"{dx} {dy}"), (t_in + fade * 1.4, "0 0"),
                               (t_out - fade, "0 0"), (t_out, f"{-dx} {-dy * 0.6:.0f}")])
    return f'<g opacity="0">{op}{mv}{body}</g>'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, cls, anchor="start", extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{f(x)}" y="{f(y)}" class="{cls}"{a}{extra}>{esc(s)}</text>'


# ------------------------------------------------------------------------------------ camera

def cam(p, yaw, pitch, cx, cy, dist=1000.0, focal=1000.0):
    x, y, z = p
    cyw, syw = math.cos(yaw), math.sin(yaw)
    x1 = x * cyw + z * syw
    z1 = -x * syw + z * cyw
    cp, sp = math.cos(pitch), math.sin(pitch)
    y2 = y * cp - z1 * sp
    z2 = y * sp + z1 * cp
    s = focal / (dist + z2)
    return cx + x1 * s, cy + y2 * s, s, z2


def rot_y(p, a):
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return (x * c + z * s, y, -x * s + z * c)


def rot_x(p, a):
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return (x, y * c - z * s, y * s + z * c)


def rot_z(p, a):
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c, z)


# ----------------------------------------------------------------------------- the H logo

LOGO_PATHS = [
    ("M0 0 C2.7 2.5 4.9 5 7 8 C7.5 8.7 8.1 9.4 8.6 10.1 C16.1 20.4 16.4 31 16.4 43.3 C16.4 45 16.4 46.6 16.4 48.2 C16.4 51.7 16.4 55.2 16.4 58.7 C16.4 64.2 16.4 69.8 16.4 75.3 C16.5 88 16.5 100.7 16.5 113.4 C16.5 125.1 16.5 136.8 16.6 148.5 C16.6 154 16.6 159.5 16.6 165 C16.6 168.4 16.6 171.8 16.6 175.2 C16.6 176.8 16.6 178.3 16.6 179.9 C16.6 182.1 16.6 184.2 16.6 186.4 C16.6 187.6 16.6 188.8 16.6 190.1 C17 193 17 193 18.5 194.9 C21 196.7 23 196.2 26 196 C28.2 195.1 30.3 194.1 32.4 193.1 C35.3 191.9 38 191.2 40.9 190.6 C45.9 189.4 49.8 187.7 54.3 185.3 C58.6 183.2 63.2 182.2 67.8 181 C70.4 180.2 72.5 179.3 74.9 178 C79.8 175.3 85.2 174.3 90.5 173 C94 172 94 172 96.4 170.5 C99.8 168.5 103.3 167.9 107.1 167.1 C112.3 166 116.9 164.8 121.6 162.4 C127 159.7 132.4 158.8 138.3 157.9 C141.3 157.2 143.2 156.5 145.8 155.1 C150.5 152.6 155.3 151.6 160.4 150.5 C166.7 149.2 172.2 147.6 177.9 144.9 C180.8 143.6 183.7 143.1 186.8 142.6 C192.6 141.4 197.5 139.6 202.9 137.3 C207.6 135.4 212.5 134.2 217.4 133 C220.5 132.1 223.4 131.1 226.3 129.9 C231.9 127.8 237.5 127 243.3 126.1 C247.6 125.5 251.5 124.6 255.6 123.1 C262.5 120.6 269.7 119.4 276.9 117.9 C284.4 116.4 291.5 114.4 298.8 111.9 C302 111 304.6 110.8 308 111 C311.3 113.7 312.9 115.3 313.7 119.5 C313.8 120.9 313.8 122.3 313.8 123.8 C313.8 124.5 313.9 125.3 313.9 126.1 C313.9 128.7 314 131.4 314 134 C314 134.5 314 134.5 314 136.8 C314.1 144.2 314.2 151.6 314.2 159 C314.2 161.5 314.2 163.9 314.2 166.4 C314.2 173.1 314.2 179.7 314.2 186.4 C314.2 190.5 314.2 194.7 314.2 198.8 C314.2 210.4 314.2 222 314.2 233.6 C314.2 234.3 314.2 235 314.2 235.8 C314.2 236.5 314.2 237.3 314.2 238 C314.2 239.5 314.2 241 314.2 242.5 C314.2 243.3 314.2 244 314.2 244.8 C314.2 256.8 314.3 268.8 314.3 280.9 C314.3 293.3 314.3 305.7 314.3 318.1 C314.3 325 314.3 332 314.3 338.9 C314.4 345.4 314.4 352 314.4 358.5 C314.4 360.9 314.4 363.3 314.4 365.6 C314.5 400.6 314.5 400.6 308.1 408.1 C307.6 408.5 307.1 409 306.5 409.5 C304.8 411.2 303.8 412.9 302.6 415 C295.9 425.8 282.1 432.8 270 436 C267.2 436.2 264.5 436.3 261.8 436.2 C261 436.2 260.2 436.2 259.5 436.2 C246 435.9 233.8 431.8 224 422 C222.6 420 221.3 418 220 416 C219.2 415.1 218.4 414.2 217.6 413.2 C208.1 401.9 209.3 385 209.3 371.2 C209.3 369 209.3 366.8 209.2 364.5 C209.2 358.7 209.2 352.9 209.2 347.1 C209.2 341.3 209.1 335.6 209.1 329.8 C209 316.2 209 302.6 209 289 C209 288.4 209 288.4 209 285.4 C209 270.3 209 255.1 209 240 C207.4 239 205.7 238 204 237 C197.4 239 190.7 241.1 184.1 243.1 C180.8 244.2 177.5 245.2 174.1 246.2 C172.4 246.7 170.7 247.3 169 247.8 C139.6 256.9 139.6 256.9 131 258.4 C129 259 129 259 126.9 260.4 C122.8 262.7 118.4 263.7 113.9 264.9 C107.3 266.7 100.9 268.7 94.5 271.1 C91.5 272.2 88.5 272.8 85.4 273.4 C80.3 274.6 76.2 276.3 71.6 278.8 C68.7 280.1 66 281 62.9 281.9 C45.7 287 30.3 293.7 20.7 309.7 C18.5 313.9 17.9 317.3 17.7 322 C17.7 323 17.6 324 17.6 325.1 C17.5 326.2 17.5 327.2 17.5 328.4 C17.4 329.5 17.4 330.7 17.3 331.8 C17 340.5 16.9 349.2 16.8 357.9 C16.8 359.2 16.8 360.4 16.7 361.7 C16.7 366.8 16.6 371.9 16.6 377 C16.6 380.8 16.5 384.6 16.5 388.3 C16.5 389.5 16.5 390.6 16.5 391.8 C16.3 405.8 11.4 413.2 1.9 423.3 C-9.4 434.2 -22 436.5 -37 436.3 C-43 436.1 -47.7 434.7 -53 432 C-53.9 431.6 -54.8 431.2 -55.8 430.8 C-69.2 424.2 -79.1 412.1 -84.1 398.2 C-85.6 392.7 -85.6 387.2 -85.6 381.5 C-85.6 380.2 -85.6 378.9 -85.7 377.6 C-85.7 374.1 -85.7 370.5 -85.7 367 C-85.7 363.2 -85.8 359.4 -85.8 355.6 C-85.9 346.8 -86 338.1 -86 329.3 C-86 326.3 -86 323.3 -86 320.3 C-86.1 300.5 -86.2 280.7 -86.2 260.8 C-86.2 256.1 -86.2 251.3 -86.2 246.5 C-86.2 230.6 -86.2 214.8 -86.2 198.9 C-86.2 198 -86.2 197.2 -86.2 196.3 C-86.2 195.5 -86.2 194.6 -86.2 193.8 C-86.2 180 -86.2 166.2 -86.2 152.4 C-86.2 138.1 -86.2 123.8 -86.2 109.4 C-86.2 101.5 -86.2 93.5 -86.2 85.5 C-86.3 78.8 -86.3 72 -86.2 65.3 C-86.2 61.8 -86.2 58.4 -86.3 55 C-86.3 51.3 -86.3 47.5 -86.2 43.8 C-86.3 42.7 -86.3 41.7 -86.3 40.6 C-86.2 29.4 -83.9 21.5 -78 12 C-77.5 11.2 -77 10.5 -76.5 9.7 C-69.6 -0.3 -57.4 -8.7 -45.4 -11.2 C-28.1 -14.3 -13.7 -10.6 0 0 Z", 225, 105),
    ("M0 0 C0.7 0.2 1.3 0.3 2 0.5 C6.6 1.7 9.9 3.5 13.7 6.2 C14.5 6.8 15.3 7.3 16.1 7.9 C21.1 11.7 25.5 15.9 29.6 20.8 C30 21.3 30.5 21.8 30.9 22.3 C41.2 35.1 39.2 54.3 39.1 69.6 C39.1 73.5 39.1 77.5 39.1 81.4 C39 83.9 39 86.4 39 89 C39 90.1 39 91.3 39 92.5 C39 93.6 39 94.7 39 95.8 C39 96.3 39 96.3 39 98.7 C38.7 101.4 38.2 103 36.7 105.2 C29.4 108.7 21.3 110.3 13.6 112.2 C12.9 112.4 12.1 112.5 11.4 112.7 C-2.6 116.2 -16.6 119 -30.8 121 C-31.3 121.1 -31.3 121.1 -33.6 121.4 C-35.2 121.7 -36.9 121.9 -38.6 122.1 C-42.5 122.7 -46 123.4 -49.6 124.8 C-53.7 126.4 -56.1 126.5 -60.3 126.2 C-63.5 123.5 -63.9 121.1 -64.2 116.9 C-64.4 111.9 -64.4 106.9 -64.3 101.9 C-64.2 92.7 -64.3 83.5 -64.7 74.3 C-64.7 72.4 -64.8 70.5 -64.9 68.6 C-65 65.8 -65.1 63 -65.2 60.2 C-65.8 46 -66 32.2 -57.3 20.2 C-57 19.9 -57 19.9 -55.7 17.9 C-52.1 13 -48.6 9.7 -43.4 6.5 C-41.3 5.2 -41.3 5.2 -39.6 3.7 C-36.2 1.5 -32.7 0.9 -28.8 0.1 C-27.9 -0.1 -27.1 -0.3 -26.3 -0.5 C-17 -2.3 -9.2 -2.2 0 0 Z", 500.3125, 93.75),
]
LOGO_MATRIX = "matrix(0.125 0 0 0.124888641 -16.95 -10.939755011)"  # maps into viewBox 0 0 51 57


def logo_polys():
    polys = []
    for d, tx, ty in LOGO_PATHS:
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
        x0, y0 = nums[0], nums[1]
        pts = [(x0, y0)]
        k = 2
        while k + 5 < len(nums):
            c1x, c1y, c2x, c2y, ex, ey = nums[k:k + 6]
            for s in range(1, 7):
                u = s / 6
                a, b, c, e = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
                pts.append((a * x0 + b * c1x + c * c2x + e * ex, a * y0 + b * c1y + c * c2y + e * ey))
            x0, y0 = ex, ey
            k += 6
        polys.append([((x + tx) * 0.125 - 16.95, (y + ty) * 0.124888641 - 10.939755011) for x, y in pts])
    return polys


def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def logo_points(n, height):
    """Blue-noise sample n points inside the H, scaled to `height` px, centred on (0, 0)."""
    polys = logo_polys()
    sc = height / 57.0
    cand = []
    while len(cand) < n * 14:
        x, y = rng.uniform(0, 51), rng.uniform(0, 57)
        if any(inside(p, x, y) for p in polys):
            cand.append(((x - 25.5) * sc, (y - 28.5) * sc))
    pts = [cand.pop()]
    # Mitchell's best-candidate, using a coarse spatial hash for speed
    pool = cand
    while len(pts) < n:
        best, bd = None, -1
        for _ in range(12):
            c = pool[rng.randrange(len(pool))]
            d = min((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 for p in pts)
            if d > bd:
                best, bd = c, d
        pts.append(best)
    return pts


# ------------------------------------------------------------------------------- particles

class P:
    pass


parts = []
for i in range(N):
    p = P()
    p.i = i
    p.amber = rng.random() < 0.12
    p.grad = "gA" if p.amber else rng.choice(["gB", "gB", "gP", "gW", "gB"])
    p.base = rng.uniform(0.75, 1.5) * (1.15 if p.amber else 1.0)
    p.ph = rng.random()
    p.ph2 = rng.random()
    p.th = rng.uniform(0, 2 * math.pi)
    p.jit = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
    parts.append(p)

LOGO_C = (600, 228)
LOGO_H = 236
LOGO_PTS = logo_points(N, LOGO_H)
rng.shuffle(LOGO_PTS)
for p, q in zip(parts, LOGO_PTS):
    p.logo = q

# tunnel star field ------------------------------------------------------------------------
for p in parts:
    p.R = rng.uniform(70, 760)
    p.z0 = rng.uniform(0, 2400)


def F_tunnel(p, t):
    z = 50 + ((p.z0 - 950 * t) % 2400)
    s = 520 / z
    x = 600 + p.R * math.cos(p.th) * s
    y = 300 + p.R * math.sin(p.th) * s * 0.86
    a = smooth((2450 - z) / 500) * smooth((z - 55) / 140)
    return x, y, p.base * clamp(s * 2.6, 0.5, 6), a


def F_logo(p, t):
    lx, ly = p.logo
    lz = p.jit[2] * 14
    yaw = -0.9 * (1 - ease((t - 2.4) / 2.6)) + 0.16 * math.sin((t - 3.6) * 0.8) * smooth((t - 4.4) / 1.5)
    pitch = 0.10 * math.sin((t - 3.0) * 0.6)
    x, y, s, z = cam((lx, ly, lz), yaw, pitch, *LOGO_C, dist=900, focal=900)
    shimmer = 0.78 + 0.22 * math.sin(2 * math.pi * (p.ph + t * 0.45))
    return x, y, p.base * 1.9 * s, shimmer


# Humanize 2 stack ---------------------------------------------------------------------------
FLOW_C = (330, 330)
PLANE_Y = [-120, -40, 40, 120]
PLANE_HALF = 122
FLOW_PITCH = 0.52


def flow_yaw(t):
    return 0.42 + 0.075 * (t - 7.0)


COLS = [(x, z) for x in (-72, 0, 72) for z in (-72, 0, 72)]
for p in parts:
    r = rng.random()
    p.role = "back" if p.amber else ("ring" if r < 0.24 else "stream")
    cx_, cz_ = COLS[rng.randrange(9)]
    p.col = (cx_ + rng.gauss(0, 12), cz_ + rng.gauss(0, 12))
    p.spd = rng.uniform(0.16, 0.26)


def F_flow(p, t):
    yaw = flow_yaw(t)
    if p.role == "stream":
        u = (p.ph + p.spd * t) % 1.0
        y = -160 + 320 * u
        w = (p.col[0], y, p.col[1])
        a = smooth(u / 0.08) * smooth((1 - u) / 0.08) * 0.95
    elif p.role == "ring":
        ang = p.th + 0.55 * t
        rad = 192 + p.jit[0] * 12
        w = (rad * math.cos(ang), 40 + p.jit[1] * 6 + 5 * math.sin(3 * ang), rad * math.sin(ang))
        a = 0.85
    else:  # FlowBench: the one arrow that runs the other way
        u = (p.ph + 0.22 * t) % 1.0
        ang = math.pi * u
        w = (-175 - 70 * math.sin(ang) + p.jit[0] * 8, 135 - 270 * u, 30 + p.jit[1] * 10)
        a = smooth(u / 0.1) * smooth((1 - u) / 0.1)
    x, y, s, z = cam(w, yaw, FLOW_PITCH, *FLOW_C)
    depth = clamp(0.55 + 0.45 * (-z / 260))
    return x, y, p.base * 2.1 * s, a * (0.5 + 0.5 * depth)


# HOA icosahedron ------------------------------------------------------------------------------
ICO_C = (330, 300)
ICO_R = 165
_g = (1 + 5 ** 0.5) / 2
_iv = [(-1, _g, 0), (1, _g, 0), (-1, -_g, 0), (1, -_g, 0), (0, -1, _g), (0, 1, _g), (0, -1, -_g),
       (0, 1, -_g), (_g, 0, -1), (_g, 0, 1), (-_g, 0, -1), (-_g, 0, 1)]
_n = math.sqrt(1 + _g * _g)
ICO_V = [(x / _n * ICO_R, y / _n * ICO_R, z / _n * ICO_R) for x, y, z in _iv]
ICO_E = sorted({tuple(sorted((a, b))) for a in range(12) for b in range(12)
                if a < b and abs(math.dist(ICO_V[a], ICO_V[b]) - ICO_R * 2 / _n * 1.0) < 1e-6 * ICO_R + 1})
ICO_E = [e for e in ICO_E if abs(math.dist(ICO_V[e[0]], ICO_V[e[1]]) - min(
    math.dist(ICO_V[0], ICO_V[k]) for k in range(1, 12))) < 1]
assert len(ICO_E) == 30, len(ICO_E)


def ico_world(v, t):
    v = rot_y(v, 0.42 * t)
    v = rot_x(v, 0.38)
    return rot_z(v, 0.18)


def F_ico(p, t):
    if p.amber:  # amber: electrons on a tilted orbit
        ang = p.th + 1.1 * t
        rad = 235 + p.jit[0] * 10
        w = rot_x((rad * math.cos(ang), 0, rad * math.sin(ang)), 1.15 + p.jit[1] * 0.25)
        w = rot_z(w, -0.35)
        x, y, s, z = cam(w, 0, 0, *ICO_C)
        return x, y, p.base * 2.0 * s, 0.6 + 0.4 * clamp(-z / 200 + 0.5)
    e = ICO_E[p.i % 30]
    k = p.i // 30
    u = ((k + 0.5) / 13.4 + 0.07 * t * (1 if p.i % 2 else -1)) % 1.0
    a0, b0 = ico_world(ICO_V[e[0]], t), ico_world(ICO_V[e[1]], t)
    w = tuple(lerp(a0[j], b0[j], u) + p.jit[j] * 3 for j in range(3))
    x, y, s, z = cam(w, 0, 0, *ICO_C)
    a = (0.3 + 0.7 * clamp(0.5 - z / (2 * ICO_R))) * smooth(u / 0.07) * smooth((1 - u) / 0.07)
    return x, y, p.base * 1.9 * s, a


# KDA heat grid ---------------------------------------------------------------------------------
KDA_C = (345, 360)
KDA_PITCH = 0.56
GRID = 6
CELL = 50
CUBE = 42


def kda_yaw(t):
    return 0.55 + 0.05 * (t - 23.0)


def kda_height(i, j, t):
    cx, cz = i - 2.5, j - 2.5
    d = math.hypot(cx, cz)
    hot = math.exp(-((cx - 0.8) ** 2 + (cz + 0.6) ** 2) / 3.0)
    wave = 0.5 + 0.5 * math.sin(1.25 * d - 2.4 * t)
    return 12 + 125 * (0.25 * wave + 0.75 * hot * (0.65 + 0.35 * wave))


def F_kda(p, t):
    yaw = kda_yaw(t)
    if p.amber:  # sparks off the hottest tiles
        u = (p.ph + 0.45 * t) % 1.0
        x0 = (0.8 + p.jit[0] * 1.6) * CELL
        z0 = (-0.6 + p.jit[1] * 1.6) * CELL
        w = (x0 + p.jit[2] * 30 * u, -110 - 230 * u, z0)
        x, y, s, z = cam(w, yaw, KDA_PITCH, *KDA_C)
        return x, y, p.base * 2.2 * s, smooth(u / 0.1) * (1 - u)
    ring = p.i % 3
    rad = (205, 238, 270)[ring] + p.jit[0] * 7
    hgt = (-55, -130, -205)[ring] + p.jit[1] * 6
    spd = (0.75, -0.55, 0.4)[ring]
    ang = p.th + spd * t
    w = (rad * math.cos(ang), hgt + 10 * math.sin(2 * ang + ring), rad * math.sin(ang))
    x, y, s, z = cam(w, yaw, KDA_PITCH, *KDA_C)
    return x, y, p.base * 2.0 * s, 0.35 + 0.6 * clamp(0.5 - z / 500)


# ProgramBench bars -------------------------------------------------------------------------------
BAR_C = (330, 430)
BAR_YAW, BAR_PITCH = 0.62, 0.36
BARS = [(-150, 0.5), (0, 0.0), (150, 3.5)]   # x, percent
BAR_SCALE = 62


def bar_grow(t):
    return ease((t - 31.6) / 2.0)


def F_bars(p, t):
    top_y = -3.5 * BAR_SCALE * bar_grow(t) - 4
    if p.role != "ring":   # fountain from the 3.5% bar
        period = 1.7
        u = ((p.ph + t / period) % 1.0)
        tt = u * period
        ang = p.th
        sp = 55 + 50 * p.ph2
        v0 = 200 + 70 * p.jit[0]
        w = (150 + math.cos(ang) * sp * tt, top_y - v0 * tt + 0.5 * 240 * tt * tt, math.sin(ang) * sp * tt)
        x, y, s, z = cam(w, BAR_YAW, BAR_PITCH, *BAR_C)
        a = smooth(u / 0.06) * (1 - u) ** 0.7
        return x, y, p.base * 2.0 * s, a
    ang = p.th + 0.35 * t
    rad = 270 + p.jit[0] * 26
    w = (rad * math.cos(ang), 2, rad * math.sin(ang) * 0.85)
    x, y, s, z = cam(w, BAR_YAW, BAR_PITCH, *BAR_C)
    return x, y, p.base * 1.8 * s, 0.25 + 0.5 * clamp(0.5 - z / 500)


# Finale globe ----------------------------------------------------------------------------------
GLOBE_C = (600, 250)
GLOBE_R = 150
for k, p in enumerate(parts):
    yy = 1 - 2 * (k + 0.5) / N
    rr = math.sqrt(1 - yy * yy)
    th = math.pi * (3 - 5 ** 0.5) * k
    p.sph = (rr * math.cos(th), yy, rr * math.sin(th))
    p.ringk = k % 2


def F_globe(p, t):
    if p.role == "ring" or p.amber:
        k = 0 if p.amber else 1
        ang = p.th + (0.9 if k == 0 else -0.6) * t
        rad = (232, 262)[k] + p.jit[0] * 5
        w = (rad * math.cos(ang), p.jit[1] * 3, rad * math.sin(ang))
        w = rot_x(w, (1.22, 1.32)[k])
        w = rot_z(w, (-0.30, 0.34)[k])
    else:
        w = tuple(c * GLOBE_R for c in p.sph)
        w = rot_y(w, 0.45 * t)
        w = rot_x(w, 0.32)
    x, y, s, z = cam(w, 0, 0, *GLOBE_C)
    return x, y, p.base * 1.9 * s, 0.2 + 0.8 * clamp(0.5 - z / 320)


def F_tunnel_end(p, t):
    return F_tunnel(p, t - T)


# timeline: (formation, hold_start, hold_end) -- transitions fill the gaps
SEGS = [
    (F_tunnel, 0.0, 2.1),
    (F_logo, 3.5, 7.0),
    (F_flow, 8.1, 15.2),
    (F_ico, 16.2, 23.2),
    (F_kda, 24.2, 31.1),
    (F_bars, 32.0, 38.5),
    (F_globe, 39.6, 46.0),
    (F_tunnel_end, 47.4, T),
]

for p in parts:
    p.trans = []
    for k in range(len(SEGS) - 1):
        gap0, gap1 = SEGS[k][2], SEGS[k + 1][1]
        dur = (gap1 - gap0) * rng.uniform(0.55, 0.75)
        st = gap0 + rng.random() * (gap1 - gap0 - dur)
        p.trans.append((st, st + dur, rng.uniform(-1, 1), rng.uniform(0.6, 1.4)))


def particle_state(p, t):
    for k, (fn, a, b) in enumerate(SEGS):
        if a <= t <= b:
            return fn(p, t)
        if k + 1 < len(SEGS) and b < t < SEGS[k + 1][1]:
            st, en, swirl, boost = p.trans[k]
            A = fn(p, t)
            B = SEGS[k + 1][0](p, t)
            u = ease((t - st) / (en - st))
            dx, dy = B[0] - A[0], B[1] - A[1]
            dist = math.hypot(dx, dy) + 1e-6
            bump = math.sin(math.pi * u)
            ox, oy = -dy / dist * swirl * 0.38 * dist * bump, dx / dist * swirl * 0.38 * dist * bump
            x = lerp(A[0], B[0], u) + ox
            y = lerp(A[1], B[1], u) + oy
            r = lerp(A[2], B[2], u) * (1 + 0.7 * boost * bump)
            al = lerp(A[3], B[3], u)
            al = max(al, 0.75 * bump * max(A[3], B[3], 0.6))
            return x, y, r, al
    return SEGS[-1][0](p, t)


def simplify(ts, chans, tol, vis):
    """Douglas-Peucker on one channel group: chans is a list of value lists sharing times ts.
    vis[k] False means the sample is invisible, so its position does not need to be exact."""
    n = len(ts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        worst, wk = 1.0, -1
        span = ts[j] - ts[i]
        for k in range(i + 1, j):
            if not (vis[k] or vis[i] or vis[j]):
                continue
            u = (ts[k] - ts[i]) / span
            e = max(abs(lerp(c[i], c[j], u) - c[k]) for c in chans) / tol
            if e > worst:
                worst, wk = e, k
        if wk >= 0:
            keep[wk] = True
            stack.append((i, wk))
            stack.append((wk, j))
    return [k for k in range(n) if keep[k]]


def keyed(attr, idx, ts, fmtv, kind=None):
    keys = ";".join(kt(ts[k]) for k in idx)
    vals = ";".join(fmtv(k) for k in idx)
    if kind:
        return (f'<animateTransform attributeName="transform" type="{kind}" dur="{f(T)}s" '
                f'repeatCount="indefinite" keyTimes="{keys}" values="{vals}"/>')
    return f'<animate attributeName="{attr}" dur="{f(T)}s" repeatCount="indefinite" keyTimes="{keys}" values="{vals}"/>'


def particles_svg():
    out = []
    steps = int(T * FPS)
    ts = [s / FPS for s in range(steps + 1)]
    for p in parts:
        X, Y, R, A = [], [], [], []
        for t in ts:
            x, y, r, a = particle_state(p, t)
            X.append(clamp(x, -60, W + 60))
            Y.append(clamp(y, -60, H + 60))
            R.append(r)
            A.append(clamp(a))
        vis = [a > 0.03 and -20 < x < W + 20 and -20 < y < H + 20 for a, x, y in zip(A, X, Y)]
        i_pos = simplify(ts, [X, Y], 1.1, vis)
        i_r = simplify(ts, [R], 0.3, vis)
        i_a = simplify(ts, [A], 0.07, [True] * len(ts))
        out.append(
            f'<circle r="{f(R[0])}" fill="url(#{p.grad})" opacity="{f(A[0], 2)}" '
            f'transform="translate({X[0]:.0f} {Y[0]:.0f})">'
            + keyed(None, i_pos, ts, lambda k: f"{X[k]:.0f} {Y[k]:.0f}", "translate")
            + keyed("r", i_r, ts, lambda k: f(R[k]))
            + keyed("opacity", i_a, ts, lambda k: f(A[k], 2))
            + "</circle>")
    return "\n".join(out)


# --------------------------------------------------------------------- sampled shape animation

def frames(t0, t1, fps):
    n = max(2, int(round((t1 - t0) * fps)))
    return [t0 + (t1 - t0) * k / n for k in range(n + 1)]


def path_anim(ts, ds, t_in, t_out, fade=0.5, attrs="", extra_anims="", op_vals=None):
    """A <path> whose d is keyed at times ts (within [t_in, t_out]) and visible only in between."""
    pairs = [(0, ds[0])] + list(zip(ts, ds)) + [(T, ds[-1])]
    keys = ";".join(kt(t) for t, _ in pairs)
    vals = ";".join(d for _, d in pairs)
    da = f'<animate attributeName="d" dur="{f(T)}s" repeatCount="indefinite" keyTimes="{keys}" values="{vals}"/>'
    if op_vals is None:
        oa = anim("opacity", window(t_in, t_out, fade))
    else:
        w = window(t_in, t_out, fade)
        oa = anim("opacity", [(t, f(v * (op_vals[min(range(len(ts)), key=lambda k: abs(ts[k] - t))]), 2))
                              for t, v in w])
    return f'<path d="{ds[0]}" opacity="0" {attrs}>{da}{oa}{extra_anims}</path>'


def poly_d(pts, close=True):
    s = "M" + "L".join(f"{x:.0f} {y:.0f}" for x, y in pts)
    return s + ("Z" if close else "")


# ---------------------------------------------------------------------------- scene builders

def scene_flow():
    t_in, t_out = 7.4, 15.6
    ts = frames(t_in - 0.2, t_out + 0.2, 8)
    out = []
    grid_d_all, fill_d_all = [[] for _ in PLANE_Y], [[] for _ in PLANE_Y]
    for t in ts:
        yaw = flow_yaw(t)
        for k, py in enumerate(PLANE_Y):
            h = PLANE_HALF
            corners = [cam((x, py, z), yaw, FLOW_PITCH, *FLOW_C)[:2] for x, z in ((-h, -h), (h, -h), (h, h), (-h, h))]
            fill_d_all[k].append(poly_d(corners))
            g = []
            for v in (-h / 2, 0, h / 2):
                a = cam((v, py, -h), yaw, FLOW_PITCH, *FLOW_C)[:2]
                b = cam((v, py, h), yaw, FLOW_PITCH, *FLOW_C)[:2]
                c = cam((-h, py, v), yaw, FLOW_PITCH, *FLOW_C)[:2]
                d = cam((h, py, v), yaw, FLOW_PITCH, *FLOW_C)[:2]
                g.append(f"M{a[0]:.0f} {a[1]:.0f}L{b[0]:.0f} {b[1]:.0f}M{c[0]:.0f} {c[1]:.0f}L{d[0]:.0f} {d[1]:.0f}")
            grid_d_all[k].append("".join(g))
    names = ["FLOWS", "RUNTIME", "AGENTS", "APPLICATIONS"]
    for k in reversed(range(len(PLANE_Y))):  # far (bottom) first
        hl = k == 1
        stroke = AMBER if hl else BLUE_LIGHT
        out.append(path_anim(ts, fill_d_all[k], t_in + 0.15 * k, t_out - 0.1 * k,
                             attrs=f'fill="url(#{"planeA" if hl else "planeB"})" stroke="{stroke}" '
                                   f'stroke-opacity="{0.9 if hl else 0.55}" stroke-width="1.4"'))
        out.append(path_anim(ts, grid_d_all[k], t_in + 0.15 * k, t_out - 0.1 * k,
                             attrs=f'fill="none" stroke="{stroke}" stroke-opacity="0.22" stroke-width="1"'))
    # agent names orbiting the AGENTS plane
    agents = ["claude", "codex", "dsh", "agy", "grok", "kimi", "qwen", "pi", "opencode", "mimo"]
    for n, name in enumerate(agents):
        ang0 = 2 * math.pi * n / len(agents)
        tts = frames(t_in, t_out, 10)
        pairs_tr, pairs_op, pairs_sc = [], [], []
        for t in tts:
            ang = ang0 + 0.28 * (t - t_in)
            w = (228 * math.cos(ang), 40, 228 * math.sin(ang))
            x, y, s, z = cam(w, flow_yaw(t), FLOW_PITCH, *FLOW_C)
            pairs_tr.append((t, f"{x:.0f} {y:.0f}"))
            pairs_sc.append((t, f(s, 2)))
            depth = clamp(0.5 - z / 600)
            env = smooth((t - t_in - 0.6) / 0.8) * smooth((t_out - 0.3 - t) / 0.6)
            pairs_op.append((t, f((0.25 + 0.75 * depth) * env, 2)))
        out.append(f'<g opacity="0">{anim("opacity", pairs_op)}{anim_tf("translate", pairs_tr)}'
                   f'{anim_tf("scale", pairs_sc, additive=True)}'
                   f'<text class="agent" text-anchor="middle" y="4">{name}</text></g>')
    # labels for each plane (plane centres project to a fixed y since the stack spins on its axis)
    plane_y = [cam((0, py, 0), 0.6, FLOW_PITCH, *FLOW_C)[1] for py in PLANE_Y]
    label_y = [198, 278, 358, 438]
    rows = [
        ("FLOWS", "RLAR · Flame Chase · Humanize 1 · Ralph Loop", "the method, as code — humanfia/flowverse"),
        ("RUNTIME", "Humanize 2", "sessions · budgets · traces · worktrees · containers · ssh"),
        ("AGENTS", "the CLIs you already log into", "claude · codex · dsh · agy · grok · kimi · qwen · pi · opencode · mimo"),
        ("APPLICATIONS", "HOA · KDA · HKA", "where a flow is found out — someone else keeps the scoreboard"),
    ]
    for k, (tag, main, sub) in enumerate(rows):
        y, py = label_y[k], plane_y[k]
        col = AMBER if k == 1 else BLUE_LIGHT
        body = (f'<path d="M560 {py:.0f}H600L640 {y - 4:.0f}H652" fill="none" stroke="{col}" stroke-opacity="0.6" stroke-dasharray="2 4"/>'
                f'<circle cx="560" cy="{py:.0f}" r="3" fill="{col}"/>'
                + text(664, y - 16, tag, "tag" if k == 1 else "tagb")
                + text(664, y + 7, main, "lab")
                + text(664, y + 27, sub, "labs"))
        out.append(reveal(body, t_in + 0.5 + 0.25 * k, t_out, dx=24, dy=0))
    out.append(reveal(text(664, 82, "02 — THE RUNTIME", "tag")
                      + text(662, 128, "Humanize 2", "h1")
                      + text(664, 152, "Agent Flow System — the flow around the agents", "sub"), t_in + 0.2, t_out))
    # FlowBench arc label
    out.append(reveal(f'<path d="M46 112 l6 -8 l6 8" fill="none" stroke="{AMBER}" stroke-width="1.6"/>'
                      + text(66, 112, "FLOWBENCH", "tag")
                      + text(46, 132, "measures · selects · ships it back", "labs"), t_in + 1.4, t_out, dy=-10))
    # typed install line
    cmd = "$ uv tool install hmz"
    out.append(typed(664, 522, cmd, t_in + 2.4, t_out, "cmd", width=12.2 * len(cmd)))
    return "\n".join(out)


_CLIPS = 0


def typed(x, y, s, t_in, t_out, cls, width):
    global _CLIPS
    _CLIPS += 1
    cid = f"type{_CLIPS}"
    dur = 0.045 * len(s)
    clip = (f'<clipPath id="{cid}"><rect x="{x - 4}" y="{y - 22}" height="32" width="0">'
            + anim("width", [(0, 0), (t_in, 0), (t_in + dur, width + 8), (T, width + 8)])
            + "</rect></clipPath>")
    caret = (f'<rect x="{x}" y="{y - 15}" width="9" height="19" fill="{AMBER}">'
             + anim_tf("translate", [(0, "0 0"), (t_in, "0 0"), (t_in + dur, f"{width + 4:.0f} 0"), (T, f"{width + 4:.0f} 0")])
             + anim("opacity", [(0, 0), (t_in, 0)] + [(t_in + dur + 0.25 * k, (k + 1) % 2) for k in range(0, int((t_out - t_in - dur) / 0.25))] + [(t_out, 0)], calc="discrete")
             + "</rect>")
    return (f'{clip}<g opacity="0">{anim("opacity", window(t_in, t_out, 0.3))}'
            f'<g clip-path="url(#{cid})">{text(x, y, s, cls)}</g>{caret}</g>')


def counter(x, y, finals, t0, t_out, cls, anchor="start", dur=1.1):
    """Roll through `finals` (list of strings, last is the real value) between t0 and t0+dur."""
    n = len(finals)
    dt = dur / n
    out = []
    for k, s in enumerate(finals):
        a = t0 + k * dt
        b = t0 + (k + 1) * dt
        if k == 0:
            pairs = [(0, 1), (b, 0)]
        elif k == n - 1:
            pairs = [(0, 0), (a, 1)]
        else:
            pairs = [(0, 0), (a, 1), (b, 0)]
        op = anim("opacity", pairs, calc="discrete")
        out.append(f'<g opacity="{1 if k == 0 else 0}">{op}{text(x, y, s, cls, anchor)}</g>')
    return "".join(out)


def roll(final, steps=9, fmt="{:.0f}", start=0.0, prefix="", suffix=""):
    vals = [start + (final - start) * ease(k / (steps - 1)) for k in range(steps)]
    return [prefix + fmt.format(v) + suffix for v in vals[:-1]] + [prefix + fmt.format(final) + suffix]


def card(x, y, w, h, nums, cap1, cap2, t_in, t_out, num_dx=24, cap_x=None, big=True, accent=BLUE_LIGHT):
    cap_x = cap_x if cap_x is not None else x + num_dx
    body = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="url(#glass)" stroke="{accent}" stroke-opacity="0.28"/>'
            f'<rect x="{x}" y="{y + 16}" width="3" height="{h - 32}" rx="1.5" fill="{accent}"/>')
    if big:  # number on the left, captions on the right
        body += counter(x + num_dx, y + h / 2 + 16, nums, t_in + 0.4, t_out, "num")
        body += text(cap_x, y + h / 2 - 4, cap1, "lab") + text(cap_x, y + h / 2 + 18, cap2, "labs")
    else:
        body += counter(x + num_dx, y + 54, nums, t_in + 0.4, t_out, "nums")
        body += text(x + num_dx, y + 80, cap1, "lab2") + text(x + num_dx, y + 99, cap2, "labs")
    return reveal(body, t_in, t_out, dx=30, dy=0)


def scene_hoa():
    t_in, t_out = 15.7, 23.6
    out = []
    ts = frames(t_in - 0.2, t_out + 0.2, 10)
    for e in ICO_E:
        ds, ops = [], []
        for t in ts:
            a = cam(ico_world(ICO_V[e[0]], t), 0, 0, *ICO_C)
            b = cam(ico_world(ICO_V[e[1]], t), 0, 0, *ICO_C)
            ds.append(f"M{a[0]:.0f} {a[1]:.0f}L{b[0]:.0f} {b[1]:.0f}")
            ops.append(0.12 + 0.5 * clamp(0.5 - (a[3] + b[3]) / (4 * ICO_R)))
        pairs = [(t, f(o, 2)) for t, o in zip(ts, ops)]
        env = window(t_in + 0.4, t_out - 0.2, 0.6)
        op_pairs = [(t, f(float(o) * (1 if t_in + 1.0 < t < t_out - 0.8 else 0), 2)) for t, o in pairs]
        op_pairs = [(0, 0), (t_in + 0.4, 0)] + [p for p in op_pairs if t_in + 1.0 <= p[0] <= t_out - 0.8] + [(t_out - 0.2, 0)]
        keys_d = [(0, ds[0])] + list(zip(ts, ds)) + [(T, ds[-1])]
        out.append(f'<path d="{ds[0]}" stroke="{BLUE_PALE}" stroke-width="1.1" fill="none" opacity="0">'
                   f'<animate attributeName="d" dur="{f(T)}s" repeatCount="indefinite" '
                   f'keyTimes="{";".join(kt(t) for t, _ in keys_d)}" values="{";".join(d for _, d in keys_d)}"/>'
                   f'{anim("opacity", op_pairs)}</path>')
    # vertices
    for v in ICO_V:
        tts = frames(t_in + 0.4, t_out - 0.2, 10)
        tr, op = [], []
        for t in tts:
            x, y, s, z = cam(ico_world(v, t), 0, 0, *ICO_C)
            tr.append((t, f"{x:.0f} {y:.0f}"))
            env = smooth((t - t_in - 1.0) / 0.6) * smooth((t_out - 0.4 - t) / 0.5)
            op.append((t, f((0.35 + 0.65 * clamp(0.5 - z / (2 * ICO_R))) * env, 2)))
        out.append(f'<circle r="7" fill="url(#gA)" opacity="0">{anim_tf("translate", tr)}{anim("opacity", op)}</circle>')
    # orbiting Lean / maths glyphs
    glyphs = ["∀", "∃", "⊢", "λ", "∑", "∫", "π", "ℝ", "≤", "→", "ℕ", "∂"]
    for n, gch in enumerate(glyphs):
        tts = frames(t_in, t_out, 8)
        tr, sc, op = [], [], []
        incl = 0.5 + 0.9 * (n % 3) / 2
        for t in tts:
            ang = 2 * math.pi * n / len(glyphs) + 0.32 * (t - t_in)
            w = rot_x((245 * math.cos(ang), 0, 245 * math.sin(ang)), incl)
            x, y, s, z = cam(w, 0, 0, *ICO_C)
            tr.append((t, f"{x:.0f} {y:.0f}"))
            sc.append((t, f(s, 2)))
            env = smooth((t - t_in - 0.7) / 0.8) * smooth((t_out - 0.3 - t) / 0.6)
            op.append((t, f((0.15 + 0.7 * clamp(0.5 - z / 500)) * env, 2)))
        out.append(f'<g opacity="0">{anim("opacity", op)}{anim_tf("translate", tr)}{anim_tf("scale", sc, True)}'
                   f'<text class="glyph" text-anchor="middle" y="8">{esc(gch)}</text></g>')
    out.append(reveal(text(640, 82, "03 — HOA · HUMANIZE OLYMPIC AGENTS", "tag")
                      + text(638, 128, "Lean accepts it, or it does not.", "h2")
                      + text(640, 154, "Fully agentic mathematics, machine-checked end to end.", "sub"), t_in + 0.2, t_out))
    cy0 = 188
    out.append(card(640, cy0, 520, 92, roll(6, 7, prefix="", suffix="/6"), "IMO 2026 · all six problems",
                    "Lean 4 checked · 3.2× faster · two backends", t_in + 0.6, t_out, cap_x=880))
    out.append(card(640, cy0 + 106, 520, 92, ["#9", "#7", "#5", "#4", "#3", "#2", "#1"], "Lean-Eval leaderboard · first place",
                    "172 research-level proofs, re-verified", t_in + 0.9, t_out, cap_x=880, accent=AMBER))
    out.append(card(640, cy0 + 212, 520, 92, roll(670, 9, suffix="/672"), "PutnamBench",
                    "plus physics & quantum, formalized", t_in + 1.2, t_out, cap_x=880))
    out.append(reveal(text(60, 540, "theorem imo_2026_p6 … := by", "code")
                      + text(330, 540, "✓ 0 sorry", "codeok"), t_in + 2.4, t_out))
    return "\n".join(out)


def box_faces(x0, z0, sx, sz, h, yaw, pitch, C, y0=0.0):
    """Visible faces (top, +x, -z) of an axis-aligned box standing on y=y0 (y is down)."""
    def P(x, y, z):
        return cam((x, y, z), yaw, pitch, *C)[:2]
    x1, z1 = x0 + sx, z0 + sz
    yt = y0 - h
    top = [P(x0, yt, z0), P(x1, yt, z0), P(x1, yt, z1), P(x0, yt, z1)]
    right = [P(x1, yt, z0), P(x1, yt, z1), P(x1, y0, z1), P(x1, y0, z0)]
    front = [P(x0, yt, z0), P(x1, yt, z0), P(x1, y0, z0), P(x0, y0, z0)]
    return top, right, front


def mix(c1, c2, u):
    a = [int(c1[k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(c2[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(lerp(x, y, u)):02x}" for x, y in zip(a, b))


def shade(c, k):
    a = [int(c[j:j + 2], 16) for j in (1, 3, 5)]
    return "#" + "".join(f"{clamp(round(v * k), 0, 255):02x}" for v in a)


def scene_kda():
    t_in, t_out = 23.7, 31.6
    out = []
    ts = frames(t_in - 0.2, t_out + 0.2, 6)
    cells = [(i, j) for i in range(GRID) for j in range(GRID)]
    cells.sort(key=lambda c: (c[0] - 2.5) - (c[1] - 2.5) * -1)  # far (small x, large z) first
    cells.sort(key=lambda c: c[0] - c[1])
    for (i, j) in cells:
        x0 = (i - GRID / 2) * CELL + (CELL - CUBE) / 2
        z0 = (j - GRID / 2) * CELL + (CELL - CUBE) / 2
        cx_, cz_ = i - 2.5, j - 2.5
        heat = math.exp(-((cx_ - 0.8) ** 2 + (cz_ + 0.6) ** 2) / 3.0)
        hv = clamp(heat * 1.15)
        base = mix(BLUE, BLUE_MID, hv / 0.45) if hv < 0.45 else mix("#c9782a", AMBER, (hv - 0.45) / 0.55)
        faces = [[], [], []]
        for t in ts:
            hgt = kda_height(i, j, t)
            fs = box_faces(x0, z0, CUBE, CUBE, hgt, kda_yaw(t), KDA_PITCH, KDA_C)
            for k in range(3):
                faces[k].append(poly_d(fs[k]))
        delay = 0.03 * (i + j)
        cols = [mix(base, "#ffffff", 0.22), shade(base, 0.72), shade(base, 0.5)]
        for k in range(3):
            out.append(path_anim(ts, faces[k], t_in + 0.2 + delay, t_out - 0.1 - delay * 0.5,
                                 attrs=f'fill="{cols[k]}" stroke="{mix(base, "#ffffff", 0.5)}" '
                                       f'stroke-opacity="{0.55 if k == 0 else 0.18}" stroke-width="0.8"'))
    # chip outline under the grid
    ds = []
    for t in ts:
        hs = GRID * CELL / 2 + 22
        pts = [cam((x, 2, z), kda_yaw(t), KDA_PITCH, *KDA_C)[:2] for x, z in ((-hs, -hs), (hs, -hs), (hs, hs), (-hs, hs))]
        ds.append(poly_d(pts))
    out.insert(0, path_anim(ts, ds, t_in, t_out, attrs=f'fill="url(#planeB)" stroke="{BLUE_LIGHT}" stroke-opacity="0.5" stroke-dasharray="6 5"'))
    out.append(reveal(text(640, 82, "04 — KDA · KERNEL DESIGN AGENTS", "tag")
                      + text(638, 128, "Faster, or it is not.", "h2")
                      + text(640, 154, "Agents that research, write, verify and profile CUDA kernels.", "sub"), t_in + 0.2, t_out))
    cw, ch = 252, 112
    out.append(card(640, 186, cw, ch, roll(1.39, 9, "{:.2f}", 1.0, suffix="×"), "past the best human entries",
                    "MLSys’26 FlashInfer · all 3 tracks", t_in + 0.6, t_out, big=False, accent=AMBER))
    out.append(card(908, 186, cw, ch, ["#6", "#5", "#4", "#3", "#2", "#1"], "SOLExec Bench · L1 ops",
                    "score 0.7608 · first place", t_in + 0.85, t_out, big=False))
    out.append(card(640, 312, cw, ch, roll(53, 9), "first places on SOL Bench",
                    "one 8×B200 node · one week", t_in + 1.1, t_out, big=False))
    out.append(card(908, 312, cw, ch, roll(6.5, 9, "{:.1f}", 1.0, suffix="×"), "MSA indexer prefill · B300",
                    "3.3× decode · bitwise-identical", t_in + 1.35, t_out, big=False))
    out.append(reveal(text(640, 462, "merged into SGLang · 5.84× kernel geomean · lossless numerics", "lab")
                      + text(640, 486, "B200 · B300 · CUDA · CuteDSL · HIP / ROCm", "code"), t_in + 1.8, t_out))
    return "\n".join(out)


def scene_bars():
    t_in, t_out = 31.2, 38.9
    out = []
    ts = frames(t_in - 0.2, t_out + 0.2, 8)
    order = sorted(BARS, key=lambda b: b[0])
    for bx, pct in order:
        faces = [[], [], []]
        for t in ts:
            hgt = max(3, pct * BAR_SCALE * bar_grow(t))
            fs = box_faces(bx - 32, -32, 64, 64, hgt, BAR_YAW, BAR_PITCH, BAR_C)
            for k in range(3):
                faces[k].append(poly_d(fs[k]))
        hero = pct > 1
        base = AMBER if hero else BLUE_MID
        cols = [mix(base, "#ffffff", 0.3), shade(base, 0.65), shade(base, 0.45)]
        for k in range(3):
            out.append(path_anim(ts, faces[k], t_in + 0.2, t_out - 0.1,
                                 attrs=f'fill="{cols[k]}" stroke="{mix(base, "#ffffff", 0.55)}" stroke-opacity="0.5" stroke-width="0.8"'))
    # floor plate
    pts = [cam((x, 0, z), BAR_YAW, BAR_PITCH, *BAR_C)[:2] for x, z in ((-240, -110), (240, -110), (240, 110), (-240, 110))]
    out.insert(0, reveal(f'<path d="{poly_d(pts)}" fill="url(#planeB)" stroke="{BLUE_LIGHT}" stroke-opacity="0.45"/>', t_in, t_out, dy=0))
    labels = [("0.5%", "model A, alone"), ("0%", "model B, alone"), ("3.5%", "A ⇄ B in a loop")]
    for (bx, pct), (val, cap) in zip(BARS, labels):
        topx, topy = cam((bx, -pct * BAR_SCALE - 12, 0), BAR_YAW, BAR_PITCH, *BAR_C)[:2]
        botx, boty = cam((bx, 0, -70), BAR_YAW, BAR_PITCH, *BAR_C)[:2]
        cls = "barv" if pct > 1 else "barvs"
        out.append(reveal(text(topx, topy - 8, val, cls, "middle"), 33.0 + pct * 0.12, t_out, dy=10))
        out.append(reveal(text(botx, boty + 34, cap, "labs", "middle"), t_in + 0.8, t_out, dy=8))
    out.append(reveal(text(640, 82, "05 — THE FLOW IS THE MULTIPLIER", "tag")
                      + text(638, 128, "Same models. Better flow.", "h2")
                      + text(640, 154, "Measured three ways: model level, tool level, flow level.", "sub"), t_in + 0.2, t_out))
    out.append(card(640, 188, 520, 92, roll(3.5, 8, "{:.1f}", 0.0, suffix="%"), "ProgramBench · builder ⇄ reviewer",
                    "vs 0.5% and 0% for the same two models alone", t_in + 0.6, t_out, cap_x=800, accent=AMBER))
    out.append(card(640, 294, 520, 92, roll(19, 8), "Kaggle competitions · HKA",
                    "ten workflows, scored by Kaggle, not by us", t_in + 0.9, t_out, cap_x=800))
    chips = [("MODEL", 640), ("TOOL", 790), ("FLOW", 940)]
    body = ""
    for k, (lab, x) in enumerate(chips):
        hl = k == 2
        body += (f'<rect x="{x}" y="414" width="110" height="34" rx="17" fill="{AMBER if hl else "none"}" '
                 f'fill-opacity="{0.16 if hl else 0}" stroke="{AMBER if hl else BLUE_LIGHT}" stroke-opacity="{0.9 if hl else 0.45}"/>'
                 + text(x + 55, 436, lab, "chip" if not hl else "chipa", "middle"))
        if k < 2:
            body += f'<path d="M{x + 118} 431h26m-6 -5l6 5l-6 5" fill="none" stroke="{BLUE_LIGHT}" stroke-opacity="0.7"/>'
    body += text(640, 478, "PutnamBench · Physics Cup · SuperChem · HLE — the flow is worth more", "labs")
    body += text(640, 497, "than the gap between model generations.", "labs")
    out.append(reveal(body, t_in + 1.3, t_out))
    return "\n".join(out)


def scene_intro():
    out = []
    t_in, t_out = 3.6, 7.3
    lx, ly = LOGO_C
    sc = LOGO_H / 57
    tf = f"translate({lx - 25.5 * sc:.2f} {ly - 28.5 * sc:.2f}) scale({sc:.4f})"
    paths = "".join(f'<path transform="translate({tx} {ty})" d="{d}"/>' for d, tx, ty in LOGO_PATHS)
    # outline draw + soft fill
    out.append(f'<g transform="{tf}" opacity="0">{anim("opacity", window(4.4, t_out, 0.4))}'
               f'<g transform="{LOGO_MATRIX}" fill="url(#logoFill)" stroke="{BLUE_PALE}" stroke-width="10" '
               f'stroke-dasharray="4000" stroke-dashoffset="4000" fill-opacity="0">'
               f'{anim("stroke-dashoffset", [(0, 4000), (4.4, 4000), (6.0, 0), (T, 0)])}'
               f'{anim("fill-opacity", [(0, 0), (5.2, 0), (6.2, 0.22), (T, 0.22)])}{paths}</g></g>')
    # shock ring + lens streak when the H locks in
    out.append(f'<circle cx="{lx}" cy="{ly}" r="10" fill="none" stroke="{BLUE_PALE}" stroke-width="2" opacity="0">'
               f'{anim("r", [(0, 10), (4.3, 10), (5.8, 560), (T, 560)])}'
               f'{anim("opacity", [(0, 0), (4.3, 0), (4.35, 0.8), (5.8, 0), (T, 0)])}'
               f'{anim("stroke-width", [(0, 6), (4.3, 6), (5.8, 0.5), (T, 0.5)])}</circle>')
    out.append(f'<ellipse cx="{lx}" cy="{ly}" rx="560" ry="2.4" fill="url(#streak)" opacity="0">'
               f'{anim("opacity", [(0, 0), (4.25, 0), (4.45, 0.95), (5.6, 0), (T, 0)])}'
               f'{anim("ry", [(0, 2.4), (4.25, 2.4), (4.45, 5), (5.6, 1), (T, 1)])}</ellipse>')
    out.append(reveal(text(600, 418, "HUMANFIA", "hero", "middle"), 4.6, t_out, dy=18))
    out.append(typed(600 - 0.5 * 10.4 * 36, 460, "We build the flow around the agents.", 5.1, t_out, "tagline", 10.4 * 36))
    out.append(reveal(text(600, 504, "HUMANIZE · FLOWVERSE · FLOWBENCH · HOA · KDA · HKA", "kicker", "middle"), 5.6, t_out, dy=8))
    return "\n".join(out)


def scene_finale():
    out = []
    t_in, t_out = 39.0, 46.6
    gx, gy = GLOBE_C
    sc = 96 / 57
    tf = f"translate({gx - 25.5 * sc:.2f} {gy - 28.5 * sc:.2f}) scale({sc:.4f})"
    paths = "".join(f'<path transform="translate({tx} {ty})" d="{d}"/>' for d, tx, ty in LOGO_PATHS)
    out.append(f'<circle cx="{gx}" cy="{gy}" r="150" fill="url(#core)" opacity="0">{anim("opacity", window(t_in + 0.6, t_out, 0.8, 0.9))}</circle>')
    # globe wireframe: parallels are invariant under the spin, meridians repeat every 30 degrees,
    # so they loop on their own short clock (phase-locked to the particles, which share t = 0)
    def gp(v):
        return cam(rot_x(v, 0.32), 0, 0, *GLOBE_C)[:2]
    wire = []
    for lat in (-60, -30, 0, 30, 60):
        la = math.radians(lat)
        pts = [gp((GLOBE_R * math.cos(la) * math.cos(a), GLOBE_R * math.sin(la), GLOBE_R * math.cos(la) * math.sin(a)))
               for a in [2 * math.pi * k / 40 for k in range(40)]]
        wire.append(f'<path d="{poly_d(pts)}" fill="none" stroke="{BLUE_LIGHT}" stroke-opacity="0.16"/>')
    period = (math.pi / 6) / 0.45
    for m in range(6):
        ds = []
        for fk in range(13):
            ang = math.pi * m / 6 + 0.45 * period * fk / 12
            pts = [gp(rot_y((GLOBE_R * math.cos(b), GLOBE_R * math.sin(b), 0), ang))
                   for b in [2 * math.pi * k / 36 for k in range(36)]]
            ds.append(poly_d(pts))
        wire.append(f'<path d="{ds[0]}" fill="none" stroke="{BLUE_LIGHT}" stroke-opacity="0.2">'
                    f'<animate attributeName="d" dur="{period:.4f}s" repeatCount="indefinite" values="{";".join(ds)}"/></path>')
    out.append(f'<g opacity="0">{anim("opacity", window(t_in + 0.3, t_out, 0.9))}{"".join(wire)}</g>')
    out.append(f'<g opacity="0">{anim("opacity", window(t_in + 1.0, t_out - 0.3, 0.8))}'
               f'<g transform="{tf}"><g transform="{LOGO_MATRIX}" fill="{SLATE_PALE}">{paths}</g></g>'
               '</g>')
    out.append(reveal(text(600, 452, "HUMANFIA", "hero2", "middle"), t_in + 0.8, t_out, dy=16))
    out.append(reveal(text(600, 484, "We build the flow around the agents. Built in public.", "tagline", "middle"), t_in + 1.2, t_out, dy=10))
    chips = ["Humanize 2", "Flowverse", "FlowBench", "HOA", "KDA", "HKA", "oh-my-humanize"]
    widths = [len(c) * 8.4 + 30 for c in chips]
    total = sum(widths) + 10 * (len(chips) - 1)
    x = 600 - total / 2
    for k, (c, w) in enumerate(zip(chips, widths)):
        hl = c == "Humanize 2"
        body = (f'<rect x="{x:.0f}" y="503" width="{w:.0f}" height="28" rx="14" fill="{AMBER if hl else BLUE_MID}" '
                f'fill-opacity="{0.18 if hl else 0.10}" stroke="{AMBER if hl else BLUE_LIGHT}" stroke-opacity="0.55"/>'
                + text(x + w / 2, 522, c, "chipa" if hl else "chip", "middle"))
        out.append(reveal(body, t_in + 1.6 + 0.09 * k, t_out, dy=10))
        x += w + 10
    out.append(reveal(text(600, 555, "humanfia.ai   ·   docs.humanfia.ai/humanize   ·   github.com/humanfia", "code", "middle"),
                      t_in + 2.4, t_out, dy=6))
    return "\n".join(out)


# ------------------------------------------------------------------------------- background

def background():
    out = []
    # drifting nebulae
    for cx_, cy_, rx, ry, grad, mv in [(260, 150, 520, 320, "neb1", "60 30"), (960, 470, 560, 330, "neb2", "-70 -20"),
                                        (700, 80, 380, 220, "neb3", "-40 25")]:
        out.append(f'<ellipse cx="{cx_}" cy="{cy_}" rx="{rx}" ry="{ry}" fill="url(#{grad})">'
                   f'<animateTransform attributeName="transform" type="translate" dur="24s" repeatCount="indefinite" '
                   f'values="0 0;{mv};0 0" calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/></ellipse>')
    # perspective floor grid
    hz = 430
    g = [f'<g opacity="0.55" mask="url(#floorMask)">']
    for k in range(-14, 15):
        x2 = 600 + k * 150
        g.append(f'<line x1="{600 + k * 18}" y1="{hz}" x2="{x2}" y2="{H + 20}" stroke="{BLUE_MID}" stroke-opacity="0.35" stroke-width="1"/>')
    nl = 9
    period = 3.0
    ys = [hz + 900 / (z) for z in [60 - 50 * k / 11 for k in range(12)]]
    vals = ";".join(f"{min(y, H + 30):.1f}" for y in ys)
    for k in range(nl):
        g.append(f'<rect x="0" width="{W}" height="1" fill="{BLUE_MID}" fill-opacity="0.4">'
                 f'<animate attributeName="y" dur="{period}s" begin="{-period * k / nl:.2f}s" repeatCount="indefinite" values="{vals}"/></rect>')
    g.append("</g>")
    out.append("".join(g))
    # twinkling dust
    for _ in range(90):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(0.4, 1.2)
        d = rng.uniform(2.5, 6)
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{f(r)}" fill="{rng.choice([BLUE_PALE, SLATE_PALE, BLUE_LIGHT])}" opacity="0.2">'
                   f'<animate attributeName="opacity" dur="{f(d)}s" begin="-{f(rng.uniform(0, d))}s" repeatCount="indefinite" '
                   f'values="0.08;{f(rng.uniform(0.4, 0.9), 2)};0.08"/></circle>')
    return "\n".join(out)


CHAPTERS = [("INTRO", 0.0, 7.4), ("HUMANIZE 2", 7.4, 15.6), ("HOA", 15.6, 23.6), ("KDA", 23.6, 31.4),
            ("FLOW > MODEL", 31.4, 38.9), ("BUILT IN PUBLIC", 38.9, T)]


def hud():
    out = []
    sc = 22 / 57
    paths = "".join(f'<path transform="translate({tx} {ty})" d="{d}"/>' for d, tx, ty in LOGO_PATHS)
    out.append(f'<g transform="translate(36 26) scale({sc:.4f})"><g transform="{LOGO_MATRIX}" fill="{SLATE_PALE}">{paths}</g></g>')
    out.append(text(66, 43, "HUMANFIA", "hud"))
    out.append(text(W - 36, 43, "AGENT FLOW SYSTEMS · 2026", "hudr", "end"))
    # corner brackets
    for (x, y, sx, sy) in [(18, 18, 1, 1), (W - 18, 18, -1, 1), (18, H - 18, 1, -1), (W - 18, H - 18, -1, -1)]:
        out.append(f'<path d="M{x} {y + 22 * sy}V{y}H{x + 22 * sx}" fill="none" stroke="{BLUE_LIGHT}" stroke-opacity="0.45" stroke-width="1.5"/>')
    # chapter bar
    x0, x1, y = 60, W - 60, 582
    gap = 10
    seg_w = (x1 - x0 - gap * (len(CHAPTERS) - 1)) / len(CHAPTERS)
    for k, (name, a, b) in enumerate(CHAPTERS):
        x = x0 + k * (seg_w + gap)
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{seg_w:.1f}" height="2" rx="1" fill="{BLUE_LIGHT}" fill-opacity="0.18"/>')
        out.append(f'<rect x="{x:.1f}" y="{y}" width="0" height="2" rx="1" fill="url(#barFill)">'
                   + anim("width", [(0, 0), (a, 0), (b, f(seg_w)), (T - 0.001, f(seg_w)), (T, 0)]) + "</rect>")
        on = [(0, 0.35), (a, 0.35), (a + 0.3, 1), (b - 0.3, 1), (b, 0.35)] if k else [(0, 1), (b - 0.3, 1), (b, 0.35), (T - 0.4, 0.35), (T, 1)]
        out.append(f'<g opacity="0.35">{anim("opacity", on)}{text(x, y - 9, f"0{k + 1}  {name}", "chap")}</g>')
    return "\n".join(out)


DEFS = f"""
<defs>
  <radialGradient id="gB"><stop offset="0" stop-color="{WHITE}"/><stop offset="0.3" stop-color="{BLUE_LIGHT}"/><stop offset="1" stop-color="{BLUE_MID}" stop-opacity="0"/></radialGradient>
  <radialGradient id="gP"><stop offset="0" stop-color="{WHITE}"/><stop offset="0.35" stop-color="{BLUE_PALE}"/><stop offset="1" stop-color="{BLUE_PALE}" stop-opacity="0"/></radialGradient>
  <radialGradient id="gW"><stop offset="0" stop-color="{WHITE}"/><stop offset="0.3" stop-color="{SLATE_PALE}" stop-opacity="0.9"/><stop offset="1" stop-color="{SLATE_PALE}" stop-opacity="0"/></radialGradient>
  <radialGradient id="gA"><stop offset="0" stop-color="{AMBER_HI}"/><stop offset="0.3" stop-color="{AMBER}"/><stop offset="1" stop-color="{AMBER_DARK}" stop-opacity="0"/></radialGradient>
  <radialGradient id="neb1"><stop offset="0" stop-color="{NEB[0]}" stop-opacity="{NEB[1]}"/><stop offset="1" stop-color="{NEB[0]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="neb2"><stop offset="0" stop-color="{NEB[2]}" stop-opacity="{NEB[3]}"/><stop offset="1" stop-color="{NEB[2]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="neb3"><stop offset="0" stop-color="{NEB[4]}" stop-opacity="{NEB[5]}"/><stop offset="1" stop-color="{NEB[4]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="core"><stop offset="0" stop-color="{BLUE_LIGHT}" stop-opacity="0.35"/><stop offset="0.55" stop-color="{BLUE}" stop-opacity="0.12"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
  <radialGradient id="vign" cx="0.5" cy="0.45" r="0.75"><stop offset="0.6" stop-color="{VIGN[0]}" stop-opacity="0"/><stop offset="1" stop-color="{VIGN[0]}" stop-opacity="{VIGN[1]}"/></radialGradient>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG_STOPS[0]}"/><stop offset="0.6" stop-color="{BG_STOPS[1]}"/><stop offset="1" stop-color="{BG_STOPS[2]}"/></linearGradient>
  <linearGradient id="streak" x1="0" x2="1"><stop offset="0" stop-color="{BLUE_PALE}" stop-opacity="0"/><stop offset="0.5" stop-color="{WHITE}"/><stop offset="1" stop-color="{BLUE_PALE}" stop-opacity="0"/></linearGradient>
  <linearGradient id="logoFill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{WHITE}"/><stop offset="1" stop-color="{BLUE_LIGHT}"/></linearGradient>
  <linearGradient id="numFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{WHITE}"/><stop offset="1" stop-color="{BLUE_LIGHT}"/></linearGradient>
  <linearGradient id="numAmber" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{AMBER_HI}"/><stop offset="1" stop-color="{AMBER}"/></linearGradient>
  <linearGradient id="heroFill" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE_PALE}"/><stop offset="0.5" stop-color="{WHITE}"/><stop offset="1" stop-color="{BLUE_PALE}"/></linearGradient>
  <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{GLASS[0]}" stop-opacity="{GLASS[1]}"/><stop offset="1" stop-color="{GLASS[0]}" stop-opacity="{GLASS[2]}"/></linearGradient>
  <linearGradient id="planeB" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE_MID}" stop-opacity="0.22"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0.05"/></linearGradient>
  <linearGradient id="planeA" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{AMBER}" stop-opacity="0.28"/><stop offset="1" stop-color="{AMBER_DARK}" stop-opacity="0.06"/></linearGradient>
  <linearGradient id="barFill" x1="0" x2="1"><stop offset="0" stop-color="{BLUE_LIGHT}"/><stop offset="1" stop-color="{AMBER}"/></linearGradient>
  <linearGradient id="floorFade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="0.5"/></linearGradient>
  <mask id="floorMask"><rect x="0" y="430" width="{W}" height="{H - 430}" fill="url(#floorFade)"/></mask>
  <clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>
<style>
  text {{ font-family: {SANS}; }}
  .hero {{ font-size: 64px; font-weight: 800; letter-spacing: 20px; fill: url(#heroFill); }}
  .hero2 {{ font-size: 46px; font-weight: 800; letter-spacing: 16px; fill: url(#heroFill); }}
  .tagline {{ font-size: 21px; font-weight: 400; fill: {BLUE_PALE}; font-family: {MONO}; }}
  .kicker {{ font-size: 13px; letter-spacing: 3px; fill: {BLUE_LIGHT}; font-family: {MONO}; opacity: 0.8; }}
  .h1 {{ font-size: 46px; font-weight: 800; fill: {TXT_STRONG}; letter-spacing: -0.5px; }}
  .h2 {{ font-size: 36px; font-weight: 800; fill: {TXT_STRONG}; letter-spacing: -0.5px; }}
  .sub {{ font-size: 16px; fill: {TXT_SUB}; }}
  .tag {{ font-size: 13px; font-weight: 600; letter-spacing: 2.5px; fill: {AMBER}; font-family: {MONO}; }}
  .tagb {{ font-size: 13px; font-weight: 600; letter-spacing: 2.5px; fill: {BLUE_LIGHT}; font-family: {MONO}; }}
  .lab {{ font-size: 17px; font-weight: 650; fill: {SLATE_PALE}; }}
  .lab2 {{ font-size: 15px; font-weight: 650; fill: {SLATE_PALE}; }}
  .labs {{ font-size: 13.5px; fill: {TXT_SUB}; }}
  .num {{ font-size: 46px; font-weight: 800; fill: url(#numFill); letter-spacing: -1px; }}
  .nums {{ font-size: 40px; font-weight: 800; fill: url(#numFill); letter-spacing: -1px; }}
  .barv {{ font-size: 30px; font-weight: 800; fill: url(#numAmber); }}
  .barvs {{ font-size: 20px; font-weight: 700; fill: {BLUE_PALE}; }}
  .agent {{ font-size: 15px; font-weight: 600; fill: {SLATE_PALE}; font-family: {MONO}; }}
  .glyph {{ font-size: 26px; fill: {BLUE_PALE}; font-family: 'STIX Two Math', 'Cambria Math', serif; }}
  .cmd {{ font-size: 20px; fill: {SLATE_PALE}; font-family: {MONO}; }}
  .code {{ font-size: 14px; fill: {BLUE_LIGHT}; font-family: {MONO}; }}
  .codeok {{ font-size: 14px; fill: {TXT_OK}; font-family: {MONO}; }}
  .chip {{ font-size: 14px; font-weight: 600; fill: {BLUE_PALE}; font-family: {MONO}; }}
  .chipa {{ font-size: 14px; font-weight: 700; fill: {AMBER}; font-family: {MONO}; }}
  .hud {{ font-size: 14px; font-weight: 700; letter-spacing: 5px; fill: {SLATE_PALE}; }}
  .hudr {{ font-size: 12px; letter-spacing: 3px; fill: {BLUE_LIGHT}; font-family: {MONO}; opacity: 0.75; }}
  .chap {{ font-size: 12px; letter-spacing: 2px; fill: {BLUE_PALE}; font-family: {MONO}; }}
</style>
"""


def main():
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-labelledby="ttl desc">',
        '<title id="ttl">Humanfia — we build the flow around the agents</title>',
        '<desc id="desc">Animated portfolio: Humanize 2 agent flow system; HOA (IMO 2026 6/6, Lean-Eval #1, '
        'PutnamBench 670/672); KDA (1.39× past human SOTA, #1 SOLExec L1, 53 SOL Bench firsts, 6.5× MSA indexer); '
        'ProgramBench 3.5% with a builder-reviewer loop; HKA on 19 Kaggle competitions.</desc>',
        DEFS,
        '<g clip-path="url(#frame)">',
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        background(),
        scene_flow(), scene_hoa(), scene_kda(), scene_bars(),
        scene_intro(), scene_finale(),
        '<g id="particles">', particles_svg(), '</g>',
        f'<rect width="{W}" height="{H}" fill="url(#vign)" pointer-events="none"/>',
        hud(),
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="{BLUE_LIGHT}" stroke-opacity="0.18"/>',
        '</g></svg>',
    ]
    svg = "\n".join(body)
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "profile", f"humanfia-portfolio-{THEME}.svg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {os.path.normpath(out)}  ({len(svg) / 1024:.0f} KiB)")


if __name__ == "__main__":
    if "THEME" in os.environ:
        main()
    else:  # build both variants; each run re-seeds the RNG so the two stay frame-for-frame identical
        import subprocess
        import sys
        for theme in ("dark", "light"):
            subprocess.run([sys.executable, os.path.abspath(__file__)], env={**os.environ, "THEME": theme}, check=True)
