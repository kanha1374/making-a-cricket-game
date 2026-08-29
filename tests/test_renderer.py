from app.models import RenderConfig
from app.services.export import encode_png
from app.services.image_pipeline import generate_default_room
from app.services.renderer import render_scene
from PIL import Image


def test_render_is_deterministic(tmp_path):
    image_path = tmp_path / "default.png"
    generate_default_room(image_path, (800, 500))
    base = Image.open(image_path).convert("RGB")
    config = RenderConfig()

    img1 = render_scene(base, config)
    img2 = render_scene(base, config)

    assert encode_png(img1) == encode_png(img2)


def test_floor_shear_changes_output(tmp_path):
    image_path = tmp_path / "default.png"
    generate_default_room(image_path, (700, 420))
    base = Image.open(image_path).convert("RGB")

    img_a = render_scene(base, RenderConfig(floor_shear=0.0))
    img_b = render_scene(base, RenderConfig(floor_shear=0.3))

    assert encode_png(img_a) != encode_png(img_b)
