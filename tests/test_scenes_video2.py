"""
Pruebas del entregable "Animaciones matemáticas del Video 2".

- Rápidas (siempre): matemáticas de fracciones/dominó, planeación de cuadros
  y registro de escenas.
- De render (lentas): renderizan a baja resolución y verifican con ffprobe que
  el número de cuadros sea EXACTAMENTE round(duration * fps). Se saltan si no
  hay ffmpeg; si no hay LaTeX, corren con fallback a Text salvo que
  VA_STRICT_LATEX=1 (Docker), donde LaTeX es obligatorio.
"""

import shutil

import pytest

from video_automation.fracciones import (
    NIVELES, are_equivalent, cross_products, eulerian_chain, expected_tile_count,
    generate_tiles, parse_fraction, representation_for, simplify, validate_chain,
)
from video_automation.manim_timing import plan_frames

import random


# --------------------------------------------------------------- fracciones
def test_parse_fraction_formats():
    assert parse_fraction("2/4") == (2, 4)
    assert parse_fraction(" 3 / 8 ") == (3, 8)
    assert parse_fraction([1, 2]) == (1, 2)


@pytest.mark.parametrize("bad", ["4/2", "0/3", "2/0", "abc", "1/1"])
def test_parse_fraction_rejects_non_proper(bad):
    with pytest.raises(ValueError):
        parse_fraction(bad)


def test_cross_products_from_guion():
    # Escena 2 · Imagen 6: 2/4 = 4/8 porque 2 × 8 = 4 × 4
    assert cross_products((2, 4), (4, 8)) == (16, 16)
    assert are_equivalent((2, 4), (4, 8))
    # Escena 9 · Imagen 27: 2/4 ≠ 2/8
    assert cross_products((2, 4), (2, 8)) == (16, 8)
    assert not are_equivalent((2, 4), (2, 8))
    assert simplify((4, 8)) == (1, 2)


@pytest.mark.parametrize("nivel,esperado", [("inicial", 15), ("intermedio", 28), ("avanzado", 45)])
def test_tile_counts_match_guion(nivel, esperado):
    fams = NIVELES[nivel]
    tiles = generate_tiles(fams)
    assert len(tiles) == esperado == expected_tile_count(len(fams))
    assert len(set(tiles)) == len(tiles)  # sin parejas duplicadas


@pytest.mark.parametrize("nivel", list(NIVELES))
def test_complete_chain_uses_every_tile_once(nivel):
    fams = NIVELES[nivel]
    tiles = generate_tiles(fams)
    chain = eulerian_chain(len(fams), tiles)
    assert validate_chain(chain, tiles, len(tiles))


def test_representations_respect_limits():
    rng = random.Random("AULA-2026")
    for nivel, fams in NIVELES.items():
        for fam in fams:
            for _ in range(30):
                rep = representation_for(fam, nivel, rng, "mixto", "variadas")
                assert are_equivalent(fam, (rep.num, rep.den))
                if rep.kind != "frac":
                    assert rep.den <= 16


# --------------------------------------------------------- plan de cuadros
@pytest.mark.parametrize("duration", [3.0, 7.37, 9.5, 12.0, 30.0])
@pytest.mark.parametrize("fps", [30, 60])
def test_plan_frames_sums_exactly(duration, fps):
    beats = [("anim", 0.8), ("anim", 1.2), ("hold", 1.0), ("anim", 0.6), ("hold", 2.0)]
    frames = plan_frames(beats, duration, fps)
    assert sum(frames) == round(duration * fps)
    assert all(f >= 1 for f, (k, _) in zip(frames, beats) if k == "anim")


def test_plan_frames_stretches_holds_not_animations():
    beats = [("anim", 1.0), ("hold", 1.0), ("anim", 1.0)]
    frames = plan_frames(beats, 10.0, 30)
    assert frames[0] == 30 and frames[2] == 30   # animaciones a velocidad nominal
    assert frames[1] == 240                      # la pausa absorbe el excedente


def test_plan_frames_compresses_everything_when_short():
    beats = [("anim", 2.0), ("hold", 2.0)]
    frames = plan_frames(beats, 2.0, 30)
    assert frames == [30, 30]


# ---------------------------------------------------------------- registro
def test_registry_has_all_video2_scenes():
    from video_automation.scenes_video2 import SCENE_REGISTRY
    from video_automation.manim_timing import TimedScene, get_scene_class

    assert len(SCENE_REGISTRY) == 10
    for name, cls in SCENE_REGISTRY.items():
        assert issubclass(cls, TimedScene)
        assert get_scene_class(name) is cls
    with pytest.raises(KeyError):
        get_scene_class("NoExiste")


def test_example_yaml_parses_and_references_registered_scenes():
    from video_automation.script_parser import parse_script
    from video_automation.heavy_render import validate_manim_scenes

    script = parse_script("examples/video2_manim.yaml")
    assert len(script.scenes) == 10
    validate_manim_scenes(script)  # no lanza


# ------------------------------------------------------------ render real
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requiere ffmpeg")


@needs_ffmpeg
@pytest.mark.parametrize("fps,duration", [(30, 4.37), (60, 3.0)])
def test_render_exact_frame_count(tmp_path, fps, duration):
    from video_automation.manim_timing import probe_video, render_timed_scene

    out = render_timed_scene("V2E02_ProductosCruzados", str(tmp_path / "c.mp4"), duration=duration,
                             resolution=(426, 240), fps=fps)
    info = probe_video(out)
    assert info["frames"] == round(duration * fps)
    assert (info["width"], info["height"]) == (426, 240)
    assert info["codec"] == "h264" and info["pix_fmt"] == "yuv420p"
    assert abs(info["avg_fps"] - fps) < 0.01


@needs_ffmpeg
def test_heavy_render_uses_registered_scene_and_duration(tmp_path):
    from video_automation.heavy_render import render_manim_scene
    from video_automation.models import Scene

    scene = Scene(id="T-01", title="t", narration="", image_paths=[], duration=2.5,
                  render_type="manim", manim_scene="V2E12_CierreRecorrido")
    clip = render_manim_scene(scene, resolution=(426, 240), fps=30, clips_dir=str(tmp_path))
    try:
        assert round(clip.duration * 30) == 75
        assert tuple(clip.size) == (426, 240)
    finally:
        clip.close()
