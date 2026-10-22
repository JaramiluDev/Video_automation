#!/usr/bin/env python3
"""
Orquestador Maestro del Pipeline - Video 2.

Ejecuta el flujo completo de automatización:
1. Limpieza de miniclips temporales en animated_clips
2. Generación de la base visual con Zoom (Ken Burns) desde GUION-02
3. Generación automática de voz TTS desde el guion YAML
4. Mezcla de Audio + Video mediante final_muxer.py
5. Subida a YouTube Studio usando YouTubeUploader
"""

import subprocess
import sys
from pathlib import Path

# Añadir la raíz del proyecto al sys.path para que reconozca la carpeta 'src'
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    default_audio = Path("data/outputs/audio_tts.mp3")
    if default_audio.exists():
        return default_audio

    for p in [Path("data/audio"), Path("data/outputs")]:
        if p.exists():
            audios = list(p.glob("*.mp3")) + list(p.glob("*.wav"))
            if audios:
                print(f"🎙 Audio encontrado en {p}: {audios[0]}")
                return audios[0]

    return None


def find_thumbnail_file() -> Path | None:
    """
    Busca automáticamente la miniatura en 'thumbnails/', 'data/' o '/app/'.
    """
    candidates = [
        Path("data/miniatura_final.jpg"),
        Path("thumbnails/miniatura_final.jpg"),
        Path("thumbnails/miniatura_auto.jpg"),
        Path("/app/data/miniatura_final.jpg"),
        Path("/app/thumbnails/miniatura_final.jpg"),
        Path("/app/thumbnails/miniatura_auto.jpg"),
        ROOT / "data/miniatura_final.jpg",
        ROOT / "thumbnails/miniatura_final.jpg",
        ROOT / "thumbnails/miniatura_auto.jpg",
    ]

    for candidate in candidates:
        if candidate.is_file():
            print(f"🖼️ Portada detectada en: {candidate}")
            return candidate.resolve()

    return None


def main() -> None:
    print("🎬 INICIANDO AUTOMATIZACIÓN COMPLETA DEL VIDEO 2")

    script_dir = Path("assets/source_scripts/GUION-02")
    animated_clips_dir = Path("animated_clips")

    Path("data/outputs").mkdir(parents=True, exist_ok=True)
    Path("data/audio").mkdir(parents=True, exist_ok=True)

    video_base = animated_clips_dir / "video2_base_render.mp4"
    output_final = Path("data/outputs/VIDEO2_FINAL.mp4")

    # Paso 0: Limpieza
    clean_temp_clips(animated_clips_dir)

    # Paso 1: Base visual
    run_step(
        "Generación de clips y render base visual (GUION-02)",
        [sys.executable, "scripts/build_zoomed_video.py", str(script_dir)],
    )

    # Paso 1.5: TTS YAML
    possible_yamls = [
        script_dir / "GUION-02.yaml",
        script_dir / "script.yaml",
        Path("assets/source_scripts/GUION-02.yaml"),
    ]
    yaml_path = next((y for y in possible_yamls if y.exists()), None)

    if yaml_path:
        run_step(
            "Generación de audio TTS desde el guion YAML",
            [
                sys.executable,
                "-m",
                "src.video_automation.narrator",
                str(yaml_path),
                "--output",
                "data/outputs/audio_tts.mp3",
            ],
        )

    # Paso 2: Unir Audio + Video
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
        print("\n⚠️ No se encontró archivo de audio. Se usará el render base.")
        output_final = video_base

    # Paso 3: Subida a YouTube Studio
    print("\n" + "=" * 70)
    print("🚀 [PIPELINE VIDEO 2] Subida automatizada a YouTube Studio")
    print("=" * 70)

    try:
        from src.video_automation.youtube_uploader import YouTubeUploader

        uploader = YouTubeUploader()
        print(f"📹 Subiendo video: {output_final}")

        thumb_file = find_thumbnail_file()
        if thumb_file:
            print(f"🖼️ Asignando portada verificada: {thumb_file}")

        # Titulo ti Video 2
        uploader.upload_video(
            video_path=str(output_final),
            title="Buscando a la X - Episodio 2",
            thumbnail_path=str(thumb_file) if thumb_file else None,
        )
        print("✅ Subida a YouTube y miniatura finalizadas con éxito.")
    except Exception as e:
        print(f"⚠️ Error durante la subida a YouTube: {e}")

    print("\n🎉 PIPELINE DEL VIDEO 2 FINALIZADO CORRECTAMENTE")


if __name__ == "__main__":
    main()