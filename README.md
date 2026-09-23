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
