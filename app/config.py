from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATE_DIR = BASE_DIR / "app" / "templates"
DEFAULT_IMAGE_PATH = STATIC_DIR / "default_room.png"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
FRAME_TIME_TARGET_MS = 33.0

DOMAINS = [
    "higdimetry",
    "physics",
    "topology",
    "calculus",
    "algebra",
    "chaos",
    "number_theory",
    "probability",
]

PRESET_PROFILES = {
    "standard": {
        "density": 0.5,
        "stroke_thickness": 2,
        "glow_strength": 0.45,
        "floor_shear": 0.18,
    },
    "maximum": {
        "density": 0.9,
        "stroke_thickness": 4,
        "glow_strength": 0.8,
        "floor_shear": 0.22,
    },
    "draft": {
        "density": 0.3,
        "stroke_thickness": 1,
        "glow_strength": 0.25,
        "floor_shear": 0.12,
    },
}
