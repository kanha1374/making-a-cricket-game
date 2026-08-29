# Magical Math Cricket Lab Editor

Python-first interactive web editor that overlays futuristic mathematical graphics on room images.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open `http://localhost:8000`.

## Features

- Image upload + generated default room
- Real-time mathematical overlays with domain filtering/toggles
- Hypercube angle, density, stroke, glow, floor-shear controls
- Perspective projection + glow compositing + deterministic render path
- High-resolution export endpoint
- Automated tests for API and deterministic rendering

## Test

```bash
pytest -q
```
