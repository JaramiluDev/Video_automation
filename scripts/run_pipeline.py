#!/usr/bin/env python3
"""
Orquestador Principal del Pipeline de Automatización de Video (Dinamico).
Soporta procesamiento completo E2E resolviendo rutas por convención a partir del ID del guion.
"""

import argparse
import asyncio
import logging
from pathlib import Path
import sys
import subprocess

# Asegurar que 'src' esté en el PATH para importaciones relativas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from video_automation.script_parser import parse_script
from video_automation.youtube_uploader import YouTubeUploader
from video_automation.narrator import generate_script_audio, generate_tts_edge, parse_yaml_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta el pipeline E2E dinámicamente a partir de un nombre o ruta de guion YAML.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--script",
        type=str,
        required=True,
        help="Nombre del guion (ej. GUION-02) o ruta relativa al archivo YAML.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("data/output"),
        help="Directorio base donde se guardarán los entregables generados",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="es-MX-DaliaNeural",
        help="Voz de Edge-TTS a utilizar para la narración",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Si se activa, el video renderizado se subirá automáticamente a YouTube",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        choices=["private", "unlisted", "public"],
        default="private",
        help="Estado de privacidad para la subida a YouTube",
    )
    parser.add_argument(
        "--thumbnail",
        type=Path,
        default=None,
        help="Ruta a una miniatura personalizada (opcional)",
    )
    return parser.parse_args()


async def run_pipeline_async(args: argparse.Namespace) -> int:
    input_arg = args.script.strip()
    
    # --- RESOLUCIÓN INTELIGENTE POR CONVENCIÓN ---
    if input_arg.endswith(".yaml"):
        script_path = Path(input_arg)
    else:
        script_path = Path("assets/source_scripts") / input_arg / f"{input_arg}.yaml"

    script_path = script_path.resolve()

    if not script_path.is_file():
        logger.error(f"❌ No se encontró el archivo de guion en: {script_path}")
        return 1

    episode_slug = script_path.stem
    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"🎬 Iniciando pipeline dinámico para: {episode_slug}")
    logger.info(f"📂 Guion localizado en: {script_path}")

    # 1. Parseo del Guion YAML (Pasando la ruta absoluta como string)
    logger.info("📄 [Paso 1/4] Parseando y validando guion YAML...")
    try:
        parsed_script = parse_script(str(script_path))
        title = getattr(parsed_script, "title", episode_slug)
        description = getattr(parsed_script, "description", f"Video automatizado del episodio {episode_slug}")
        logger.info(f"✅ Guion validado: '{title}'")
    except Exception as e:
        logger.error(f"❌ Error al parsear el guion '{script_path}': {e}")
        return 1

    # 2. Generación de Narración (TTS Multi-Voz por Escena y Diálogo)
    audio_output = output_dir / f"{episode_slug}_audio.mp3"
    logger.info(f"🎙️ [Paso 2/4] Generando narración TTS multi-voz escena por escena...")
    try:
        success = await generate_script_audio(
            yaml_path=script_path,
            output_path=audio_output,
            default_voice=args.voice,
        )
        if not success:
            raise RuntimeError("Falló la generación de audio multi-voz.")
            
        logger.info(f"✅ Audio generado en: {audio_output}")
    except Exception as e:
        logger.error(f"❌ Error en la generación de TTS: {e}")
        return 1

    # 3. Muxing / Ensamble Final
    final_video = output_dir / f"{episode_slug}_final.mp4"
    logger.info(f"🎞️ [Paso 3/4] Ensamblando video final en: {final_video}")
    
    try:
        candidates = [
            script_path.parent / "manim_overlay.mp4",
            script_path.parent / f"{episode_slug}_base.mp4",
            output_dir / f"{episode_slug}_base.mp4"
        ]
        
        base_video_candidate = next((c for c in candidates if c.is_file()), None)

        if base_video_candidate:
            logger.info(f"🔍 Video base localizado en: {base_video_candidate}")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(base_video_candidate),
                "-i", str(audio_output),
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(final_video)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            logger.info("✅ Ensamble con FFmpeg completado con éxito.")
        else:
            logger.warning(
                f"⚠️ No se encontró video base. Se empaquetará únicamente la pista de audio en {audio_output}."
            )
            final_video = audio_output
            
    except Exception as e:
        logger.error(f"❌ Error durante el ensamble del video: {e}")
        return 1

    # 4. Subida Opcional a YouTube
    if args.upload:
        logger.info("🚀 [Paso 4/4] Publicando video en YouTube...")
        if not final_video.suffix == ".mp4":
            logger.error("❌ Se requiere un archivo .mp4 válido para subir a YouTube.")
            return 1

        try:
            uploader = YouTubeUploader(auto_authenticate=True)
            uploader.upload_video(
                title=title,
                description=description,
                file_path=final_video,
                thumbnail_path=args.thumbnail,
                privacy_status=args.privacy,
            )
            logger.info("🎉 ¡Proceso de subida a YouTube finalizado!")
        except Exception as e:
            logger.error(f"❌ Error durante la subida a YouTube: {e}")
            return 1
    else:
        logger.info("ℹ️ [Paso 4/4] Subida a YouTube omitida (usa --upload para activar).")

    logger.info("✨ ¡Pipeline completado exitosamente!")
    return 0


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(run_pipeline_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()