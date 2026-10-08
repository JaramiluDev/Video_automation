# Video Automation Pipeline 🎬📐
Automated Python pipeline to generate math videos for YouTube from YAML scripts and image sequences.

## Workflow (MVP)
1. Parses a YAML script (`examples/sample_script.yaml`).
2. Collects ordered images from scenes (e.g., `assets/source_scripts/GUION-03/`).
3. Assembles the final video using `moviepy` and `ffmpeg`.
4. *(Upcoming)* TTS generation, subtitles creation, and automatic YouTube upload.

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

## Google Sheets ingestion & TTS (new)

This project now supports importing scripts directly from Google Sheets and
extracting word-level timestamps from `edge-tts` for precise subtitle alignment.

### Install optional dependencies

```bash
pip install --upgrade edge-tts pyttsx3 google-api-python-client google-auth
```

### Fetch a script from Google Sheets

Make sure you share the sheet with a service account (or configure ADC), then:

```bash
python scripts/fetch_sheet_script.py --sheet-id <SHEET_ID> --episode 3 --credentials path/to/service-account.json
```

- Output YAML is saved to `assets/source_scripts/GUION-03/GUION-03.yaml`.
- Expected columns (case-insensitive): `Escena`, `Narracion`, `TipoVisual`, `Recurso`, `DuracionEstimada`.

### Run the renderer and get word-aligned subtitles

```bash
python -m src.video_automation.cli render --script assets/source_scripts/GUION-03/GUION-03.yaml --output output/ --fps 24
```

This will produce per-scene audio and SRT files under `output/audio/` and a combined
SRT in `output/subtitles/`.

If you want a single combined audio file and remapped timestamps, I can add
that as an option — ask and I'll implement it.
