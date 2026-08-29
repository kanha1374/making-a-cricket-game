from __future__ import annotations

import json
from http import HTTPStatus
from time import perf_counter

from flask import Flask, Response, jsonify, render_template, request

from app.config import (
    DEFAULT_IMAGE_PATH,
    DOMAINS,
    FRAME_TIME_TARGET_MS,
    MAX_UPLOAD_BYTES,
    PRESET_PROFILES,
    TEMPLATE_DIR,
)
from app.models import RenderConfig
from app.services.export import encode_png, upscale_for_export
from app.services.image_pipeline import load_image_from_upload, normalize_base_image
from app.services.renderer import render_scene


def _bad_request(message: str, status: int = HTTPStatus.BAD_REQUEST) -> Response:
    response = jsonify({"error": message})
    response.status_code = int(status)
    return response


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder="static")

    @app.get("/")
    def index() -> str:
        return render_template("index.html", domains=DOMAINS, presets=sorted(PRESET_PROFILES.keys()))

    @app.get("/api/domains")
    def get_domains() -> Response:
        return jsonify({"domains": DOMAINS})

    @app.get("/api/presets")
    def get_presets() -> Response:
        return jsonify({"presets": PRESET_PROFILES})

    def _extract_payload() -> dict:
        payload_raw = request.form.get("config") or request.args.get("config")
        if not payload_raw:
            return {}
        try:
            payload = json.loads(payload_raw)
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except ValueError as exc:
            raise ValueError("Invalid config payload") from exc

    def _render(high_res: bool = False) -> Response:
        started = perf_counter()
        try:
            payload = _extract_payload()
            config = RenderConfig.from_payload(payload)
            base = load_image_from_upload(request.files.get("image"), DEFAULT_IMAGE_PATH, MAX_UPLOAD_BYTES)
            normalized = normalize_base_image(base)
            result = render_scene(normalized, config)
            if high_res:
                result = upscale_for_export(result, factor=2)
            body = encode_png(result)
            response = Response(body, mimetype="image/png")
            elapsed_ms = (perf_counter() - started) * 1000
            response.headers["X-Render-Time-Ms"] = f"{elapsed_ms:.2f}"
            response.headers["X-Frame-Target-Ms"] = f"{FRAME_TIME_TARGET_MS:.2f}"
            return response
        except ValueError:
            return _bad_request("Invalid input payload")
        except Exception:
            return _bad_request("Rendering failed", HTTPStatus.INTERNAL_SERVER_ERROR)

    @app.post("/api/render")
    def render_endpoint() -> Response:
        return _render(high_res=False)

    @app.post("/api/export")
    def export_endpoint() -> Response:
        return _render(high_res=True)

    return app
