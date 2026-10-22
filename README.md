# Video Automation Pipeline 🎬📐
Automated Python pipeline to generate math videos for YouTube from YAML scripts and image sequences.

## Workflow (MVP)
1. Parses a YAML script (`examples/sample_script.yaml`).
2. Collects ordered images from scenes (e.g., `assets/source_scripts/GUION-03/`).
3. Assembles the final video using `moviepy` and `ffmpeg`.
4. *(Upcoming)* TTS generation, subtitles creation, and automatic YouTube upload.

## Render quality (fast / low-res / production)
All render commands accept `--fast` (480p, 15 fps, 2 threads, low priority),
`--low-res` (720p) or `--production` (script resolution, default). You can set
a default per machine with `VA_QUALITY=fast`. Details and benchmarks:
[docs/render-profiles.md](docs/render-profiles.md).

    python -m src.video_automation.cli render --script examples/video2_overlays.yaml --no-audio --fast
    python -m src.video_automation.cli profiles

## Dynamic math animations (Manim)
Parametrized Manim scenes built from a JSON/YAML file (no hardcoded content).
Videos are written to `data/renders/manim/`. Schema and options:
[docs/math-animator.md](docs/math-animator.md).

    python -m src.video_automation.math_animator --config data/scenes/sample_math.json --quality low
    python -m src.video_automation.math_animator --config data/scenes/sample_math.json --quality high

## Installations

### Windows
Make sure you have Python and FFmpeg installed. You can quickly install them via PowerShell using winget:
    
    winget install Python.Python.3.11
    winget install Gyan.FFmpeg

Before,Open a new terminal/powershell and configure the virtual environment:

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

### Arch Linux
```bash
sudo pacman -S --needed python python-pip python-virtualenv ffmpeg git
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

### Generación Base Visual (Zoom y Concatenación)
Para generar el video base con los efectos Ken Burns y unir todos los clips de una escena, ejecuta el orquestador apuntando a la carpeta del guion:

```bash
docker compose run --rm video-app python scripts/build_zoomed_video.py assets/source_scripts/GUION-02
cat << 'EOF' >> README.md

### Generación Base Visual (Zoom y Concatenación)
Para generar el video base con los efectos Ken Burns y unir todos los clips de una escena, ejecuta el orquestador apuntando a la carpeta del guion:

```bash
docker compose run --rm video-app python scripts/build_zoomed_video.py assets/source_scripts/GUION-02
mkdir -p .github/workflows
cat << 'EOF' > .github/workflows/ci.yml
name: CI Pipeline

on:
  pull_request:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Pytest
        run: |
          pytest tests/
