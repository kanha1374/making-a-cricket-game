from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from PIL import ImageDraw

from app.models import RenderConfig

Color = tuple[int, int, int, int]


@dataclass
class OverlayContext:
    draw: ImageDraw.ImageDraw
    width: int
    height: int
    stroke: int
    jitter: float
    rng: random.Random


PALETTE: dict[str, Color] = {
    "higdimetry": (153, 255, 86, 220),
    "physics": (82, 255, 222, 220),
    "topology": (255, 99, 216, 220),
    "calculus": (180, 214, 255, 220),
    "algebra": (255, 184, 88, 220),
    "chaos": (255, 74, 74, 220),
    "number_theory": (130, 186, 255, 220),
    "probability": (87, 255, 158, 220),
}


def _seed(config: RenderConfig, domain: str, width: int, height: int) -> int:
    msg = (
        f"{domain}|{width}|{height}|{config.field_filter}|{config.xw_angle}|{config.yz_angle}|"
        f"{config.density}|{config.stroke_thickness}|{config.glow_strength}|{config.floor_shear}"
    )
    return int(hashlib.sha256(msg.encode("utf-8")).hexdigest()[:16], 16)


def _jitter(ctx: OverlayContext, x: float, y: float) -> tuple[float, float]:
    return (
        x + ctx.rng.uniform(-ctx.jitter, ctx.jitter),
        y + ctx.rng.uniform(-ctx.jitter, ctx.jitter),
    )


def _polyline(ctx: OverlayContext, points: list[tuple[float, float]], color: Color) -> None:
    warped = [_jitter(ctx, x, y) for x, y in points]
    if len(warped) > 1:
        ctx.draw.line(warped, fill=color, width=ctx.stroke, joint="curve")


def draw_higdimetry(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["higdimetry"]
    cx, cy = ctx.width * 0.5, ctx.height * 0.52
    size = min(ctx.width, ctx.height) * (0.16 + 0.12 * config.density)
    a = math.radians(config.xw_angle)
    b = math.radians(config.yz_angle)

    outer = [
        (cx - size, cy - size),
        (cx + size, cy - size),
        (cx + size, cy + size),
        (cx - size, cy + size),
        (cx - size, cy - size),
    ]

    offset = size * 0.45
    inner = []
    for x, y in outer:
        ix = x + offset * math.cos(a) - offset * math.sin(b)
        iy = y - offset * math.sin(a) * 0.5 + offset * math.cos(b) * 0.2
        inner.append((ix, iy))

    _polyline(ctx, outer, color)
    _polyline(ctx, inner, color)
    for p1, p2 in zip(outer[:-1], inner[:-1]):
        _polyline(ctx, [p1, p2], color)

    for i in range(1, 5):
        r = size * (0.25 + i * 0.12)
        bbox = [cx - r, cy - r * 0.5, cx + r, cy + r * 0.5]
        ctx.draw.arc(bbox, start=0, end=360, fill=(65, 255, 240, 110), width=max(1, ctx.stroke - 1))


def draw_physics(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["physics"]
    y = ctx.height * 0.33
    x1, x2 = ctx.width * 0.18, ctx.width * 0.42
    x3, x4 = ctx.width * 0.58, ctx.width * 0.82
    _polyline(ctx, [(x1, y), (ctx.width * 0.5, y + 30), (x4, y)], color)
    _polyline(ctx, [(x2, y + 90), (ctx.width * 0.5, y + 30), (x3, y + 90)], color)
    # photon spark
    for i in range(8):
        angle = i * (math.pi / 4)
        px = ctx.width * 0.5 + math.cos(angle) * 28
        py = y + 30 + math.sin(angle) * 28
        _polyline(ctx, [(ctx.width * 0.5, y + 30), (px, py)], (255, 240, 170, 220))


def draw_topology(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["topology"]
    cx, cy = ctx.width * 0.28, ctx.height * 0.66
    scale = min(ctx.width, ctx.height) * 0.1
    points = []
    for i in range(300):
        t = (2 * math.pi) * (i / 300)
        x = (2 + math.cos(3 * t)) * math.cos(2 * t)
        y = (2 + math.cos(3 * t)) * math.sin(2 * t)
        points.append((cx + x * scale * 0.55, cy + y * scale * 0.55))
    _polyline(ctx, points + [points[0]], color)


def draw_calculus(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["calculus"]
    expressions = [
        "d/dx (sin x) = cos x",
        "∫ e^(-x²) dx ≈ √π/2",
        "∇·E = ρ/ε₀",
    ]
    x, y = int(ctx.width * 0.56), int(ctx.height * 0.12)
    spacing = int(34 * (0.8 + config.density * 0.5))
    for idx, text in enumerate(expressions):
        ctx.draw.text((x, y + spacing * idx), text, fill=color)


def draw_algebra(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["algebra"]
    x0, y0 = int(ctx.width * 0.08), int(ctx.height * 0.12)
    cell = int(24 + 10 * config.density)
    rows, cols = 5, 5
    for r in range(rows + 1):
        _polyline(ctx, [(x0, y0 + r * cell), (x0 + cols * cell, y0 + r * cell)], color)
    for c in range(cols + 1):
        _polyline(ctx, [(x0 + c * cell, y0), (x0 + c * cell, y0 + rows * cell)], color)
    for r in range(rows):
        for c in range(cols):
            n = (r * cols + c + 1) % 10
            ctx.draw.text((x0 + c * cell + 7, y0 + r * cell + 5), str(n), fill=color)


def draw_chaos(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["chaos"]
    # Lorenz attractor projection
    sigma, beta, rho = 10.0, 8 / 3, 28.0
    x, y, z = 0.1, 0.0, 0.0
    pts = []
    for _ in range(int(1200 * (0.7 + config.density * 0.8))):
        dt = 0.01
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z
        x += dx * dt
        y += dy * dt
        z += dz * dt
        px = ctx.width * 0.74 + x * 5
        py = ctx.height * 0.68 + z * 2.3
        pts.append((px, py))
    _polyline(ctx, pts, color)

    # Double pendulum trace
    base_x, base_y = ctx.width * 0.45, ctx.height * 0.22
    l1, l2 = 70, 65
    th1, th2 = 1.1, 1.6
    path = []
    for _ in range(140):
        th1 += ctx.rng.uniform(-0.06, 0.06)
        th2 += ctx.rng.uniform(-0.09, 0.09)
        x1, y1 = base_x + l1 * math.sin(th1), base_y + l1 * math.cos(th1)
        x2, y2 = x1 + l2 * math.sin(th2), y1 + l2 * math.cos(th2)
        path.append((x2, y2))
    _polyline(ctx, [(base_x, base_y), path[0]], color)
    _polyline(ctx, path, (255, 170, 170, 180))


def draw_number_theory(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["number_theory"]
    x, y = int(ctx.width * 0.62), int(ctx.height * 0.43)
    ctx.draw.text((x, y), "π(x) ~ x / ln(x)", fill=color)
    ctx.draw.text((x, y + 28), "e^(iπ) + 1 = 0", fill=color)
    cx, cy = int(ctx.width * 0.86), int(ctx.height * 0.53)
    radius = int(min(ctx.width, ctx.height) * 0.12)
    for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]:
        ang = (p / 29) * (2 * math.pi)
        px = cx + radius * math.cos(ang)
        py = cy + radius * math.sin(ang)
        ctx.draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)


def draw_probability(ctx: OverlayContext, config: RenderConfig) -> None:
    color = PALETTE["probability"]
    x0 = ctx.width * 0.08
    y0 = ctx.height * 0.86
    width = ctx.width * 0.36
    points = []
    for i in range(140):
        t = i / 139
        x = x0 + t * width
        n = (t - 0.5) / 0.16
        y = y0 - math.exp(-(n * n) / 2) * 90
        points.append((x, y))
    _polyline(ctx, points, color)

    nodes = []
    for _ in range(12):
        nodes.append(
            (
                ctx.width * 0.48 + ctx.rng.uniform(0, ctx.width * 0.18),
                ctx.height * 0.72 + ctx.rng.uniform(-ctx.height * 0.12, ctx.height * 0.12),
            )
        )
    for i, n1 in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            n2 = nodes[j]
            if ctx.rng.random() < 0.18:
                _polyline(ctx, [n1, n2], (70, 255, 170, 110))
    for x, y in nodes:
        ctx.draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color)


DOMAIN_DRAWERS = {
    "higdimetry": draw_higdimetry,
    "physics": draw_physics,
    "topology": draw_topology,
    "calculus": draw_calculus,
    "algebra": draw_algebra,
    "chaos": draw_chaos,
    "number_theory": draw_number_theory,
    "probability": draw_probability,
}


def draw_all_overlays(draw: ImageDraw.ImageDraw, width: int, height: int, config: RenderConfig) -> None:
    active = config.active_domains()
    for domain in active:
        drawer = DOMAIN_DRAWERS.get(domain)
        if not drawer:
            continue
        ctx = OverlayContext(
            draw=draw,
            width=width,
            height=height,
            stroke=config.stroke_thickness,
            jitter=0.5 + config.density * 1.3,
            rng=random.Random(_seed(config, domain, width, height)),
        )
        drawer(ctx, config)
