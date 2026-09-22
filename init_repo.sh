#!/bin/bash

echo "Creando estructura de directorios..."
mkdir -p config data/{scripts,assets,audio,subtitles,renders,thumbnails} src/video_automation tests docs examples scripts

echo "Creando archivos de configuración..."

cat << 'EOF' > README.md
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
EOF

cat << 'EOF' > .gitignore
.venv/
.env
__pycache__/
*.pyc
data/audio/*
data/renders/*
data/subtitles/*
data/thumbnails/*
!data/**/.gitkeep
EOF

touch data/scripts/.gitkeep data/assets/.gitkeep data/audio/.gitkeep data/subtitles/.gitkeep data/renders/.gitkeep data/thumbnails/.gitkeep

cat << 'EOF' > .env.example
YOUTUBE_CLIENT_ID=tu_client_id_aqui
YOUTUBE_CLIENT_SECRET=tu_client_secret_aqui
YOUTUBE_REFRESH_TOKEN=tu_token_aqui
TTS_API_KEY=tu_api_key_aqui
DEFAULT_LANGUAGE=es-MX
EOF

cat << 'EOF' > requirements.txt
python-dotenv>=1.0.0
pydantic>=2.4.2
PyYAML>=6.0.1
pytest>=7.4.2
requests>=2.31.0
moviepy>=1.0.3
ffmpeg-python>=0.2.0
python-docx>=1.0.1
Pillow>=10.0.1
EOF

cat << 'EOF' > pyproject.toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "video_automation"
version = "0.1.0"
description = "Pipeline para automatización de videos de matemáticas"
authors = [{name = "JaramiluDev Team"}]
dependencies = [
    "pydantic",
    "PyYAML",
    "moviepy"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF

cat << 'EOF' > config/settings.example.yaml
default_language: "es"
output_resolution: [1920, 1080]
output_fps: 30
default_music_volume: 0.1
default_subtitle_font: "Arial"
output_directory: "data/renders"
allowed_scene_folders:
  - "assets/source_scripts"
EOF

echo "Creando código fuente MVP en src/video_automation/..."

touch src/video_automation/__init__.py

cat << 'EOF' > src/video_automation/models.py
from pydantic import BaseModel
from typing import List, Optional

class Scene(BaseModel):
    id: str
    title: str
    narration: str
    image_paths: List[str]
    duration: float
    voice: Optional[str] = "default"
    text_on_screen: Optional[str] = ""
    transitions: Optional[str] = "fade"

class ScriptDefinition(BaseModel):
    title: str
    scenes: List[Scene]
    output_filename: str

class OutputSettings(BaseModel):
    resolution: tuple = (1920, 1080)
    fps: int = 30
EOF

cat << 'EOF' > src/video_automation/script_parser.py
import yaml
from pathlib import Path
from .models import ScriptDefinition

def parse_script(file_path: str) -> ScriptDefinition:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return ScriptDefinition(**data)
EOF

cat << 'EOF' > src/video_automation/compositor.py
import os
from moviepy.editor import ImageClip, concatenate_videoclips

def compose_video(image_paths: list, durations: list, output_path: str):
    print(f"Ensamblando video con {len(image_paths)} imágenes...")
    clips = []
    for img, dur in zip(image_paths, durations):
        if os.path.exists(img):
            clip = ImageClip(img).set_duration(dur)
            clips.append(clip)
        else:
            print(f"Advertencia: No se encontró la imagen {img}")
    
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_path, fps=30)
EOF

cat << 'EOF' > src/video_automation/pipeline.py
from pathlib import Path
from .script_parser import parse_script
from .compositor import compose_video

def run_pipeline(script_path: str, output_dir: str) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)
    
    all_images = []
    all_durations = []
    
    for scene in script.scenes:
        for img in scene.image_paths:
            all_images.append(img)
            all_durations.append(scene.duration / len(scene.image_paths))
            
    output_file = Path(output_dir) / script.output_filename
    compose_video(all_images, all_durations, str(output_file))
    print(f"Pipeline completado. Video guardado en: {output_file}")
    return str(output_file)
EOF

cat << 'EOF' > src/video_automation/cli.py
import argparse
from .pipeline import run_pipeline
from .script_parser import parse_script

def main():
    parser = argparse.ArgumentParser(description="Video Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    val_parser = subparsers.add_parser("validate", help="Valida el formato del guión YAML")
    val_parser.add_argument("--script", required=True, help="Ruta al script YAML")

    ren_parser = subparsers.add_parser("render", help="Renderiza el video")
    ren_parser.add_argument("--script", required=True, help="Ruta al script YAML")
    ren_parser.add_argument("--output", default="data/renders", help="Directorio de salida")

    args = parser.parse_args()

    if args.command == "validate":
        try:
            script = parse_script(args.script)
            print(f"✅ Guión '{script.title}' validado correctamente con {len(script.scenes)} escenas.")
        except Exception as e:
            print(f"❌ Error al validar: {e}")
    elif args.command == "render":
        run_pipeline(args.script, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
EOF

cat << 'EOF' > src/video_automation/main.py
from video_automation.cli import main

if __name__ == "__main__":
    main()
EOF

touch src/video_automation/{config,scene_builder,narrator,subtitles,youtube_uploader}.py

echo "Creando tests y documentación..."

cat << 'EOF' > tests/test_script_parser.py
import pytest
from video_automation.script_parser import parse_script

def test_parse_valid_script(tmp_path):
    assert True
EOF

touch tests/test_pipeline.py
touch docs/{architecture,script-format,setup}.md

cat << 'EOF' > examples/sample_script.yaml
title: "Resolviendo la Ecuación Cuadrática"
output_filename: "ecuacion_cuadratica_mvp.mp4"
scenes:
  - id: "ESCENA-01"
    title: "Introducción"
    narration: "Bienvenidos. Hoy buscaremos a la X usando la fórmula general."
    image_paths: 
      - "data/assets/placeholder_1.png"
    duration: 3.0
    text_on_screen: "Buscando a la X"
EOF

cat << 'EOF' > scripts/render_sample.sh
#!/bin/bash
if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
echo "Generando imagen de prueba temporal..."
python -c "from PIL import Image; Image.new('RGB', (1920, 1080), color = 'blue').save('data/assets/placeholder_1.png')"
echo "Corriendo renderizado..."
python -m src.video_automation.cli render --script examples/sample_script.yaml
EOF
chmod +x scripts/render_sample.sh

echo "¡Estructura MVP generada con éxito, mi buen! Échale un ojo con 'tree'."
