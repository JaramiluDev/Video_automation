from pathlib import Path

from .compositor import compose_video
from .narrator import TTSNarrator
from .script_parser import parse_script


def run_pipeline(script_path: str, output_dir: str, fps: int = 30, resolution: str = "1920x1080", include_audio: bool = True) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)

    all_images = []
    all_durations = []
    narrative_audio = []

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    for scene in script.scenes:
        for img in scene.image_paths:
            all_images.append(img)
            all_durations.append(scene.duration / len(scene.image_paths))

        if include_audio and scene.narration.strip():
            audio_output = output_root / "audio" / f"{scene.id}.wav"
            audio_output.parent.mkdir(parents=True, exist_ok=True)
            narration_result = TTSNarrator().generate_audio(scene.narration, str(audio_output))
            narrative_audio.append({
                "scene_id": scene.id,
                "audio_path": narration_result["audio_path"],
                "duration": narration_result["duration"],
            })

    output_file = output_root / script.output_filename
    compose_video(all_images, all_durations, str(output_file), fps=fps, resolution=resolution)

    if include_audio and narrative_audio:
        print(f"Audio generado para {len(narrative_audio)} escenas. Carpeta: {output_root / 'audio'}")

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return str(output_file)
