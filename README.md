# Video Automation Pipeline 🎬📐
Pipeline automatizado en Python para generar videos de matemáticas para YouTube a partir de guiones y secuencias de imágenes.

## Flujo de Trabajo (MVP)
1. Lee un guión en YAML (examples/sample_script.yaml).
2. Recolecta las imágenes ordenadas de las escenas (ej. assets/source_scripts/GUION-03/).
3. Ensambla el video final usando moviepy/ffmpeg.
4. (Futuro) Generación de TTS, subtítulos y subida automática a YouTube.

## Instalación en Arch Linux

sudo pacman -S --needed python python-pip python-virtualenv ffmpeg git
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

*Nota: Este repo es un prototipo MVP, la automatización completa aún está en desarrollo.*
