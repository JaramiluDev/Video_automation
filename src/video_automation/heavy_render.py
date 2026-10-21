import logging
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from moviepy import VideoFileClip, AudioFileClip
from .models import ScriptDefinition, Scene, OutputSettings
from .compositor import build_image_clip, compose_clips
from .render_profiles import RenderProfile, default_profile

log = logging.getLogger(__name__)

def _get_scene_audio_duration(scene_id: str, default_duration: float) -> float:
    """Busca el audio consolidado de la escena para extraer su duración real exacta."""
    possible_paths = [
        Path(f"data/output/GUION-02_audio_dialogues/{scene_id}/{scene_id}_consolidated.mp3"),
        Path(f"data/output/GUION-02_audio_dialogues/escena_{scene_id.replace('escena_', '')}/{scene_id}_consolidated.mp3")
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with AudioFileClip(str(p)) as ac:
                    return float(ac.duration)
            except Exception:
                pass
    # Buscar de forma genérica en data/output/
    audio_dir = Path("data/output")
    if audio_dir.exists():
        for match in audio_dir.glob(f"**/{scene_id}*_consolidated.mp3"):
            try:
                with AudioFileClip(str(match)) as ac:
                    return float(ac.duration)
            except Exception:
                pass
    return float(default_duration)

def _formula_card_class(scene: Scene):
    from manim import Text, Write, FadeOut, VGroup, UP
    from .manim_timing import TimedScene, tex

    class FormulaCard(TimedScene):
        def timeline(self):
            mobjects = []
            if scene.text_on_screen:
                mobjects.append(Text(scene.text_on_screen, font_size=36).to_edge(UP))
            if scene.formula:
                mobjects.append(tex(scene.formula, font_size=64))
            elif scene.narration:
                mobjects.append(Text(scene.narration, font_size=40))
            if not mobjects:
                self.hold(1.0)
                return
            group = VGroup(*mobjects) if len(mobjects) > 1 else mobjects[0]
            max_width = self.camera.frame_width * 0.9
            max_height = self.camera.frame_height * 0.8
            if group.width > max_width:
                group.scale_to_fit_width(max_width)
            if group.height > max_height:
                group.scale_to_fit_height(max_height)
            self.beat(Write(group), t=1.0)
            self.hold(max(scene.duration - 1.5, 0.5))
            self.beat(FadeOut(group), t=0.5)

    FormulaCard.__name__ = f"FormulaCard_{scene.id}".replace("-", "_")
    return FormulaCard

def render_manim_scene(scene: Scene, resolution: tuple = (1920, 1080), fps: int = 30,
                       clips_dir: Optional[str] = None, duration: Optional[float] = None,
                       profile: Optional[RenderProfile] = None, use_cache: bool = False):
    from .manim_timing import render_timed_scene

    real_dur = _get_scene_audio_duration(scene.id, scene.duration)
    target = float(duration if duration is not None else real_dur)
    out_dir = Path(clips_dir) if clips_dir else Path(tempfile.mkdtemp(prefix="manim_clips_"))
    out_path = out_dir / f"{scene.id}.mp4"

    what = scene.manim_scene or _formula_card_class(scene)
    extra = None if scene.manim_scene else {
        "formula": scene.formula, "text_on_screen": scene.text_on_screen, "narration": scene.narration,
    }
    render_timed_scene(what, str(out_path), duration=target, params=scene.manim_params,
                       resolution=tuple(resolution), fps=fps, profile=profile,
                       use_cache=use_cache, cache_extra=extra)

    print(f"🎬 Escena Manim '{scene.id}' renderizada en: {out_path} ({target:.3f}s @ {fps}fps)")
    return VideoFileClip(str(out_path))

def validate_manim_scenes(script: ScriptDefinition) -> None:
    from .manim_timing import get_scene_class

    for scene in script.scenes:
        if scene.render_type == "manim" and scene.manim_scene:
            get_scene_class(scene.manim_scene)
        if scene.manim_overlay:
            if scene.render_type == "manim":
                raise ValueError(f"La escena {scene.id}: manim_overlay solo aplica a render_type 'images'")
            from .animations.export import get_overlay_scene
            get_overlay_scene(scene.manim_overlay)

def overlay_params(scene: Scene, image_durations: Sequence[float]) -> dict:
    from .animations.export import get_overlay_scene

    cls = get_overlay_scene(scene.manim_overlay)
    params = dict(scene.manim_overlay_params or {})
    if params.get("tramos") is None and image_durations:
        segments = tuple(getattr(cls, "SEGMENTS", ()) or ())
        if not segments or len(segments) == len(image_durations):
            params["tramos"] = [float(d) for d in image_durations]
        else:
            log.warning("%s: %s tiene %d tramos y la escena %d imágenes.", scene.id, cls.__name__,
                        len(segments), len(image_durations))
    return params

def render_scene_overlay(scene: Scene, base_clips: List, resolution: Tuple[int, int], fps: int,
                         clips_dir: Path, profile: Optional[RenderProfile] = None,
                         use_cache: bool = False):
    from moviepy import ColorClip, CompositeVideoClip, concatenate_videoclips
    from .animations import render_overlay

    resolution = (int(resolution[0]), int(resolution[1]))
    base_clips = [c for c in base_clips if c is not None]
    real_dur = _get_scene_audio_duration(scene.id, scene.duration)
    
    if base_clips:
        base = base_clips[0] if len(base_clips) == 1 else concatenate_videoclips(base_clips, method="compose")
    else:
        log.warning("%s: sin imágenes válidas; el overlay va sobre fondo negro.", scene.id)
        base = ColorClip(size=resolution, color=(0, 0, 0), duration=real_dur)

    params = overlay_params(scene, [c.duration for c in base_clips])
    out = Path(clips_dir) / f"{scene.id}_overlay.mov"
    render_overlay(scene.manim_overlay, str(out), duration=real_dur, params=params,
                   resolution=resolution, fps=fps, profile=profile, use_cache=use_cache)
    overlay = VideoFileClip(str(out), has_mask=True)
    print(f"🧮 Overlay '{scene.manim_overlay}' sobre '{scene.id}': {out}")
    return CompositeVideoClip([base, overlay.with_position((0, 0))], size=resolution) \
        .with_duration(real_dur)

def resolve_output_format(script: ScriptDefinition, profile: RenderProfile,
                          resolution: Optional[Sequence[int]] = None,
                          fps: Optional[int] = None) -> Tuple[Tuple[int, int], int]:
    settings = script.output_settings or OutputSettings()
    base_res = tuple(resolution) if resolution else tuple(settings.resolution)
    base_fps = int(fps) if fps else int(settings.fps)
    return profile.resolve(base_res, base_fps)

def render_video(script: ScriptDefinition, output_dir: str,
                 profile: Optional[RenderProfile] = None,
                 resolution: Optional[Sequence[int]] = None,
                 fps: Optional[int] = None,
                 use_cache: bool = True) -> str:
    print(f"Iniciando renderizado pesado sincronizado para: {script.title}")

    profile = profile or default_profile()
    res, out_fps = resolve_output_format(script, profile, resolution, fps)
    print(f"⚙️  {profile.summary(res, out_fps)}")
    validate_manim_scenes(script)
    clips: List = []
    clips_dir = profile.tag_dir(Path(output_dir) / "manim_clips")

    for scene in script.scenes:
        # Obtener la duración real basada en el audio consolidado de la escena (21 mins total)
        real_duration = _get_scene_audio_duration(scene.id, scene.duration)
        
        if scene.render_type == "manim":
            # Forzar la duración real al render de manim
            scene.duration = real_duration
            clips.append(render_manim_scene(scene, resolution=res, fps=out_fps,
                                            clips_dir=str(clips_dir), profile=profile,
                                            use_cache=use_cache))
            continue
            
        scene_clips = []
        num_imgs = len(scene.image_paths) if scene.image_paths else 1
        img_duration = real_duration / num_imgs
        
        for img in scene.image_paths:
            scene_clips.append(build_image_clip(img, img_duration, res))
            
        if scene.manim_overlay:
            scene.duration = real_duration
            clips.append(render_scene_overlay(scene, scene_clips, res, out_fps, clips_dir,
                                              profile=profile, use_cache=use_cache))
        else:
            clips.extend(scene_clips)

    output_file = profile.tag_path(Path(output_dir) / script.output_filename)

    result = compose_clips(
        clips,
        str(output_file),
        audio_path=script.audio_path,
        subtitle_path=script.subtitle_path,
        fps=out_fps,
        resolution=res,
        profile=profile,
    )

    print(f"Renderizado pesado sincronizado completado. Video guardado en: {result}")
    return result
