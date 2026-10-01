#!/usr/bin/env python3
"""
Orquestador Maestro del Pipeline - Video 2.

Ejecuta el flujo completo de automatización sin depender de YAML:
1. Limpieza de miniclips temporales en animated_clips
2. Generación de la base visual con Zoom (Ken Burns) desde GUION-02
3. Mezcla con el audio (si existe en data/audio/ o data/outputs/)
4. Subida a YouTube Studio usando YouTubeUploader
"""

import subprocess
import sys
from pathlib import Path


def run_step(description: str, command: list[str]) -> None:
    """Ejecuta un comando de sistema imprimiendo el progreso."""
    print("\n" + "=" * 70)
    print(f"🚀 [PIPELINE VIDEO 2] {description}")
    print("=" * 70)
    print(f"⚙️  Ejecutando: {' '.join(command)}")

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        print(f"\n❌ Error fatal en el paso: {description}")
        sys.exit(result.returncode)

    print(f"✅ Paso completado exitosamente: {description}")


def clean_temp_clips(clips_dir: Path) -> None:
    """Limpia los miniclips anteriores para no concatenar basura."""
    print("\n🧹 Limpiando miniclips temporales en:", clips_dir)
    if clips_dir.exists():
        for item in clips_dir.glob("*.mp4"):
            item.unlink()
    else:
        clips_dir.mkdir(parents=True, exist_ok=True)


def find_audio_file() -> Path | None:
    """Busca automáticamente el archivo de audio (.mp3 o .wav)."""
    # 1. Buscar en data/outputs/audio_tts.mp3
    default_audio = Path("data/outputs/audio_tts.mp3")
    if default_audio.exists():
        return default_audio

    # 2. Buscar cualquier mp3 o wav en data/audio/
    audio_dir = Path("data/audio")
    if audio_dir.exists():
        audios = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav"))
        if audios:
            print(f"🎙️️ Audio encontrado en data/audio: {audios[0]}")
            return audios[0]

    return None


def main() -> None:
    print("🎬 INICIANDO AUTOMATIZACIÓN COMPLETA DEL VIDEO 2")

    script_dir = Path("assets/source_scripts/GUION-02")
    animated_clips_dir = Path("animated_clips")

    video_base = animated_clips_dir / "video2_base_render.mp4"
    output_final = Path("data/outputs/VIDEO2_FINAL.mp4")

    # Paso 0: Limpieza
    clean_temp_clips(animated_clips_dir)

    # Paso 1: Base visual usando build_zoomed_video.py con las imágenes de GUION-02
    run_step(
        "Generación de clips y render base visual (GUION-02)",
        [sys.executable, "scripts/build_zoomed_video.py", str(script_dir)],
    )

    # Paso 2: Unir Audio + Video mediante final_muxer.py
    audio_file = find_audio_file()
    if audio_file and audio_file.exists():
        run_step(
            "Ensamblado final de Audio + Video (Muxer)",
            [
                sys.executable,
                "scripts/final_muxer.py",
                str(video_base),
                str(audio_file),
                str(output_final),
            ],
        )
    else:
        print("\n⚠️  No se encontró archivo de audio (.mp3 o .wav) en 'data/audio/' ni 'data/outputs/audio_tts.mp3'.")
        print("📌 Si ya tienes el audio grabado/generado, mételo en la carpeta 'data/audio/'.")
        output_final = video_base

    # Paso 3: Subida a YouTube Studio
    print("\n" + "=" * 70)
    print("🚀 [PIPELINE VIDEO 2] Subida automatizada a YouTube Studio")
    print("=" * 70)

    try:
        from src.video_automation.youtube_uploader import YouTubeUploader

        uploader = YouTubeUploader()
        print(f"📹 Subiendo video: {output_final}")
        uploader.upload_video(video_path=str(output_final), title="Buscando a la X - Video 2")
        print("✅ Subida a YouTube finalizada.")
    except Exception as e:
        print(f"⚠️ Nota sobre subida a YouTube: {e}")

    print("\n🎉 PIPELINE DEL VIDEO 2 FINALIZADO CORRECTAMENTE")


if __name__ == "__main__":
    main()
