"""
Pruebas de la sincronización del video base con el audio multi-voz (HG).

Antes: 36 imágenes × 5 s = 3:00 contra ~21 min de audio, y `-shortest`
cortaba el episodio. Ahora cada escena dura lo que su *_consolidated.mp3 y el
total empata con <guion>_audio.mp3 cuadro a cuadro.
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from video_automation.heavy_render import (
    AudioSyncError,
    apply_audio_sync,
    default_dialogues_dir,
    default_images_root,
    find_scene_audio,
    fmt_hms,
    frames_for_durations,
    image_seconds,
    plan_audio_sync,
    probe_duration,
    probe_frame_count,
    render_audio_synced_base,
    resolve_scene_images,
    split_scene_frames,
)
from video_automation.models import OutputSettings, Scene, ScriptDefinition
from video_automation.render_profiles import get_profile

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="requiere ffmpeg/ffprobe")


# ---------------------------------------------------------------------------
# Reparto de cuadros (sin ffmpeg)
# ---------------------------------------------------------------------------

def test_frames_for_durations_sum_is_exact_and_no_drift():
    durs = [105.74, 108.84, 99.5, 110.98, 106.87, 104.76, 110.52, 109.92, 105.29, 103.99, 114.55, 90.77]
    for fps in (15, 24, 30, 60):
        frames = frames_for_durations(durs, fps)
        assert sum(frames) == round(sum(durs) * fps)
        # Ningún corte acumulado se aleja más de medio cuadro del tiempo real.
        acc_t, acc_f = 0.0, 0
        for d, f in zip(durs, frames):
            acc_t += d
            acc_f += f
            assert abs(acc_f / fps - acc_t) <= 0.5 / fps + 1e-9


def test_frames_for_durations_scales_to_episode_total():
    durs = [10.0, 20.0, 30.0]
    frames = frames_for_durations(durs, 30, total_frames=1803)
    assert sum(frames) == 1803
    assert frames[2] > frames[1] > frames[0]


def test_frames_for_durations_gives_at_least_one_frame():
    frames = frames_for_durations([0.0, 0.001, 5.0], 30)
    assert all(f >= 1 for f in frames)
    assert sum(frames) == 150


def test_split_scene_frames_equal_parts():
    assert split_scene_frames(90, 3, 30) == [30, 30, 30]
    out = split_scene_frames(100, 3, 30)
    assert sum(out) == 100 and max(out) - min(out) <= 1
    assert split_scene_frames(7, 1, 30) == [7]
    assert sum(split_scene_frames(2, 3, 30)) == 2


def test_split_scene_frames_snaps_to_turn_changes():
    # Escena de 30 s a 30 fps con turnos de 8 + 11 + 11 s: los cortes ideales
    # (10 s y 20 s) se mueven a los cambios de voz (8 s y 19 s).
    out = split_scene_frames(900, 3, 30, turn_durations=[8.0, 11.0, 11.0])
    assert out == [240, 330, 330]


def test_split_scene_frames_ignores_far_turns():
    # El único cambio de turno está muy lejos del corte ideal: se queda el ideal.
    out = split_scene_frames(900, 2, 30, turn_durations=[1.0, 29.0])
    assert out == [450, 450]


def test_split_scene_frames_random_invariants():
    rng = random.Random(3)
    for _ in range(300):
        total = rng.randint(1, 5000)
        n = rng.randint(1, 6)
        turns = [rng.uniform(0.2, 20) for _ in range(rng.randint(0, 15))]
        out = split_scene_frames(total, n, 30, turn_durations=turns or None)
        assert len(out) == n
        assert sum(out) == total
        if total >= n:
            assert all(f >= 1 for f in out)


def test_image_seconds_is_frame_exact():
    scene = Scene(id="e1", title="t", image_paths=["a", "b", "c"], duration=10.0)
    secs = image_seconds(scene, 30)
    assert len(secs) == 3
    assert round(sum(secs) * 30) == 300
    assert all(abs(s * 30 - round(s * 30)) < 1e-9 for s in secs)


def test_fmt_hms():
    assert fmt_hms(1271.064) == "21:11.064"
    assert fmt_hms(3725.5) == "1:02:05.500"


# ---------------------------------------------------------------------------
# Convenciones de archivos (sin ffmpeg)
# ---------------------------------------------------------------------------

def test_default_dialogues_dir_matches_narrator_convention():
    assert default_dialogues_dir("data/output/GUION-02_audio.mp3") == \
        Path("data/output/GUION-02_audio_dialogues")


def test_find_scene_audio_layouts(tmp_path):
    nested = tmp_path / "escena_01" / "escena_01_consolidated.mp3"
    nested.parent.mkdir()
    nested.write_bytes(b"x")
    flat = tmp_path / "escena_02_consolidated.wav"
    flat.write_bytes(b"x")
    deep = tmp_path / "otra" / "escena_03_consolidated.mp3"
    deep.parent.mkdir()
    deep.write_bytes(b"x")
    empty = tmp_path / "escena_04" / "escena_04_consolidated.mp3"
    empty.parent.mkdir()
    empty.write_bytes(b"")
    assert find_scene_audio("escena_01", tmp_path) == nested
    assert find_scene_audio("escena_02", tmp_path) == flat
    assert find_scene_audio("escena_03", tmp_path) == deep
    assert find_scene_audio("escena_04", tmp_path) is None
    assert find_scene_audio("escena_01", None) is None


def test_resolve_scene_images_from_numbered_folders(tmp_path):
    for name in ("ESCENA-01", "ESCENA-02", "ESCENA-10"):
        d = tmp_path / name
        d.mkdir()
        for img in ("img (10).png", "img (2).png", "img (1).png", "nota.txt"):
            (d / img).write_bytes(b"x")
    s1 = Scene(id="escena_01", title="a")
    s10 = Scene(id="escena_10", title="b")
    imgs = resolve_scene_images(s1, 0, tmp_path)
    assert [Path(p).name for p in imgs] == ["img (1).png", "img (2).png", "img (10).png"]
    assert Path(resolve_scene_images(s10, 9, tmp_path)[0]).parent.name == "ESCENA-10"
    # image_paths del YAML mandan sobre la carpeta
    s = Scene(id="escena_01", title="a", image_paths=["x.png"])
    assert resolve_scene_images(s, 0, tmp_path) == ["x.png"]
    assert resolve_scene_images(Scene(id="escena_05", title="c"), 4, tmp_path) == []


def test_default_images_root(tmp_path):
    script = tmp_path / "GUION-02.yaml"
    script.write_text("scenes: []", encoding="utf-8")
    (tmp_path / "GUION-02" / "ESCENA-01").mkdir(parents=True)
    assert default_images_root(script) == tmp_path / "GUION-02"


def test_resolve_script_path_prefers_multivoice_yaml(tmp_path):
    from video_automation.pipeline import resolve_script_path

    (tmp_path / "GUION-02").mkdir()
    (tmp_path / "GUION-02" / "GUION-02.yaml").write_text("scenes: []", encoding="utf-8")
    assert resolve_script_path("GUION-02", base=tmp_path) == (tmp_path / "GUION-02" / "GUION-02.yaml").resolve()
    (tmp_path / "GUION-02.yaml").write_text("scenes: []", encoding="utf-8")
    assert resolve_script_path("GUION-02", base=tmp_path) == (tmp_path / "GUION-02.yaml").resolve()


# ---------------------------------------------------------------------------
# Con audio real (ffmpeg)
# ---------------------------------------------------------------------------

def _tone(path: Path, seconds: float, freq: int = 440) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=f={freq}:d={seconds}:sample_rate=24000",
                    "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", str(path)], check=True)
    return path


def _concat(parts, out: Path) -> Path:
    from video_automation.narrator import concatenate_audio_files

    assert concatenate_audio_files(parts, out)
    return out


def _png(path: Path, color: str) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), color).save(path)


@pytest.fixture
def episode(tmp_path):
    """Episodio de 3 escenas (2 imágenes c/u) con audio multi-voz sintético."""
    out = tmp_path / "output"
    dialogues = out / "EP_audio_dialogues"
    turns = {"escena_01": [1.0, 1.5], "escena_02": [0.8, 0.9, 1.6], "escena_03": [1.2]}
    scene_audio = []
    for sid, lens in turns.items():
        files = [_tone(dialogues / sid / f"turn_{i:02d}_X.mp3", d, 300 + 100 * i)
                 for i, d in enumerate(lens, 1)]
        scene_audio.append(_concat(files, dialogues / sid / f"{sid}_consolidated.mp3"))
    episode_audio = _concat(scene_audio, out / "EP_audio.mp3")
    images = tmp_path / "EP"
    for n, color in ((1, "red"), (2, "green"), (3, "blue")):
        _png(images / f"ESCENA-{n:02d}" / "a.png", color)
        _png(images / f"ESCENA-{n:02d}" / "b.png", "white")
    script = ScriptDefinition(
        title="EP", output_filename="ep.mp4",
        output_settings=OutputSettings(resolution=(320, 180), fps=10),
        scenes=[Scene(id=sid, title=sid, duration=5.0) for sid in turns],
    )
    return {"script": script, "audio": episode_audio, "dialogues": dialogues,
            "images": images, "out": out}


@needs_ffmpeg
def test_plan_uses_real_audio_not_yaml_duration(episode):
    plan = plan_audio_sync(episode["script"], 10, episode_audio=episode["audio"],
                           images_root=episode["images"])
    ep_secs = probe_duration(episode["audio"])
    assert plan.total_frames == round(ep_secs * 10)
    assert [s.source for s in plan.scenes] == ["audio"] * 3
    # Las escenas duran lo que su audio (≈2.5 / 3.3 / 1.2 s), no los 5 s del YAML.
    for s in plan.scenes:
        assert abs(s.seconds(10) - s.audio_seconds) < 0.25
        assert len(s.image_paths) == 2 and sum(s.image_frames) == s.frames
    assert plan.scenes[0].turns == 2
    assert "TOTAL" in plan.table()
    json.dumps(plan.to_dict())


@needs_ffmpeg
def test_plan_missing_audio_is_an_error_unless_allowed(episode):
    shutil.rmtree(episode["dialogues"] / "escena_02")
    with pytest.raises(AudioSyncError, match="escena_02"):
        plan_audio_sync(episode["script"], 10, dialogues_dir=episode["dialogues"])
    plan = plan_audio_sync(episode["script"], 10, dialogues_dir=episode["dialogues"], strict=False)
    assert plan.scenes[1].source == "yaml"
    assert plan.scenes[1].frames == 50
    assert plan.warnings


@needs_ffmpeg
def test_apply_audio_sync_updates_durations(episode):
    plan = plan_audio_sync(episode["script"], 10, episode_audio=episode["audio"],
                           images_root=episode["images"])
    synced = apply_audio_sync(episode["script"], plan)
    assert [round(s.duration * 10) for s in synced.scenes] == [s.frames for s in plan.scenes]
    assert all(len(s.image_paths) == 2 for s in synced.scenes)
    assert episode["script"].scenes[0].duration == 5.0  # el original no cambia


@needs_ffmpeg
@pytest.mark.parametrize("ken_burns", [True, False])
def test_render_synced_base_matches_audio_frame_exact(episode, ken_burns):
    prof = get_profile("production")
    out = render_audio_synced_base(episode["script"], episode["out"] / "EP_base.mp4",
                                   episode_audio=episode["audio"], images_root=episode["images"],
                                   profile=prof, ken_burns=ken_burns, jobs=2)
    ep_secs = probe_duration(episode["audio"])
    assert probe_frame_count(out) == round(ep_secs * 10)
    assert abs(probe_duration(out) - ep_secs) <= 1 / 10
    report = json.loads(out.with_suffix(".sync.json").read_text(encoding="utf-8"))
    assert report["total_frames"] == round(ep_secs * 10)
    assert len(report["scenes"]) == 3


@needs_ffmpeg
def test_render_synced_base_with_muxed_audio_and_cache(episode):
    prof = get_profile("production")
    kwargs = dict(episode_audio=episode["audio"], images_root=episode["images"],
                  profile=prof, ken_burns=False, mux_audio=True)
    out = render_audio_synced_base(episode["script"], episode["out"] / "EP_base.mp4", **kwargs)
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                              "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.split()
    assert streams == ["video", "audio"]
    clips = sorted((episode["out"] / "base_clips").glob("*.mp4"))
    assert len(clips) == 6
    mtimes = [c.stat().st_mtime_ns for c in clips]
    render_audio_synced_base(episode["script"], episode["out"] / "EP_base.mp4", **kwargs)
    assert [c.stat().st_mtime_ns for c in clips] == mtimes  # caché: no se regeneran


@needs_ffmpeg
def test_fast_profile_tags_output(episode):
    out = render_audio_synced_base(episode["script"], episode["out"] / "EP_base.mp4",
                                   episode_audio=episode["audio"], images_root=episode["images"],
                                   profile=get_profile("fast"), ken_burns=False)
    assert out.name == "EP_base_fast.mp4"
    assert (episode["out"] / "base_clips_fast").is_dir()


@needs_ffmpeg
def test_synced_base_with_overlay_scene_uses_render_video(episode, monkeypatch):
    """Si una escena trae overlay Manim, el base sale de render_video con los tiempos del audio."""
    pytest.importorskip("manim")
    monkeypatch.delenv("VA_COMPOSITOR", raising=False)
    script = episode["script"]
    scenes = list(script.scenes)
    scenes[0] = scenes[0].model_copy(update={
        "manim_overlay": "FormulaOverlay",
        "manim_overlay_params": {"formulas": ["x = 1", "x = 2"]},
    })
    script = script.model_copy(update={"scenes": scenes})
    out = render_audio_synced_base(script, episode["out"] / "EP_base.mp4",
                                   episode_audio=episode["audio"], images_root=episode["images"],
                                   profile=get_profile("production"), ken_burns=False)
    ep_secs = probe_duration(episode["audio"])
    assert probe_frame_count(out) == round(ep_secs * 10)
