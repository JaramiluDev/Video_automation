"""
Motor de Renderizado de Video Pesado (heavy_render.py)
Módulo asignado a HG.

Orquesta el ensamblado visual final: conecta secuencias de imágenes y
animaciones matemáticas de Manim en una sola línea de tiempo, y delega en
compositor.py (audio real + subtítulos quemados + export) para el resultado.

Tipos de escena (models.Scene):
  - render_type "images"                 → imágenes del guion.
  - render_type "images" + manim_overlay → imágenes con un overlay Manim
                                           transparente encima (fórmulas,
                                           paneles), un tramo por imagen.
  - render_type "manim"                  → animación Manim a pantalla completa
                                           (manim_scene registrado o FormulaCard).

Calidad: render_video(..., profile=...) usa render_profiles.py
(--fast / --low-res / --production). Los clips Manim se guardan en
<salida>/manim_clips[_fast|_lowres]/ con una clave de caché: si no cambió la
escena, sus parámetros, la duración, el formato ni el código, no se vuelven a
renderizar.
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from moviepy import VideoFileClip

from .models import ScriptDefinition, Scene, OutputSettings
from .compositor import build_image_clip, compose_clips
from .render_profiles import RenderProfile, default_profile

log = logging.getLogger(__name__)


def _formula_card_class(scene: Scene):
    """
    Escena genérica (título + fórmula LaTeX o narración) para guiones que solo
    traen `formula`. Ahora hereda de TimedScene, así que también dura
    EXACTAMENTE scene.duration (antes duraba duration + 0.5 s).
    """
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
                self.hold(1.0)  # clip vacío pero con la duración correcta
                return
            group = VGroup(*mobjects) if len(mobjects) > 1 else mobjects[0]
            # Evita que texto/fórmulas largas se salgan del cuadro.
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
    """
    Renderiza una escena con Manim y devuelve un VideoFileClip listo para
    concatenarse con el resto de la línea de tiempo.

    - scene.manim_scene → clase registrada en scenes_video2.py (Video 2).
    - si no, scene.formula / scene.narration → tarjeta genérica (FormulaCard).

    En ambos casos el clip sale con resolución, fps y número de cuadros
    exactos (round(duration * fps)), codificado igual que simple_animator
    (libx264 / yuv420p / CFR), para que compositor.py y simple_concatenator
    no tengan que re-sincronizar nada.

    duration: permite que el pipeline inyecte otro tiempo (ej. el que midió
    el TTS). Por defecto se usa scene.duration, que es lo que da el parser.

    resolution/fps son los finales (ya escalados por el perfil). use_cache
    reutiliza el clip de clips_dir si su clave coincide.
    """
    from .manim_timing import render_timed_scene

    target = float(duration if duration is not None else scene.duration)
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
    """Falla ANTES de renderizar si el YAML pide una escena/overlay que no existe."""
    from .manim_timing import get_scene_class

    for scene in script.scenes:
        if scene.render_type == "manim" and scene.manim_scene:
            get_scene_class(scene.manim_scene)  # lanza KeyError con la lista disponible
        if scene.manim_overlay:
            if scene.render_type == "manim":
                raise ValueError(f"La escena {scene.id}: manim_overlay solo aplica a render_type 'images'")
            from .animations.export import get_overlay_scene

            get_overlay_scene(scene.manim_overlay)  # KeyError con la lista disponible
        if scene.duration <= 0:
            raise ValueError(f"La escena {scene.id} tiene duration <= 0")


def overlay_params(scene: Scene, image_durations: Sequence[float]) -> dict:
    """
    Parámetros del overlay con los tramos alineados a las imágenes de la
    escena. Si la clase tiene SEGMENTS fijos de otro tamaño, se respetan
    (se escalan a la duración) y se avisa que los cortes pueden no coincidir.
    """
    from .animations.export import get_overlay_scene

    cls = get_overlay_scene(scene.manim_overlay)
    params = dict(scene.manim_overlay_params or {})
    if params.get("tramos") is None and image_durations:
        segments = tuple(getattr(cls, "SEGMENTS", ()) or ())
        if not segments or len(segments) == len(image_durations):
            params["tramos"] = [float(d) for d in image_durations]
        else:
            log.warning("%s: %s tiene %d tramos y la escena %d imágenes; los cambios del overlay "
                        "no caerán en los cortes de imagen.", scene.id, cls.__name__,
                        len(segments), len(image_durations))
    return params


def render_scene_overlay(scene: Scene, base_clips: List, resolution: Tuple[int, int], fps: int,
                         clips_dir: Path, profile: Optional[RenderProfile] = None,
                         use_cache: bool = False):
    """
    Renderiza el overlay Manim de una escena de imágenes (.mov con alfa) y lo
    compone encima de sus imágenes. Devuelve UN clip con la duración exacta
    de la escena.
    """
    from moviepy import ColorClip, CompositeVideoClip, concatenate_videoclips
    from .animations import render_overlay

    resolution = (int(resolution[0]), int(resolution[1]))
    base_clips = [c for c in base_clips if c is not None]
    if base_clips:
        base = base_clips[0] if len(base_clips) == 1 else concatenate_videoclips(base_clips, method="compose")
    else:
        log.warning("%s: sin imágenes válidas; el overlay va sobre fondo negro.", scene.id)
        base = ColorClip(size=resolution, color=(0, 0, 0), duration=scene.duration)

    params = overlay_params(scene, [c.duration for c in base_clips])
    out = Path(clips_dir) / f"{scene.id}_overlay.mov"
    render_overlay(scene.manim_overlay, str(out), duration=scene.duration, params=params,
                   resolution=resolution, fps=fps, profile=profile, use_cache=use_cache)
    overlay = VideoFileClip(str(out), has_mask=True)
    print(f"🧮 Overlay '{scene.manim_overlay}' sobre '{scene.id}': {out}")
    return CompositeVideoClip([base, overlay.with_position((0, 0))], size=resolution) \
        .with_duration(scene.duration)


def resolve_output_format(script: ScriptDefinition, profile: RenderProfile,
                          resolution: Optional[Sequence[int]] = None,
                          fps: Optional[int] = None) -> Tuple[Tuple[int, int], int]:
    """
    Formato final: lo que pida la CLI (--resolution/--fps) o, si no, el
    output_settings del guion; después el perfil lo escala (fast → 480p...).
    """
    settings = script.output_settings or OutputSettings()
    base_res = tuple(resolution) if resolution else tuple(settings.resolution)
    base_fps = int(fps) if fps else int(settings.fps)
    return profile.resolve(base_res, base_fps)


def render_video(script: ScriptDefinition, output_dir: str,
                 profile: Optional[RenderProfile] = None,
                 resolution: Optional[Sequence[int]] = None,
                 fps: Optional[int] = None,
                 use_cache: bool = True) -> str:
    """
    Punto de entrada principal del módulo. Recorre las escenas del guión en
    orden, arma un clip por cada una (imagen, imagen + overlay o Manim) y
    llama a compose_clips() con audio y subtítulos si el guión los trae.

    profile: perfil de calidad (None → $VA_QUALITY o production).
    resolution/fps: sobrescriben output_settings del guion (antes de escalar).
    use_cache: reutiliza clips Manim ya renderizados con la misma clave.
    """
    print(f"Iniciando renderizado pesado para: {script.title}")

    profile = profile or default_profile()
    res, out_fps = resolve_output_format(script, profile, resolution, fps)
    print(f"⚙️  {profile.summary(res, out_fps)}")
    validate_manim_scenes(script)
    clips: List = []
    # Los clips de Manim se conservan junto al render final por si se
    # quieren revisar o unir con simple_concatenator (-c copy). Cada perfil
    # usa su carpeta para no mezclar resoluciones.
    clips_dir = profile.tag_dir(Path(output_dir) / "manim_clips")

    for scene in script.scenes:
        if scene.render_type == "manim":
            clips.append(render_manim_scene(scene, resolution=res, fps=out_fps,
                                            clips_dir=str(clips_dir), profile=profile,
                                            use_cache=use_cache))
            continue
        scene_clips = []
        for img in scene.image_paths:
            duration = scene.duration / len(scene.image_paths)
            scene_clips.append(build_image_clip(img, duration, res))
        if scene.manim_overlay:
            clips.append(render_scene_overlay(scene, scene_clips, res, out_fps, clips_dir,
                                              profile=profile, use_cache=use_cache))
        else:
            clips.extend(scene_clips)

    # Los borradores no pisan el render de producción: video.mp4 → video_fast.mp4
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

    print(f"Renderizado pesado completado. Video guardado en: {result}")
    return result
