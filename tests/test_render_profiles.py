"""
Pruebas de los perfiles de calidad (--fast / --low-res / --production) y de la
integración de overlays Manim en heavy_render.

- Rápidas (siempre): resolución/fps por perfil, flags de CLI, argumentos de
  FFmpeg, sufijos de salida y que heavy_render/compositor reciban el perfil.
- De render (requieren ffmpeg): caché de clips Manim, FormulaOverlay con alfa
  y un render completo imagen + overlay con el perfil fast.
"""

import argparse
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_automation.render_profiles import (
    add_quality_arguments, get_profile, profile_from_args,
)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="requiere ffmpeg")
PLACEHOLDER = "data/assets/placeholder_1.png"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("VA_QUALITY", raising=False)
    monkeypatch.delenv("VA_THREADS", raising=False)
    monkeypatch.setenv("VA_NO_NICE", "1")             # no bajar la prioridad de pytest
    monkeypatch.setenv("VA_CACHE_DIR", str(tmp_path / "cache"))


# ------------------------------------------------------------ resolución/fps
@pytest.mark.parametrize("name,expected", [
    ("fast", ((854, 480), 15)),
    ("low-res", ((1280, 720), 30)),
    ("production", ((1920, 1080), 30)),
])
def test_profiles_scale_1080p30(name, expected):
    assert get_profile(name).resolve((1920, 1080), 30) == expected


def test_fast_keeps_aspect_ratio_and_even_dims_for_vertical_video():
    (w, h), fps = get_profile("fast").resolve((1080, 1920), 60)
    assert (w, h) == (480, 854) and fps == 15
    assert w % 2 == 0 and h % 2 == 0


def test_profiles_never_upscale():
    assert get_profile("low-res").resolve((640, 360), 24) == ((640, 360), 24)
    assert get_profile("production").resolve((1280, 720), 60) == ((1280, 720), 60)


def test_aliases_env_and_unknown(monkeypatch):
    assert get_profile("preview").name == "fast"
    assert get_profile("720p").name == "low-res"
    assert get_profile("final").name == "production"
    assert get_profile(None).name == "production"
    monkeypatch.setenv("VA_QUALITY", "fast")
    assert get_profile(None).name == "fast"
    with pytest.raises(ValueError):
        get_profile("ultra")


# ---------------------------------------------------------------- FFmpeg args
def test_x264_args_and_threads(monkeypatch):
    fast = get_profile("fast")
    assert fast.x264_args() == ["-preset", "ultrafast", "-crf", "30", "-threads", "2"]
    prod = get_profile("production")
    assert prod.x264_args() == ["-preset", "medium", "-crf", "18"]    # hilos automáticos
    monkeypatch.setenv("VA_THREADS", "3")
    assert prod.thread_count == 3
    kw = fast.moviepy_write_kwargs()
    assert kw["preset"] == "ultrafast" and kw["threads"] == 3 and "-crf" in kw["ffmpeg_params"]


def test_low_res_uses_half_the_cores(monkeypatch):
    monkeypatch.setattr("video_automation.render_profiles.os.cpu_count", lambda: 8)
    assert get_profile("low-res").thread_count == 4


def test_tag_paths_only_outside_production():
    assert get_profile("fast").tag_path("data/renders/v.mp4") == Path("data/renders/v_fast.mp4")
    assert get_profile("low-res").tag_dir("out/manim_clips") == Path("out/manim_clips_lowres")
    assert get_profile("production").tag_path("v.mp4") == Path("v.mp4")
    assert get_profile("fast").tag_path("v_fast.mp4") == Path("v_fast.mp4")   # no duplica


# ----------------------------------------------------------------------- CLI
def _parser(preview=False):
    ap = argparse.ArgumentParser()
    add_quality_arguments(ap, preview_alias=preview)
    return ap


@pytest.mark.parametrize("argv,name", [
    ([], "production"), (["--fast"], "fast"), (["--low-res"], "low-res"),
    (["--production"], "production"), (["--quality", "draft"], "fast"),
])
def test_quality_flags(argv, name):
    assert profile_from_args(_parser().parse_args(argv)).name == name


def test_quality_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--fast", "--production"])


def test_preview_alias_and_explicit_threads_win_over_env(monkeypatch):
    monkeypatch.setenv("VA_THREADS", "6")
    prof = profile_from_args(_parser(preview=True).parse_args(["--preview", "--threads", "1"]))
    assert prof.name == "fast" and prof.thread_count == 1


def test_main_cli_render_accepts_quality_and_cache_flags():
    from video_automation.cli import build_parser

    args = build_parser().parse_args(["render", "--script", "x.yaml", "--fast", "--no-cache"])
    assert args.quality == "fast" and args.no_cache is True
    assert args.fps is None and args.resolution is None   # el guion manda si no se dan


def test_parse_resolution():
    from video_automation.pipeline import parse_resolution

    assert parse_resolution("1280x720") == (1280, 720)
    assert parse_resolution(None) is None
    with pytest.raises(ValueError):
        parse_resolution("720p")


# ------------------------------------------------------------- heavy_render
def _script(**kw):
    from video_automation.models import OutputSettings, Scene, ScriptDefinition

    scenes = kw.pop("scenes", None) or [Scene(id="E1", title="t", narration="", image_paths=[PLACEHOLDER],
                                              duration=2.0)]
    return ScriptDefinition(title="T", scenes=scenes, output_filename="out.mp4",
                            output_settings=kw.pop("settings", OutputSettings()), **kw)


def test_render_video_applies_fast_profile_and_tags_output(tmp_path):
    from video_automation.heavy_render import render_video

    with patch("video_automation.heavy_render.compose_clips") as compose, \
         patch("video_automation.heavy_render.build_image_clip") as build:
        build.return_value = MagicMock()
        compose.return_value = "x"
        render_video(_script(), str(tmp_path), profile=get_profile("fast"))

    args, kwargs = compose.call_args
    assert kwargs["resolution"] == (854, 480) and kwargs["fps"] == 15
    assert kwargs["profile"].name == "fast"
    assert Path(args[1]).name == "out_fast.mp4"
    build.assert_called_once_with(PLACEHOLDER, 2.0, (854, 480))


def test_render_video_cli_overrides_then_profile_scales(tmp_path):
    from video_automation.heavy_render import render_video

    with patch("video_automation.heavy_render.compose_clips") as compose, \
         patch("video_automation.heavy_render.build_image_clip", return_value=MagicMock()):
        render_video(_script(), str(tmp_path), profile=get_profile("low-res"),
                     resolution=(3840, 2160), fps=60)
    _, kwargs = compose.call_args
    assert kwargs["resolution"] == (1280, 720) and kwargs["fps"] == 30


def test_validate_rejects_unknown_overlay_and_overlay_on_manim_scene():
    from video_automation.heavy_render import validate_manim_scenes
    from video_automation.models import Scene

    bad = Scene(id="E1", title="t", narration="", image_paths=[PLACEHOLDER], duration=2,
                manim_overlay="NoExiste")
    with pytest.raises(KeyError):
        validate_manim_scenes(_script(scenes=[bad]))
    wrong = Scene(id="E2", title="t", narration="", image_paths=[], duration=2, render_type="manim",
                  manim_overlay="FormulaOverlay")
    with pytest.raises(ValueError):
        validate_manim_scenes(_script(scenes=[wrong]))


def test_overlay_params_align_segments_with_images():
    from video_automation.heavy_render import overlay_params
    from video_automation.models import Scene

    f = Scene(id="E1", title="t", narration="", image_paths=["a", "b"], duration=8,
              manim_overlay="FormulaOverlay", manim_overlay_params={"formula": "x"})
    assert overlay_params(f, [4.0, 4.0])["tramos"] == [4.0, 4.0]
    # Scene02Math tiene 3 tramos fijos: con 3 imágenes se alinean, con 2 no se fuerzan.
    s3 = Scene(id="E2", title="t", narration="", image_paths=["a", "b", "c"], duration=15,
               manim_overlay="Scene02Math")
    assert overlay_params(s3, [5.0, 5.0, 5.0])["tramos"] == [5.0, 5.0, 5.0]
    assert "tramos" not in overlay_params(s3, [7.5, 7.5])


def test_manim_registry_includes_overlays():
    from video_automation.animations.math_scenes import FormulaOverlay
    from video_automation.manim_timing import get_scene_class

    assert get_scene_class("FormulaOverlay") is FormulaOverlay


def test_ken_burns_receives_profile_encode_args(tmp_path):
    from video_automation import simple_animator

    with patch.object(simple_animator.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0)
        simple_animator.create_ken_burns_clip(Path(PLACEHOLDER), tmp_path / "c.mp4", True,
                                              duration=5, fps=15, width=854, height=480,
                                              encode_args=get_profile("fast").x264_args())
    cmd = run.call_args[0][0]
    assert cmd[cmd.index("-preset") + 1] == "ultrafast"
    assert "854x480" in " ".join(cmd) and cmd[cmd.index("-r") + 1] == "15"


# ------------------------------------------------------------ render real
@needs_ffmpeg
def test_manim_clip_cache_skips_rerender(tmp_path):
    from video_automation.manim_timing import render_timed_scene

    fast = get_profile("fast")
    out = tmp_path / "c.mp4"
    kw = dict(duration=1.0, resolution=(320, 180), fps=15, profile=fast, use_cache=True)
    render_timed_scene("V2E12_CierreRecorrido", str(out), **kw)
    assert (tmp_path / "c.mp4.key").exists()
    first = out.stat().st_mtime_ns

    with patch("video_automation.manim_timing.normalize_clip") as norm:
        render_timed_scene("V2E12_CierreRecorrido", str(out), **kw)
        norm.assert_not_called()                       # vino de la caché
    assert out.stat().st_mtime_ns == first

    kw["duration"] = 1.2                               # otra duración → otra clave
    render_timed_scene("V2E12_CierreRecorrido", str(out), **kw)
    assert out.stat().st_mtime_ns != first


@needs_ffmpeg
def test_formula_overlay_alpha_exact_frames(tmp_path):
    from video_automation.animations import render_overlay

    info = render_overlay("FormulaOverlay", str(tmp_path / "f.mov"), duration=2.0,
                          params={"formulas": [r"\frac{2}{4}", r"2 \times 8 = 16"], "titulo": "Prueba",
                                  "tramos": [1.0, 1.0]},
                          resolution=(320, 180), fps=15, profile=get_profile("fast"))
    assert info["frames"] == 30 and info["has_alpha"]
    assert (info["width"], info["height"]) == (320, 180)


@needs_ffmpeg
def test_render_video_images_with_overlay_fast(tmp_path):
    from video_automation.heavy_render import render_video
    from video_automation.manim_timing import probe_video
    from video_automation.models import OutputSettings, Scene

    scenes = [
        Scene(id="E1", title="t", narration="", image_paths=[PLACEHOLDER, PLACEHOLDER], duration=2.0,
              manim_overlay="FormulaOverlay",
              manim_overlay_params={"formulas": ["a^2 + b^2 = c^2", r"\frac{1}{2}"]}),
        Scene(id="E2", title="t", narration="", image_paths=[], duration=1.0, render_type="manim",
              formula="x = 1"),
    ]
    script = _script(scenes=scenes, settings=OutputSettings(resolution=(640, 360), fps=30))
    result = render_video(script, str(tmp_path), profile=get_profile("fast"))
    assert Path(result).name == "out_fast.mp4"
    info = probe_video(result)
    assert (info["width"], info["height"]) == (640, 360)   # lado corto 360 < 480: fast no reescala
    assert abs(info["avg_fps"] - 15) < 0.01
    assert abs(info["duration"] - 3.0) < 0.15
    assert (tmp_path / "manim_clips_fast" / "E1_overlay.mov").exists()
