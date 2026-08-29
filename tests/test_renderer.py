from app.models import RenderConfig
from app.services.export import encode_png
from app.services.image_pipeline import generate_default_room, load_image_from_upload
from app.services.renderer import render_scene
from PIL import Image


class _Upload:
    def __init__(self, data: bytes, filename: str = "x.png"):
        self._data = data
        self.filename = filename

    def read(self):
        return self._data


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


def test_upload_size_limit_enforced(tmp_path):
    fallback = tmp_path / "fallback.png"
    generate_default_room(fallback, (400, 240))
    upload = _Upload(b"x" * 20, "x.png")
    try:
        load_image_from_upload(upload, fallback, max_upload_bytes=10)
        assert False
    except ValueError:
        assert True
