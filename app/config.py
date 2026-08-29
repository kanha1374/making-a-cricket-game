from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATE_DIR = BASE_DIR / "app" / "templates"
DEFAULT_IMAGE_PATH = STATIC_DIR / "default_room.png"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

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
