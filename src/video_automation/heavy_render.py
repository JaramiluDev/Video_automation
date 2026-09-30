"""
Motor de Renderizado de Video Pesado (heavy_render.py)
Módulo asignado a HG.

Orquesta el ensamblado visual final: conecta secuencias de imágenes y
animaciones matemáticas de Manim en una sola línea de tiempo, y delega en
compositor.py (audio real + subtítulos quemados + export) para el resultado.
"""

import tempfile
from pathlib import Path
from typing import List

from moviepy import VideoFileClip

from .models import ScriptDefinition, Scene, OutputSettings
from .compositor import build_image_clip, compose_clips


def render_manim_scene(scene: Scene, resolution: tuple = (1920, 1080), fps: int = 30):
    """
    Renderiza una escena con Manim y devuelve un VideoFileClip listo para
    concatenarse con el resto de la línea de tiempo.

    Si Manim no está disponible en el entorno, hace fallback a un clip de color
    con texto de contenido, para que el pipeline no falle en entornos de CI o
    Docker livianos.
    """
    try:
        import numpy as np  # noqa: F401
        from manim import (
            Scene as ManimScene, Text, MathTex, Write, FadeOut, VGroup, tempconfig, UP,
        )

        render_dir = tempfile.mkdtemp(prefix="manim_render_")

        class FormulaScene(ManimScene):
            def construct(self):
                mobjects = []

                if scene.text_on_screen:
                    title = Text(scene.text_on_screen, font_size=36)
                    title.to_edge(UP)
                    mobjects.append(title)

                body = None
                if scene.formula:
                    try:
                        body = MathTex(scene.formula, font_size=64)
                    except Exception as e:
                        print(f"⚠️ MathTex falló ({e}), usando texto plano como fallback.")
                        body = Text(scene.formula, font_size=48)
                elif scene.narration:
                    body = Text(scene.narration, font_size=40)

                if body is not None:
                    mobjects.append(body)

                if not mobjects:
                    return

                group = VGroup(*mobjects) if len(mobjects) > 1 else mobjects[0]

                max_width = self.camera.frame_width * 0.9
                max_height = self.camera.frame_height * 0.8
                if group.width > max_width:
                    group.scale_to_fit_width(max_width)
                if group.height > max_height:
                    group.scale_to_fit_height(max_height)

                self.play(Write(group))
                hold_time = max(scene.duration - 1.5, 0.5)
                self.wait(hold_time)
                self.play(FadeOut(group))

        width, height = resolution
        with tempconfig({
            "media_dir": render_dir,
            "pixel_width": width,
            "pixel_height": height,
            "frame_rate": fps,
            "output_file": scene.id,
            "disable_caching": True,
            "progress_bar": "none",
        }):
            manim_scene = FormulaScene()
            manim_scene.render()
            video_path = manim_scene.renderer.file_writer.movie_file_path

        print(f"🎬 Escena Manim '{scene.id}' renderizada en: {video_path}")
        return VideoFileClip(str(video_path)).resized(new_size=resolution)
    except ModuleNotFoundError:
        print(f"⚠️ Manim no está instalado. Usando fallback visual simple para la escena '{scene.id}'.")
        from moviepy import ColorClip, CompositeVideoClip, TextClip

        content = scene.formula or scene.narration or scene.title
        duration = max(scene.duration, 0.5)
        background = ColorClip(size=resolution, color=(0, 0, 0), duration=duration).with_fps(fps)

        try:
            text_clip = TextClip(text=content, font_size=28, color='white', method='label')
            text_clip = text_clip.with_duration(duration).with_position(('center', 'center'))
            return CompositeVideoClip([background, text_clip], size=resolution).with_duration(duration)
        except OSError:
            return background


def render_video(script: ScriptDefinition, output_dir: str) -> str:
    """
    Punto de entrada principal del módulo. Recorre las escenas del guión en
    orden, arma un clip por cada una (imagen o Manim) y llama a
    compose_clips() con audio y subtítulos si el guión los trae.
    """
    print(f"Iniciando renderizado pesado para: {script.title}")

    settings = script.output_settings or OutputSettings()
    clips: List = []

    for scene in script.scenes:
        if scene.render_type == "manim":
            clips.append(render_manim_scene(scene, resolution=settings.resolution, fps=settings.fps))
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
