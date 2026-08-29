from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from app.models import RenderConfig
from app.services.overlays import draw_all_overlays


def _overlay_surface_size(base: Image.Image) -> tuple[int, int]:
    return base.width, base.height


def _apply_floor_perspective(overlay: Image.Image, shear: float) -> Image.Image:
    width, height = overlay.size
    y_anchor = int(height * 0.62)
    transformed = overlay.transform(
        overlay.size,
        Image.Transform.AFFINE,
        (1, shear, -shear * y_anchor, 0, 1, 0),
        resample=Image.Resampling.BICUBIC,
    )
    return transformed


def render_scene(base_image: Image.Image, config: RenderConfig) -> Image.Image:
    base = base_image.convert("RGBA")
    width, height = _overlay_surface_size(base)

    # Draw overlays into floor-focused layer for scene-consistent placement.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw_all_overlays(draw, width, height, config)

    projected = _apply_floor_perspective(overlay, config.floor_shear)

    # Glow pass
    glow_radius = int(2 + config.glow_strength * 10)
    glow_layer = projected.filter(ImageFilter.GaussianBlur(glow_radius))
    glow_alpha = int(90 + config.glow_strength * 110)
    glow_layer.putalpha(glow_alpha)

    composed = Image.alpha_composite(base, glow_layer)
    composed = Image.alpha_composite(composed, projected)

    # Subtle neon grading
    grade = Image.new("RGBA", (width, height), (15, 20, 40, 20))
    composed = ImageChops.add(composed, grade)

    return composed.convert("RGB")
