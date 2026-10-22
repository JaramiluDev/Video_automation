#!/usr/bin/env python3
"""
Script parser para agrupar por escena y diálogo los guiones del Video Automation Pipeline.

Busca específicamente las 12 escenas principales y las líneas que empiezan con
los nombres de los personajes (DETECTIVE:, AGENTE CERO:, ANA:) dentro de cada escena,
generando un archivo YAML estructurado listo para la síntesis de audio TTS multi-voz.

Ejemplo de uso:
  python3 script_parser.py --input assets/source_scripts/Guion_visual_12_escenas_36_imagenes_DIALOGOS.docx --output assets/source_scripts/GUION-02.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

# Auto-detectar .venv si el entorno actual carece de dependencias (p. ej. pydantic o docx)
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and sys.executable != str(VENV_PYTHON):
    try:
        import pydantic  # noqa: F401
    except ImportError:
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

SRC_DIR = PROJECT_ROOT / "src"
for p in [str(PROJECT_ROOT), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from video_automation.models import ScriptDefinition
from video_automation.script_parser import (
    IndentedDumper,
    docx_to_yaml_data,
    extract_docx_scenes,
    iter_document_texts,
    parse_script,
)

# Mapeo oficial de personajes a modelos de voz
VOICE_MAPPING = {
    "DETECTIVE": {"character": "Detective", "voice_model": "DrSimi"},
    "AGENTE CERO": {"character": "AgenteCero", "voice_model": "PersonajeVaronil2"},
    "ANA": {"character": "Ana", "voice_model": "PersonajeFemenino"},
}


def resolve_input_path(raw_path: str | Path) -> Path:
    """Busca el archivo de entrada resolviendo rutas relativas y ubicaciones conocidas."""
    target = Path(raw_path)
    if target.exists():
        return target.resolve()

    candidates = [
        PROJECT_ROOT / target,
        PROJECT_ROOT / "assets" / "source_scripts" / target.name,
        PROJECT_ROOT / "assets" / "source_scripts" / "GUION-02" / target.name,
        Path.home() / "Downloads" / target.name,
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            print(f"ℹ️ Archivo de entrada localizado en: {candidate}")
            return candidate.resolve()

    raise FileNotFoundError(
        f"❌ Error: No se encontró el archivo de entrada '{raw_path}'."
    )


def parse_docx_dialogues(
    docx_path: str | Path,
    voice_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Función de lectura que busca específicamente el inicio de las 12 escenas
    y los diálogos de DETECTIVE, AGENTE CERO y ANA.
    """
    mapping = voice_mapping or VOICE_MAPPING
    scenes: List[Dict[str, Any]] = []
    current_scene: Optional[Dict[str, Any]] = None
    scene_counter = 0
    scene_dialogues: List[Dict[str, str]] = []

    for text in iter_document_texts(docx_path):
        if not text:
            continue

        # Detectar el inicio de una de las 12 escenas principales
        if text.startswith("Escena ") and "." in text[:12]:
            if current_scene:
                scenes.append(current_scene)

            scene_counter += 1
            scene_dialogues = []

            # Asegúrate de que cada escena devuelva tanto el texto unificado como los diálogos multivoz:
            current_scene = {
                "id": f"escena_{scene_counter:02d}",
                "title": text,
                "narration": " ".join([d["text"] for d in scene_dialogues]), # Satisface al narrador base
                "dialogue": scene_dialogues                                  # Alimenta los modelos de Applio
            }
            continue

        # Detectar quién habla
        for prefix, info in mapping.items():
            if text.startswith(prefix + ":") or text.startswith(prefix + " :"):
                dialogue_text = text.split(":", 1)[1].strip()
                if current_scene is not None:
                    scene_dialogues.append(
                        {
                            "character": info["character"],
                            "voice_model": info["voice_model"],
                            "text": dialogue_text,
                        }
                    )
                    current_scene["narration"] = " ".join([d["text"] for d in scene_dialogues])
                break

    if current_scene:
        scenes.append(current_scene)

    return scenes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Script Parser por Escena y Diálogo (Video Automation)"
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_file",
        type=str,
        default="assets/source_scripts/Guion_visual_12_escenas_36_imagenes_DIALOGOS.docx",
        help="Ruta al archivo DOCX o YAML de entrada",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        type=str,
        default="assets/source_scripts/GUION-02.yaml",
        help="Ruta al archivo YAML de salida",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = resolve_input_path(args.input_file)
    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()

    if suffix == ".docx":
        print(f"📄 Procesando guión por escenas y diálogos: {input_path}")
        scenes = parse_docx_dialogues(input_path, voice_mapping=VOICE_MAPPING)

        # Guardar el YAML limpio con la estructura correcta para el pipeline
        yaml_content = {"scenes": scenes}
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                yaml_content,
                f,
                Dumper=IndentedDumper,
                allow_unicode=True,
                sort_keys=False,
            )

        print("=" * 65)
        print("✅ ¡Guion procesado y estructurado correctamente!")
        print(f"🎬 Total escenas identificadas: {len(scenes)}")
        total_dialogues = sum(len(s.get("dialogue", s.get("dialogues", []))) for s in scenes)
        print(f"💬 Total diálogos extraídos   : {total_dialogues}")
        for idx, sc in enumerate(scenes, 1):
            dialogue_count = len(sc.get("dialogue", sc.get("dialogues", [])))
            print(f"   {idx}. {sc['title']} -> {dialogue_count} diálogos")
        print(f"📂 Archivo YAML generado      : {output_path}")
        print("=" * 65)

    elif suffix in (".yaml", ".yml"):
        print(f"🔍 Validando guión YAML: {input_path}")
        script_def = parse_script(str(input_path))
        print(f"✅ Guión '{script_def.title}' válido con {len(script_def.scenes)} escenas.")


if __name__ == "__main__":
    main()
