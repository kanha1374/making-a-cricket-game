from __future__ import annotations

import json
from http import HTTPStatus

from flask import Flask, Response, jsonify, render_template, request

from app.config import DEFAULT_IMAGE_PATH, DOMAINS, TEMPLATE_DIR
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
        return render_template("index.html", domains=DOMAINS)

    @app.get("/api/domains")
    def get_domains() -> Response:
        return jsonify({"domains": DOMAINS})

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
        try:
            payload = _extract_payload()
            config = RenderConfig.from_payload(payload)
            base = load_image_from_upload(request.files.get("image"), DEFAULT_IMAGE_PATH)
            normalized = normalize_base_image(base)
            result = render_scene(normalized, config)
            if high_res:
                result = upscale_for_export(result, factor=2)
            body = encode_png(result)
            return Response(body, mimetype="image/png")
        except ValueError as exc:
            return _bad_request(str(exc))
        except Exception:
            return _bad_request("Rendering failed", HTTPStatus.INTERNAL_SERVER_ERROR)

    @app.post("/api/render")
    def render_endpoint() -> Response:
        return _render(high_res=False)

    @app.post("/api/export")
    def export_endpoint() -> Response:
        return _render(high_res=True)

    return app
