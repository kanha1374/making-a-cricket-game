from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw


def generate_default_room(path: Path, size: tuple[int, int] = (1280, 720)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    img = Image.new("RGB", size, "#080b16")
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(8 + 16 * t)
        g = int(11 + 26 * t)
        b = int(22 + 38 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    draw.polygon(
        [
            (0, int(height * 0.62)),
            (width, int(height * 0.62)),
            (width, height),
            (0, height),
        ],
        fill=(20, 26, 40),
    )
    img.save(path, format="PNG")


def load_image_from_upload(file_storage, fallback_path: Path, max_upload_bytes: int) -> Image.Image:
    if file_storage and file_storage.filename:
        data = file_storage.read()
        if not data:
            raise ValueError("Uploaded file is empty")
        if len(data) > max_upload_bytes:
            raise ValueError("Uploaded image is too large")
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return image

    if not fallback_path.exists():
        generate_default_room(fallback_path)

    return Image.open(fallback_path).convert("RGB")


def normalize_base_image(image: Image.Image, max_size: tuple[int, int] = (1600, 1000)) -> Image.Image:
    image = image.copy()
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image
