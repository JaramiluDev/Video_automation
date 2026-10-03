#!/usr/bin/env python3
"""
Módulo de Locución y Generación de Voz TTS (Narrator).

Lee un guion en formato YAML y genera el archivo de audio MP3
correspondiente utilizando edge-tts (o gTTS como respaldo).
"""

import argparse
import asyncio
import sys
from pathlib import Path
import yaml


async def generate_tts_edge(text: str, output_path: Path, voice: str = "es-MX-JorgeNeural") -> bool:
    """Genera audio a partir de texto utilizando edge-tts."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        print(f"✅ [Edge-TTS] Audio generado correctamente en: {output_path}")
        return True
    except Exception as e:
        print(f"⚠️ Error al usar edge-tts: {e}")
        return False


def generate_tts_gtts(text: str, output_path: Path, lang: str = "es") -> bool:
    """Genera audio a partir de texto utilizando gTTS (respaldo)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang)
        tts.save(str(output_path))
        print(f"✅ [gTTS] Audio generado correctamente en: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Error al usar gTTS: {e}")
        return False


def parse_yaml_text(yaml_path: Path) -> str:
    """Lee el archivo YAML del guion y extrae el texto consolidado de todas las escenas."""
    if not yaml_path.exists():
        print(f"❌ Archivo de guion no encontrado: {yaml_path}")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    paragraphs = []
    if isinstance(data, dict) and "scenes" in data:
        for scene in data["scenes"]:
            if isinstance(scene, dict) and "text" in scene and scene["text"]:
                paragraphs.append(str(scene["text"]).strip())
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "text" in item:
                paragraphs.append(str(item["text"]).strip())

    return " ".join(paragraphs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generador de Voz Narradora (TTS) desde Guion YAML"
    )
    parser.add_argument(
        "yaml_path",
        type=str,
        help="Ruta al archivo YAML del guion"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/outputs/audio_tts.mp3",
        help="Ruta del archivo MP3 de salida"
    )
    parser.add_argument(
        "--voice",
        "-v",
        type=str,
        default="es-MX-JorgeNeural",
        help="Voz TTS a utilizar"
    )

    args = parser.parse_args()

    yaml_file = Path(args.yaml_path)
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"🎙️ Leyendo guion desde: {yaml_file}")
    text_content = parse_yaml_text(yaml_file)

    if not text_content.strip():
        print("❌ El archivo YAML no contiene texto válido en las escenas.")
        sys.exit(1)

    print(f"📝 Texto a narrar ({len(text_content)} caracteres):\n\"{text_content[:150]}...\"")
    print("⏳ Generando audio de locución...")

    # Intentar primero con edge-tts (mejor calidad y velocidad)
    success = asyncio.run(generate_tts_edge(text_content, output_file, args.voice))

    # Si falla, intentar con gTTS como fallback
    if not success:
        print("🔄 Intentando fallback con gTTS...")
        success = generate_tts_gtts(text_content, output_file)

    if not success:
        print("❌ No se pudo generar el audio TTS con ninguna librería disponible.")
        sys.exit(1)

    print(f"🎉 Proceso de locución completado: {output_file}")


if __name__ == "__main__":
    main()