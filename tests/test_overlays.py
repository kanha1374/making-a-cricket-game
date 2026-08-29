from PIL import Image, ImageDraw

from app.models import RenderConfig
from app.services.overlays import draw_all_overlays


def test_overlay_draws_non_empty_pixels():
    img = Image.new("RGBA", (900, 560), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    draw_all_overlays(draw, 900, 560, RenderConfig())

    alpha = img.getchannel("A")
    assert alpha.getbbox() is not None


def test_filter_limits_domains():
    img1 = Image.new("RGBA", (720, 480), (0, 0, 0, 0))
    img2 = Image.new("RGBA", (720, 480), (0, 0, 0, 0))
    draw_all_overlays(ImageDraw.Draw(img1, "RGBA"), 720, 480, RenderConfig(field_filter="physics"))
    draw_all_overlays(ImageDraw.Draw(img2, "RGBA"), 720, 480, RenderConfig(field_filter="topology"))

    assert img1.tobytes() != img2.tobytes()
