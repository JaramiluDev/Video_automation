from pathlib import Path
from .script_parser import parse_script
from .heavy_render import render_video
from .narrator import TTSNarrator

def run_pipeline(script_path: str, output_dir: str, fps: int = 30, resolution: str = "1920x1080", include_audio: bool = True) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    narrative_audio = []

    if include_audio:
        for scene in script.scenes:
            if scene.narration.strip():
                audio_output = output_root / "audio" / f"{scene.id}.wav"
                audio_output.parent.mkdir(parents=True, exist_ok=True)
                narration_result = TTSNarrator().generate_audio(scene.narration, str(audio_output))
                narrative_audio.append({
                    "scene_id": scene.id,
                    "audio_path": narration_result["audio_path"],
                    "duration": narration_result["duration"],
                })
        if narrative_audio:
            print(f"Audio generado para {len(narrative_audio)} escenas. Carpeta: {output_root / 'audio'}")

    output_file = render_video(script, output_dir)

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return output_file