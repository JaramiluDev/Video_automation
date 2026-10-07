#!/usr/bin/env python3
"""
Orquestador Principal del Pipeline de Automatización de Video.
Soporta procesamiento completo E2E: Parseo -> TTS -> Ensamble Audiovisual -> Subida a YouTube.
"""

import argparse
import asyncio
import logging
from pathlib import Path
import sys
from typing import Optional

# Asegurar que 'src' esté en el PATH para importaciones relativas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from video_automation.narrator import generate_narration
from video_automation.script_parser import parse_script
from video_automation.youtube_uploader import YouTubeUploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta el pipeline completo de producción de video a partir de un guion YAML.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--script",
        type=Path,
        required=True,
        help="Ruta al archivo de guion YAML (ej. assets/source_scripts/GUION-02/GUION-02.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("data/output"),
        help="Directorio donde se guardarán los entregables generados",
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
    script_path: Path = args.script.resolve()
    if not script_path.is_file():
        logger.error(f"❌ El archivo de guion '{script_path}' no existe.")
        return 1

    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"🎬 Iniciando pipeline para: {script_path.name}")

    # 1. Parseo del Guion YAML
    logger.info("📄 [Paso 1/4] Parseando y validando guion YAML...")
    try:
        parsed_script = parse_script(script_path)
        title = getattr(parsed_script, "title", script_path.stem)
        description = getattr(parsed_script, "description", f"Video automatizado desde {script_path.name}")
        logger.info(f"✅ Guion validado: '{title}'")
    except Exception as e:
        logger.error(f"❌ Error al parsear el guion '{script_path}': {e}")
        return 1

    # 2. Generación de Narración (TTS)
    audio_output = output_dir / f"{script_path.stem}_audio.mp3"
    logger.info(f"🎙️ [Paso 2/4] Generando narración TTS con la voz '{args.voice}'...")
    try:
        full_text = " ".join(
            scene.narration for scene in parsed_script.scenes if getattr(scene, "narration", None)
        )
        if not full_text.strip():
            logger.warning("⚠️ No se encontró texto de narración en las escenas del guion.")
            full_text = title

        await generate_narration(text=full_text, output_path=audio_output, voice=args.voice)
        logger.info(f"✅ Audio generado en: {audio_output}")
    except Exception as e:
        logger.error(f"❌ Error en la generación de TTS: {e}")
        return 1

    # 3. Muxing / Ensamble Final
    final_video = output_dir / f"{script_path.stem}_final.mp4"
    logger.info(f"🎞️ [Paso 3/4] Ensamblando video final en: {final_video}")
    # Nota: Aquí se invoca el compositor o el script de muxing según la estructura del proyecto
    # Si la fuente base ya está en data/renders o assets, la tomamos de allí.
    try:
        # Fallback/Verificación si existe render base
        base_video_candidate = script_path.parent / f"{script_path.stem}_base.mp4"
        if not base_video_candidate.is_file():
            base_video_candidate = output_dir / f"{script_path.stem}_base.mp4"

        if base_video_candidate.is_file():
            import subprocess
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
                f"⚠️ No se encontró video base en '{base_video_candidate}'. "
                f"Se creó el paquete con la pista de audio lista en {audio_output}."
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