"""
Pruebas del catálogo de componentes (HG) para el Episodio 3:
ecuaciones.py (lógica pura), animations/components.py (piezas Manim) y los
overlays genéricos FractionOverlay / LinearEquationOverlay / GraphOverlay.

- Rápidas (siempre): despeje exacto, comprobación, raíces, reparto de
  tramos, construcción de componentes sin renderizar, compatibilidad de
  nombres antiguos y que el YAML del Episodio 3 apunte a overlays existentes.
- De render (requieren ffmpeg): cada overlay nuevo en borrador, con alfa y
  cuadros exactos, incluso con más/menos tramos que contenidos y con ícono.
"""

from __future__ import annotations

import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from video_automation.ecuaciones import (
    check_steps, find_pair, frac_latex, pairs_with_product, parse_linear, poly_eval, poly_latex,
    real_roots, solve_steps, vertex,
)

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="requiere ffmpeg/ffprobe")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    from manim import tempconfig

    monkeypatch.delenv("VA_QUALITY", raising=False)
    monkeypatch.setenv("VA_NO_NICE", "1")
    monkeypatch.setenv("VA_CACHE_DIR", str(tmp_path / "cache"))
    # Los componentes que se arman fuera de un render escriben sus SVG de
    # LaTeX/Text en media/ del directorio actual: se mandan a tmp_path.
    with tempconfig({"media_dir": str(tmp_path / "media")}):
        yield


# ------------------------------------------------------- ecuaciones (puras)
@pytest.mark.parametrize("text,solution", [
    ("x + 4 = 0", -4), ("x + 5 = 0", -5), ("3x - 5 = 10", 5), ("2x + 3 = x - 1", -4),
    ("x/2 + 1 = 4", 6), ("-x = 7", -7), ("4 = 2x", 2), ("5 - x = 2x + 11", -2),
    ("2/3x = 4", 6), ("3x = 2", Fraction(2, 3)), ("x − 1 = 0", 1),
])
def test_linear_solutions_are_exact(text, solution):
    eq = parse_linear(text)
    assert eq.solution == solution
    steps = solve_steps(eq)
    assert steps[0].kind == "start" and steps[-1].kind == "solution"
    assert steps[-1].latex == f"x = {frac_latex(solution)}"
    lines, ok = check_steps(eq)
    assert ok and len(lines) == 2


def test_steps_match_the_blackboard_of_episode_3():
    """Pizarrón de la Escena 5: x + 4 = 0 → x + 4 - 4 = 0 - 4 → x = -4."""
    steps = solve_steps(parse_linear("x + 4 = 0"))
    assert [s.latex for s in steps] == ["x + 4 = 0", "x + 4 - 4 = 0 - 4", "x = -4"]
    assert steps[1].explanation == "Restamos 4 en ambos lados" and steps[1].op == "- 4"
    assert check_steps(parse_linear("x + 4 = 0"))[0][0] == r"\left(-4\right) + 4 = 0"


def test_steps_without_intermediate_lines():
    steps = solve_steps(parse_linear("3x - 5 = 10"), show_operations=False)
    assert [s.latex for s in steps] == ["3x - 5 = 10", "3x = 15", "x = 5"]


def test_wrong_value_fails_the_check():
    lines, ok = check_steps(parse_linear("x + 4 = 0"), 4)
    assert not ok and r"\neq" in lines[1]


@pytest.mark.parametrize("bad", ["x + y = 2", "x^2 = 4", "2 = 2", "x + 1 = x", "x = ", "3 4 = x",
                                 "x = 1 = 2", "x/0 = 1"])
def test_invalid_linear_equations(bad):
    with pytest.raises(ValueError):
        parse_linear(bad)


def test_polynomial_helpers():
    assert poly_eval([1, 9, 20], -4) == 0 and poly_eval([1, 9, 20], -5) == 0
    assert real_roots([1, 9, 20]) == [-5, -4]
    assert real_roots([1, 0, 1]) == []
    assert real_roots([2, -1]) == [Fraction(1, 2)]
    assert poly_latex([1, 9, 20]) == "x^{2} + 9x + 20"
    assert poly_latex([-1, 0, 4]) == "-x^{2} + 4"
    assert vertex([1, 9, 20]) == (Fraction(-9, 2), Fraction(-1, 4))
    roots = real_roots([1, 0, -2])          # ±√2: sin forma exacta → flotantes
    assert all(isinstance(r, float) for r in roots) and abs(roots[1] ** 2 - 2) < 1e-12


def test_casting_of_numbers():
    assert find_pair(20, 9) == (4, 5)
    assert find_pair(20, 21) == (1, 20)
    assert find_pair(20, 100) is None
    assert (1, 20) in pairs_with_product(20) and (-4, -5) in pairs_with_product(20)
    assert (2, -3) in pairs_with_product(-6)


# ------------------------------------------------------------- tramos
def test_distribute_contents_over_segments():
    from video_automation.animations.math_scenes import distribute

    assert distribute(2, 2) == [[0], [1]]
    assert distribute(2, 3) == [[0], [1], []]       # imagen extra: se queda la última
    assert distribute(3, 1) == [[0, 1, 2]]          # una imagen: todo en ese tramo
    assert distribute(3, 2) == [[0], [1, 2]]
    with pytest.raises(ValueError):
        distribute(1, 0)


# ------------------------------------------------- registro y compatibilidad
def test_new_overlays_are_registered_everywhere():
    from video_automation.animations.export import get_overlay_scene
    from video_automation.manim_timing import get_scene_class

    for name in ("FractionOverlay", "LinearEquationOverlay", "GraphOverlay"):
        assert get_overlay_scene(name).__name__ == name
        assert get_scene_class(name).__name__ == name   # también como escena completa


def test_old_import_paths_still_work():
    from video_automation import scenes_video2 as v2
    from video_automation.animations import components as c
    from video_automation.animations import math_scenes as ms

    assert v2.T is c.T and v2.frac is c.frac and v2.fraction_rect is c.fraction_rect
    assert v2.BG == c.BG and v2.check_mark is c.check_mark and callable(v2._hatch)
    assert ms.panel is c.panel and ms.tag is c.tag and "abajo" in ms.PANEL_LAYOUTS


def test_episode3_yaml_references_existing_overlays():
    from video_automation.heavy_render import validate_manim_scenes
    from video_automation.script_parser import parse_script

    script = parse_script(str(ROOT / "examples" / "episodio3_overlays.yaml"))
    validate_manim_scenes(script)
    overlays = {s.manim_overlay for s in script.scenes}
    assert {"LinearEquationOverlay", "GraphOverlay", "FormulaOverlay"} <= overlays


# --------------------------------------------- componentes (sin renderizar)
def test_components_build_and_expose_parts():
    from manim import DOWN

    from video_automation.animations import components as c

    row = c.cross_products_row((2, 4), (4, 8))
    assert row.equivalent and len(row.prods) == 2
    bars = c.fraction_bars_row((1, 3), (2, 6), True)
    assert len(bars.ra.cells) == 3 and len(bars.rb.shaded) == 2

    steps = solve_steps(parse_linear("x + 4 = 0"))
    flow = c.steps_flow(steps, direction=DOWN)
    assert len(flow.lines) == 3 and len(flow.arrows) == 2

    plot = c.function_plot([1, 9, 20], [-7, -2, 1], [-1, 6, 1])
    assert len(plot.roots) == 2 and plot.label is not None
    assert len(c.function_plot([1, 0, 1], [-3, 3, 1], [0, 9, 3]).roots) == 0   # sin raíces reales

    nl = c.number_line_points([-6, 0, 1], [-5, -4])
    assert len(nl.dots) == 2

    for pos in c.PANEL_LAYOUTS:
        box = c.panel_box(pos)
        assert abs(box.get_center()[0]) + box.width / 2 <= c.FRAME_W / 2 + 1e-6
    with pytest.raises(ValueError):
        c.panel_box("diagonal")


def _write_assets(tmp_path: Path):
    svg = tmp_path / "lupa.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                   '<circle cx="10" cy="10" r="7" fill="none" stroke="#F4C95D" stroke-width="2"/>'
                   '<line x1="15" y1="15" x2="22" y2="22" stroke="#F4C95D" stroke-width="3"/></svg>',
                   encoding="utf-8")
    from PIL import Image

    png = tmp_path / "icono.png"
    Image.new("RGBA", (32, 32), (244, 201, 93, 255)).save(png)
    return svg, png


def test_asset_mobject_svg_png_and_errors(tmp_path):
    from manim import ImageMobject, SVGMobject

    from video_automation.animations.components import asset_mobject

    svg, png = _write_assets(tmp_path)
    assert isinstance(asset_mobject(svg, height=1.0), SVGMobject)
    img = asset_mobject(png, height=0.8)
    assert isinstance(img, ImageMobject) and abs(img.height - 0.8) < 1e-6
    with pytest.raises(FileNotFoundError):
        asset_mobject(tmp_path / "no.svg")
    bad = tmp_path / "x.gif"
    bad.write_bytes(b"GIF89a")
    with pytest.raises(ValueError):
        asset_mobject(bad)


# ----------------------------------------------------- render en borrador
RES, FPS = (256, 144), 15


@needs_ffmpeg
@pytest.mark.parametrize("scene,params,duration", [
    ("LinearEquationOverlay", {"ecuacion": "x + 4 = 0", "titulo": "Primer caso", "comprobar": True}, 6.0),
    ("LinearEquationOverlay", {"ecuaciones": ["3x - 5 = 10", "x/2 + 1 = 4"], "posicion": "derecha",
                               "tramos": [4.5]}, 4.5),                       # 2 ecuaciones, 1 tramo
    ("GraphOverlay", {"funcion": [1, 9, 20], "x_range": [-7, -2, 1], "y_range": [-1, 6, 1],
                      "tramos": [3, 3, 3]}, 9.0),                            # curva + 2 raíces
    ("GraphOverlay", {"funcion": [2, -4], "x_range": [-1, 4], "y_range": [-4, 4],
                      "posicion": "centro"}, 4.0),                           # recta en franja
    ("FractionOverlay", {"a": "2/4", "b": "4/8", "titulo": "¿Equivalentes?"}, 7.0),
    ("FractionOverlay", {"a": "2/4", "b": "2/8", "modo": "productos", "tramos": [2.5, 2.5]}, 5.0),
    ("FormulaOverlay", {"formula": r"x = -4", "posicion": "izquierda"}, 3.0),
])
def test_overlays_render_in_draft_with_alpha(tmp_path, scene, params, duration):
    from video_automation.animations import render_overlay
    from video_automation.render_profiles import get_profile

    out = tmp_path / f"{scene}.mov"
    info = render_overlay(scene, str(out), duration=duration, params=params, resolution=RES, fps=FPS,
                          profile=get_profile("draft"))
    assert (info["width"], info["height"]) == RES
    assert info["frames"] == int(round(duration * FPS)) and info["has_alpha"]


@needs_ffmpeg
def test_overlay_with_svg_and_png_icons(tmp_path):
    from video_automation.animations import render_overlay
    from video_automation.render_profiles import get_profile

    svg, png = _write_assets(tmp_path)
    for icon in (svg, png):
        out = tmp_path / f"icon_{icon.suffix[1:]}.mp4"
        info = render_overlay("LinearEquationOverlay", str(out), duration=3.0,
                              params={"ecuacion": "x + 5 = 0", "icono": str(icon)},
                              resolution=RES, fps=FPS, profile=get_profile("fast"))
        assert info["frames"] == 45


# ------------------------------------------------ sin LaTeX (dvisvgm roto)
@needs_ffmpeg
def test_overlays_survive_broken_dvisvgm(tmp_path, monkeypatch, caplog):
    """En Windows con MiKTeX, dvisvgm puede fallar: todo debe caer a texto plano, con UN aviso."""
    import logging

    import manim.utils.tex_file_writing as tfw

    from video_automation import manim_timing as mt
    from video_automation.animations import render_overlay
    from video_automation.render_profiles import get_profile

    def broken(*a, **k):
        raise ValueError("Your installation does not support converting .dvi files to SVG.")

    monkeypatch.setattr(tfw, "convert_to_svg", broken)
    monkeypatch.setattr(mt, "_latex_broken", False)
    monkeypatch.delenv("VA_STRICT_LATEX", raising=False)
    caplog.set_level(logging.WARNING)
    for scene, params in [
        ("GraphOverlay", {"funcion": [1, 9, 20], "x_range": [-7, -2, 1], "y_range": [-1, 6, 1]}),
        ("LinearEquationOverlay", {"ecuacion": "x + 4 = 0", "comprobar": True}),
    ]:
        monkeypatch.setattr(mt, "_latex_broken", False)     # GraphOverlay primero: falla en los ejes
        info = render_overlay(scene, str(tmp_path / f"{scene}.mov"), duration=3.0, params=params,
                              resolution=RES, fps=FPS, profile=get_profile("draft"))
        assert info["frames"] == 45
    avisos = [r for r in caplog.records if "LaTeX no funciona" in r.getMessage()]
    assert 1 <= len(avisos) <= 2                             # uno por render, no uno por fórmula


def test_latex_to_plain_is_readable():
    from video_automation.manim_timing import latex_to_plain

    assert latex_to_plain(r"\frac{2}{4} = \frac{4}{8}") == "2/4 = 4/8"
    assert latex_to_plain(r"\left(-4\right) + 4 = 0") == "(-4) + 4 = 0"
    assert latex_to_plain(r"(-4)^2 + 9(-4) + 20") == "(-4)² + 9(-4) + 20"
    assert latex_to_plain(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}") == "x = (-b ± √(b² - 4ac))/2a"


@needs_ffmpeg
def test_plain_text_fallback_is_not_cached(tmp_path, monkeypatch):
    """Un overlay hecho sin LaTeX no se guarda en caché: al arreglar LaTeX se regenera."""
    import manim.utils.tex_file_writing as tfw

    from video_automation import manim_timing as mt
    from video_automation.animations import render_overlay
    from video_automation.render_profiles import get_profile

    monkeypatch.setattr(tfw, "convert_to_svg", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("Your installation does not support converting .dvi files to SVG.")))
    monkeypatch.setattr(mt, "_latex_broken", False)
    monkeypatch.delenv("VA_STRICT_LATEX", raising=False)
    out = tmp_path / "f.mov"
    render_overlay("FormulaOverlay", str(out), duration=2.0, params={"formula": "x = 1"},
                   resolution=RES, fps=FPS, profile=get_profile("draft"), use_cache=True)
    assert out.exists() and not (tmp_path / "f.mov.key").exists()
