from pathlib import Path
from typing import Optional, Tuple, Union

from .script_parser import parse_script
from .heavy_render import render_video
from .narrator import TTSNarrator
from .render_profiles import RenderProfile, get_profile


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

    output_file = render_video(script, output_dir, profile=profile,
                               resolution=parse_resolution(resolution), fps=fps,
                               use_cache=use_cache)

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return output_file
