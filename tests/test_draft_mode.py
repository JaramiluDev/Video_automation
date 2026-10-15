"""
Pruebas del modo borrador --draft (HG): 480p / ≤15 fps para iterar vistas previas.

- Rápidas (siempre): --draft se acepta en TODAS las entradas (CLI del
  pipeline, render_profiles, math_animator, scripts de Manim) y equivale a
  --fast; $VA_QUALITY también decide la calidad de math_animator.
- De render (requieren ffmpeg/ffprobe): la concatenación no pide cuadros
  inexistentes cuando la duración no cae en la rejilla de 15 fps (9.5 s →
  142 cuadros) y el video final conserva round(suma × fps) cuadros.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from video_automation.render_profiles import add_quality_arguments, get_profile, profile_from_args

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="requiere ffmpeg/ffprobe")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("VA_QUALITY", raising=False)
    monkeypatch.delenv("VA_THREADS", raising=False)
    monkeypatch.setenv("VA_NO_NICE", "1")
    monkeypatch.setenv("VA_CACHE_DIR", str(tmp_path / "cache"))


# ------------------------------------------------------------ render_profiles
def test_draft_flag_is_fast_profile():
    ap = argparse.ArgumentParser()
    add_quality_arguments(ap)
    prof = profile_from_args(ap.parse_args(["--draft"]))
    assert prof.name == "fast"
    assert prof.resolve((1920, 1080), 30) == ((854, 480), 15)


@pytest.mark.parametrize("alias", ["draft", "borrador", "480p", "preview"])
def test_draft_aliases(alias):
    assert get_profile(alias).name == "fast"


def test_draft_is_exclusive_with_production():
    ap = argparse.ArgumentParser()
    add_quality_arguments(ap)
    with pytest.raises(SystemExit):
        ap.parse_args(["--draft", "--production"])


@pytest.mark.parametrize("module", ["src.video_automation.cli", "src.video_automation.math_animator"])
def test_module_help_survives_windows_encoding(module):
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    out = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, cwd=ROOT,
                         timeout=120, env=env)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")


def test_main_cli_render_accepts_draft():
    from video_automation.cli import build_parser

    args = build_parser().parse_args(["render", "--script", "x.yaml", "--draft"])
    assert profile_from_args(args).name == "fast"


@pytest.mark.parametrize("script", ["render_video2_scenes.py", "render_manim_clips.py",
                                    "build_zoomed_video.py"])
def test_scripts_list_draft_flag(script):
    # Como en Windows: la salida a un pipe usa cp1252 y la ayuda trae ≤, ←, ñ...
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"],
                         capture_output=True, cwd=ROOT, timeout=120, env=env)
    out.stdout = out.stdout.decode("utf-8", "replace")
    out.stderr = out.stderr.decode("utf-8", "replace")
    assert out.returncode == 0, out.stderr
    assert "--draft" in out.stdout


# --------------------------------------------------------------- math_animator
@pytest.mark.parametrize("argv,quality", [
    (["--draft"], "low"), (["--fast"], "low"), (["-ql"], "low"),
    (["--low-res"], "medium"), (["-qm"], "medium"),
    (["--production"], "high"), (["-qh"], "high"),
    (["--quality", "draft"], "low"), (["--quality", "720p"], "medium"),
])
def test_math_animator_quality_flags(argv, quality):
    from video_automation import math_animator as ma

    args = ma.build_parser().parse_args(["--config", "x.json", *argv])
    assert ma.resolve_quality(args.quality).name == quality


@pytest.mark.parametrize("env,quality", [
    (None, "low"), ("fast", "low"), ("draft", "low"), ("low-res", "medium"),
    ("production", "high"), ("high", "high"),
])
def test_math_animator_default_follows_va_quality(monkeypatch, env, quality):
    from video_automation import math_animator as ma

    if env is None:
        monkeypatch.delenv("VA_QUALITY", raising=False)
    else:
        monkeypatch.setenv("VA_QUALITY", env)
    assert ma.default_quality() == quality


def test_math_animator_medium_preset():
    from video_automation.math_animator import output_path_for, resolve_quality

    q = resolve_quality("medium")
    assert q.resolution == (1280, 720) and q.fps == 30
    assert output_path_for("demo", q).name == "demo_720p.mp4"


# ------------------------------------------------- concatenación en borrador
def _frames(path: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip())


def _clip_file(tmp_path: Path, name: str, frames: int, fps: int, color: str) -> Path:
    out = tmp_path / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:s=128x72:r={fps}", "-frames:v", str(frames),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


@needs_ffmpeg
def test_draft_concat_has_exact_frames_and_no_overread(tmp_path):
    """9.5 s a 15 fps → 142 cuadros; antes MoviePy leía el cuadro 142 inexistente."""
    from moviepy import VideoFileClip

    from video_automation.compositor import compose_clips
    from video_automation.heavy_render import _exact_clip

    fps = 15
    specs = [("a", 10.0, "red"), ("b", 9.5, "green"), ("c", 10.0, "blue"), ("d", 9.0, "white")]
    clips = []
    for name, dur, color in specs:
        f = _clip_file(tmp_path, name, int(round(dur * fps)), fps, color)
        clips.append(_exact_clip(VideoFileClip(str(f)), dur, fps))
    out = tmp_path / "final.mp4"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compose_clips(clips, str(out), fps=fps, resolution=(128, 72), profile=get_profile("fast"))
    overreads = [w for w in caught if "bytes wanted" in str(w.message)]
    assert not overreads, [str(w.message) for w in overreads]
    assert _frames(out) == sum(int(round(d * fps)) for _, d, _ in specs)  # 150+142+150+135


@needs_ffmpeg
@pytest.mark.parametrize("fps,durations", [(30, [5, 5, 5, 9.5, 10]), (15, [3.3, 2.2, 7.1])])
def test_compose_keeps_round_total_frames(tmp_path, fps, durations):
    from moviepy import ColorClip

    from video_automation.compositor import compose_clips

    clips = [ColorClip((64, 36), color=(40 * i, 0, 0), duration=d) for i, d in enumerate(durations)]
    out = tmp_path / "c.mp4"
    compose_clips(clips, str(out), fps=fps, resolution=(64, 36), profile=get_profile("fast"))
    assert _frames(out) == int(round(sum(durations) * fps))


# ------------------------------------------- composición de overlays con FFmpeg
PLACEHOLDER = str(ROOT / "data" / "assets" / "placeholder_1.png")


def _overlay_scene(**kw):
    from video_automation.models import Scene

    base = dict(id="E1", title="t", narration="", image_paths=[PLACEHOLDER, PLACEHOLDER], duration=3.1,
                manim_overlay="FormulaOverlay", manim_overlay_params={"formulas": ["x = 1", "x = 2"]})
    base.update(kw)
    return Scene(**base)


@needs_ffmpeg
@pytest.mark.parametrize("compositor", ["ffmpeg", "moviepy"])
def test_overlay_scene_exact_frames_with_both_compositors(tmp_path, monkeypatch, compositor):
    from video_automation.heavy_render import render_scene_overlay

    monkeypatch.setenv("VA_COMPOSITOR", compositor)
    clip = render_scene_overlay(_overlay_scene(), [None, None], (256, 144), 15, tmp_path,
                                profile=get_profile("fast"))
    assert clip.size == [256, 144] or tuple(clip.size) == (256, 144)
    assert abs(clip.duration - round(3.1 * 15) / 15) < 1e-6          # 46 cuadros
    scene_mp4 = tmp_path / "E1_scene.mp4"
    assert scene_mp4.exists() == (compositor == "ffmpeg")
    if compositor == "ffmpeg":
        assert _frames(scene_mp4) == 46


@needs_ffmpeg
def test_ffmpeg_compositor_keeps_timing_with_missing_image_and_uses_cache(tmp_path, monkeypatch):
    from video_automation.heavy_render import render_scene_overlay

    monkeypatch.delenv("VA_COMPOSITOR", raising=False)
    scene = _overlay_scene(image_paths=[PLACEHOLDER, str(tmp_path / "no_existe.png")], duration=2.0)
    render_scene_overlay(scene, [None, None], (256, 144), 15, tmp_path, profile=get_profile("fast"),
                         use_cache=True)
    out = tmp_path / "E1_scene.mp4"
    assert _frames(out) == 30 and (tmp_path / "E1_scene.mp4.key").exists()
    mtime = out.stat().st_mtime_ns
    render_scene_overlay(scene, [None, None], (256, 144), 15, tmp_path, profile=get_profile("fast"),
                         use_cache=True)
    assert out.stat().st_mtime_ns == mtime        # misma clave: no se recompone


@needs_ffmpeg
def test_lazy_clip_opens_reader_only_while_playing(tmp_path, monkeypatch):
    import moviepy
    import numpy as np
    from moviepy import VideoFileClip

    from video_automation.compositor import lazy_video_clip

    src = _clip_file(tmp_path, "s", 30, 15, "red")
    opened, closed = [], []

    class Spy(VideoFileClip):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            opened.append(1)

        def close(self):
            closed.append(1)
            super().close()

    monkeypatch.setattr(moviepy, "VideoFileClip", Spy)
    clip = lazy_video_clip(str(src), 2.0, 15)
    assert len(opened) == len(closed) == 1           # solo se abrió para leer el tamaño
    assert tuple(clip.size) == (128, 72) and abs(clip.duration - 2.0) < 1e-9
    ref = VideoFileClip(str(src))
    assert np.array_equal(clip.get_frame(0.5), ref.get_frame(0.5))
    assert len(opened) == 2 and len(closed) == 1     # lector vivo mientras se reproduce
    clip.get_frame(29 / 15)                           # último cuadro → se cierra
    assert len(closed) == 2
    ref.close()
