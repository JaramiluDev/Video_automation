#!/usr/bin/env python3
"""
Orquestador del pipeline de Video Automation.

Dos entradas:

- Librería (la usa `cli render`): run_pipeline() / parse_resolution().
- E2E por episodio (`python scripts/run_pipeline.py -s GUION-02` o
  `python -m src.video_automation.pipeline -s GUION-02`):
    1. parsea el guion,
    2. genera el audio multi-voz por escena (narrator.py),
    3. arma el VIDEO BASE SINCRONIZADO con ese audio (heavy_render.py, HG):
       cada escena dura lo que su <id>_consolidated.mp3 y el total empata
       con <guion>_audio.mp3 cuadro a cuadro,
    4. une video + audio y opcionalmente sube a YouTube.

Antes el paso 3 tomaba un video base fijo (manim_overlay.mp4 o 36 imágenes
× 5 s = 3:00) y `ffmpeg -shortest` cortaba el episodio de ~21 min en 3 min.
"""

import argparse
import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, Union

# Permite ejecutar este archivo directamente (python src/video_automation/pipeline.py).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "video_automation"

from .script_parser import parse_script
from .heavy_render import (
    AudioSyncError,
    default_dialogues_dir,
    default_images_root,
    fmt_hms,
    probe_duration,
    render_audio_synced_base,
    render_video,
)
from .narrator import TTSNarrator
from .render_profiles import (
    RenderProfile,
    add_quality_arguments,
    ensure_utf8_stdio,
    get_profile,
    profile_from_args,
)

logger = logging.getLogger("run_pipeline")


# ---------------------------------------------------------------------------
# Librería (cli render)
# ---------------------------------------------------------------------------

def parse_resolution(value: Union[str, Tuple[int, int], None]) -> Optional[Tuple[int, int]]:
    """'1280x720' → (1280, 720). None/'' → None (se usa la del guion)."""
    if value is None or value == "":
        return None
    if isinstance(value, (tuple, list)):
        return int(value[0]), int(value[1])
    try:
        w, h = str(value).lower().replace("×", "x").split("x")
        res = int(w), int(h)
    except ValueError:
        raise ValueError(f"Resolución inválida {value!r}; usa ANCHOxALTO, p. ej. 1280x720")
    if res[0] <= 0 or res[1] <= 0:
        raise ValueError(f"Resolución inválida {value!r}")
    return res


def run_pipeline(script_path: str, output_dir: str, fps: Optional[int] = None,
                 resolution: Union[str, Tuple[int, int], None] = None, include_audio: bool = True,
                 profile: Union[RenderProfile, str, None] = None, use_cache: bool = True) -> str:
    """
    fps / resolution: si se dan, sobrescriben output_settings del guion.
    profile: perfil de calidad (objeto o nombre: fast | low-res | production).
    """
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)
    if not isinstance(profile, RenderProfile):
        profile = get_profile(profile)
    profile.apply_process_limits()

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    narrative_audio = []

    if include_audio:
        for i, scene in enumerate(script.scenes):
            if (scene.narration or "").strip():
                sid = scene.id or f"escena_{i + 1:02d}"
                audio_output = output_root / "audio" / f"{sid}.wav"
                audio_output.parent.mkdir(parents=True, exist_ok=True)
                narration_result = TTSNarrator().generate_audio(scene.narration, str(audio_output))
                narrative_audio.append({
                    "scene_id": sid,
                    "audio_path": narration_result["audio_path"],
                    "duration": narration_result["duration"],
                })
        if narrative_audio:
            print(f"Audio generado para {len(narrative_audio)} escenas. Carpeta: {output_root / 'audio'}")

    output_file = render_video(script, output_dir, profile=profile,
                               resolution=parse_resolution(resolution), fps=fps,
                               use_cache=use_cache)

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return output_file


# ---------------------------------------------------------------------------
# E2E por episodio
# ---------------------------------------------------------------------------

def resolve_script_path(value: str, base: Path = Path("assets/source_scripts")) -> Path:
    """
    'GUION-02' → el YAML del episodio. Prioridad:
      1. assets/source_scripts/GUION-02.yaml          (guion multi-voz con `dialogue`)
      2. assets/source_scripts/GUION-02/GUION-02.yaml (conversión antigua del .docx)
    Una ruta que termina en .yaml se usa tal cual.
    """
    value = value.strip()
    if value.endswith((".yaml", ".yml")):
        return Path(value).resolve()
    candidates = [base / f"{value}.yaml", base / value / f"{value}.yaml"]
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return candidates[0].resolve()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta el pipeline E2E dinámicamente a partir de un nombre o ruta de guion YAML.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-s", "--script", type=str, required=True,
                        help="Nombre del guion (ej. GUION-02) o ruta relativa al archivo YAML.")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("data/output"),
                        help="Directorio base donde se guardarán los entregables generados")
    parser.add_argument("--voice", type=str, default="es-MX-DaliaNeural",
                        help="Voz de Edge-TTS a utilizar para la narración")
    parser.add_argument("--reuse-audio", action="store_true",
                        help="No regenera el TTS si ya existen <guion>_audio.mp3 y sus *_consolidated.mp3")
    parser.add_argument("--images-root", type=Path, default=None,
                        help="Carpeta con ESCENA-NN/ (por defecto assets/source_scripts/<guion>/)")
    parser.add_argument("--no-sync-base", action="store_true",
                        help="No arma el video base sincronizado; usa manim_overlay.mp4/<guion>_base.mp4 como antes")
    parser.add_argument("--static", action="store_true",
                        help="Video base con imágenes fijas (sin Ken Burns)")
    parser.add_argument("--cut-mode", choices=["turns", "equal"], default="turns",
                        help="Cortes de imagen: en los cambios de turno de diálogo o en partes iguales")
    parser.add_argument("--jobs", type=int, default=None,
                        help="Clips del video base en paralelo (por defecto $VA_JOBS o según el perfil)")
    parser.add_argument("--upload", action="store_true",
                        help="Si se activa, el video renderizado se subirá automáticamente a YouTube")
    parser.add_argument("--privacy", type=str, choices=["private", "unlisted", "public"],
                        default="private", help="Estado de privacidad para la subida a YouTube")
    parser.add_argument("--thumbnail", type=Path, default=None,
                        help="Ruta a una miniatura personalizada (opcional)")
    add_quality_arguments(parser)
    return parser.parse_args(argv)


def _audio_ready(audio_output: Path, parsed_script) -> bool:
    if not audio_output.is_file() or audio_output.stat().st_size == 0:
        return False
    dialogues = default_dialogues_dir(audio_output)
    for i, scene in enumerate(parsed_script.scenes):
        sid = scene.id or f"escena_{i + 1:02d}"
        if not any(dialogues.rglob(f"{sid}_consolidated.*")):
            return False
    return True


def build_synced_base(parsed_script, script_path: Path, audio_output: Path, output_dir: Path,
                      profile: RenderProfile, images_root: Optional[Path] = None,
                      ken_burns: bool = True, cut_mode: str = "turns",
                      jobs: Optional[int] = None) -> Path:
    """Paso 3 (HG): video base que dura exactamente lo que el audio multi-voz."""
    images_root = images_root or default_images_root(script_path)
    return render_audio_synced_base(
        parsed_script,
        output_dir / f"{script_path.stem}_base.mp4",
        episode_audio=audio_output,
        dialogues_dir=default_dialogues_dir(audio_output),
        images_root=images_root,
        profile=profile,
        ken_burns=ken_burns,
        cut_mode=cut_mode,
        strict=True,
        jobs=jobs,
    )


async def run_pipeline_async(args: argparse.Namespace) -> int:
    script_path = resolve_script_path(args.script)
    if not script_path.is_file():
        logger.error(f"❌ No se encontró el archivo de guion en: {script_path}")
        return 1

    from .narrator import generate_script_audio

    episode_slug = script_path.stem
    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = profile_from_args(args)

    logger.info(f"🎬 Iniciando pipeline para el episodio: {episode_slug}")
    logger.info(f"📂 Archivo de guion localizado en: {script_path}")

    # 1. Parseo del Guion YAML
    logger.info("📄 [Paso 1/4] Parseando y validando guion YAML...")
    try:
        parsed_script = parse_script(str(script_path))
        title = getattr(parsed_script, "title", None) or episode_slug
        description = getattr(parsed_script, "description", None) or \
            f"Video automatizado del episodio {episode_slug}"
        logger.info(f"✅ Guion validado: '{title}' ({len(parsed_script.scenes)} escenas)")
    except Exception as e:
        logger.error(f"❌ Error al parsear el guion '{script_path}': {e}")
        return 1

    # 2. Generación de Narración (TTS Multi-Voz por Escena y Diálogo)
    audio_output = output_dir / f"{episode_slug}_audio.mp3"
    if getattr(args, "reuse_audio", False) and _audio_ready(audio_output, parsed_script):
        logger.info(f"🎙️ [Paso 2/4] Reutilizando audio existente: {audio_output}")
    else:
        logger.info("🎙️ [Paso 2/4] Generando narración TTS multi-voz escena por escena...")
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
    try:
        logger.info(f"⏱️ Duración del audio del episodio: {fmt_hms(probe_duration(audio_output))}")
    except Exception:
        pass

    # 3. Video base sincronizado con el audio + ensamble final
    final_video = output_dir / f"{episode_slug}_final.mp4"
    logger.info(f"🎞️ [Paso 3/4] Ensamblando video final en: {final_video}")
    try:
        base_video: Optional[Path] = None
        if not getattr(args, "no_sync_base", False):
            try:
                base_video = build_synced_base(
                    parsed_script, script_path, audio_output, output_dir, profile,
                    images_root=getattr(args, "images_root", None),
                    ken_burns=not getattr(args, "static", False),
                    cut_mode=getattr(args, "cut_mode", "turns"),
                    jobs=getattr(args, "jobs", None),
                )
            except AudioSyncError as e:
                logger.error(f"❌ No se pudo sincronizar el video base con el audio: {e}")
                return 1
        else:
            candidates = [
                output_dir / f"{episode_slug}_base.mp4",
                script_path.parent / episode_slug / f"{episode_slug}_base.mp4",
                script_path.parent / f"{episode_slug}_base.mp4",
                script_path.parent / "manim_overlay.mp4",
            ]
            base_video = next((c for c in candidates if c.is_file()), None)

        if base_video:
            logger.info(f"🔍 Video base: {base_video}")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(base_video),
                "-i", str(audio_output),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                # Con el base sincronizado ambos duran lo mismo: -shortest recortaría
                # el último cuadro (~1/fps). Solo se usa con un base de otra duración.
                *(["-shortest"] if getattr(args, "no_sync_base", False) else []),
                "-movflags", "+faststart",
                str(final_video),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                v, a = probe_duration(final_video), probe_duration(audio_output)
                logger.info(f"✅ Video final: {fmt_hms(v)} (audio {fmt_hms(a)}, diferencia {v - a:+.3f}s)")
            except Exception:
                logger.info("✅ Ensamble con FFmpeg completado con éxito.")
        else:
            logger.warning(
                "⚠️ No se encontró ningún video base. "
                f"Se empaquetará únicamente la pista de audio lista en {audio_output}."
            )
            final_video = audio_output

    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", "ignore")[-800:] if e.stderr else str(e)
        logger.error(f"❌ Error de FFmpeg durante el ensamble del video: {err}")
        return 1
    except Exception as e:
        logger.error(f"❌ Error durante el ensamble del video: {e}")
        return 1

    # 4. Subida Opcional a YouTube
    if args.upload:
        logger.info("🚀 [Paso 4/4] Publicando video en YouTube...")
        if final_video.suffix != ".mp4":
            logger.error("❌ Se requiere un archivo .mp4 válido para subir a YouTube.")
            return 1
        try:
            from .youtube_uploader import YouTubeUploader

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


def main(argv=None) -> None:
    ensure_utf8_stdio()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)
    profile_from_args(args).apply_process_limits()
    exit_code = asyncio.run(run_pipeline_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
