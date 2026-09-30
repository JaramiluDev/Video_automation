"""
Motor de Renderizado de Video Pesado (heavy_render.py)
Módulo asignado a HG.

Orquesta el ensamblado visual final: conecta secuencias de imágenes y
animaciones matemáticas de Manim en una sola línea de tiempo, y delega en
compositor.py (audio real + subtítulos quemados + export) para el resultado.
"""

import tempfile
from pathlib import Path
from typing import List, Optional

from moviepy import VideoFileClip

from .models import ScriptDefinition, Scene, OutputSettings
from .compositor import build_image_clip, compose_clips


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
                       clips_dir: Optional[str] = None, duration: Optional[float] = None):
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
    """
    from .manim_timing import render_timed_scene

    target = float(duration if duration is not None else scene.duration)
    out_dir = Path(clips_dir) if clips_dir else Path(tempfile.mkdtemp(prefix="manim_clips_"))
    out_path = out_dir / f"{scene.id}.mp4"

    what = scene.manim_scene or _formula_card_class(scene)
    render_timed_scene(what, str(out_path), duration=target, params=scene.manim_params,
                       resolution=tuple(resolution), fps=fps)

    print(f"🎬 Escena Manim '{scene.id}' renderizada en: {out_path} ({target:.3f}s @ {fps}fps)")
    return VideoFileClip(str(out_path))


def validate_manim_scenes(script: ScriptDefinition) -> None:
    """Falla ANTES de renderizar si el YAML pide una escena que no existe."""
    from .manim_timing import get_scene_class

    for scene in script.scenes:
        if scene.render_type == "manim" and scene.manim_scene:
            get_scene_class(scene.manim_scene)  # lanza KeyError con la lista disponible
        if scene.duration <= 0:
            raise ValueError(f"La escena {scene.id} tiene duration <= 0")


def render_video(script: ScriptDefinition, output_dir: str) -> str:
    """
    Punto de entrada principal del módulo. Recorre las escenas del guión en
    orden, arma un clip por cada una (imagen o Manim) y llama a
    compose_clips() con audio y subtítulos si el guión los trae.
    """
    print(f"Iniciando renderizado pesado para: {script.title}")

    settings = script.output_settings or OutputSettings()
    validate_manim_scenes(script)
    clips: List = []
    # Los clips de Manim se conservan junto al render final por si se
    # quieren revisar o unir con simple_concatenator (-c copy).
    clips_dir = Path(output_dir) / "manim_clips"

    for scene in script.scenes:
        if scene.render_type == "manim":
            clips.append(render_manim_scene(scene, resolution=settings.resolution, fps=settings.fps,
                                            clips_dir=str(clips_dir)))
        else:
            for img in scene.image_paths:
                duration = scene.duration / len(scene.image_paths)
                clips.append(build_image_clip(img, duration, settings.resolution))

    output_file = Path(output_dir) / script.output_filename

    result = compose_clips(
        clips,
        str(output_file),
        audio_path=script.audio_path,
        subtitle_path=script.subtitle_path,
        fps=settings.fps,
        resolution=settings.resolution,
    )

    print(f"Renderizado pesado completado. Video guardado en: {result}")
    return result
