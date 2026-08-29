import io
import json

from app import create_app


def test_index_loads():
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Magical Math Editor" in response.data


def test_render_endpoint_returns_png():
    client = create_app().test_client()
    config = {
        "field_filter": "all",
        "xw_angle": 20,
        "yz_angle": 40,
        "density": 0.4,
        "stroke_thickness": 3,
        "glow_strength": 0.4,
        "floor_shear": 0.2,
        "domains_enabled": {"physics": True},
    }
    img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c```\xf8\x0f\x00\x01\x04\x01\x00\x18\xdd\x8d\x18\x00\x00\x00\x00IEND\xaeB`\x82"

    response = client.post(
        "/api/render",
        data={
            "config": json.dumps(config),
            "image": (io.BytesIO(img), "tiny.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_bad_config_returns_400():
    client = create_app().test_client()
    response = client.post("/api/render", data={"config": "not-json"})
    assert response.status_code == 400
