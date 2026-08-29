from __future__ import annotations

import io

from PIL import Image


def encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def upscale_for_export(image: Image.Image, factor: int = 2) -> Image.Image:
    if factor <= 1:
        return image
    return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
