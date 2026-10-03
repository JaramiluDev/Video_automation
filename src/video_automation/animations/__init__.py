"""
Módulo de Overlay y Animaciones Manim (HG).

Clips de animación matemática que se incrustan sobre la base visual del guion
(los Ken Burns de simple_animator.py / build_zoomed_video.py).

  math_scenes.py  Escenas Manim (solo escenas) + SCENE_REGISTRY.
                  FormulaOverlay: overlay genérico de fórmulas desde el YAML.
  base.py         OverlayScene: tramos alineados a los cortes de la base y
                  fondo transparente opcional.
  export.py       render_overlay(): 1080p, fps constante, cuadros exactos;
                  .mp4 opaco (igual que simple_animator) o .mov/.webm con alfa.

CLI: scripts/render_manim_clips.py
"""

from .export import render_overlay, probe_overlay
from .math_scenes import SCENE_REGISTRY, FormulaOverlay, Scene02Math

__all__ = ["SCENE_REGISTRY", "Scene02Math", "FormulaOverlay", "render_overlay", "probe_overlay"]
