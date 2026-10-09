"""
Pruebas de math_animator.py (Módulo Visual y Animaciones Dinámicas — HG).

- Rápidas (siempre): lectura/validación de la configuración JSON/YAML/dict,
  calidades low/high, rutas de salida y CLI (con el render simulado).
- De render (requieren Manim + ffprobe): genera un MP4 real en modo low y
  verifica resolución, fps, duración y que el archivo quede en la carpeta de
  salida.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from video_automation import math_animator as ma
from video_automation.math_animator import (
    CHANNEL_BG, DEFAULT_OUTPUT_DIR, MathSceneConfig, SceneConfigError,
    load_scene_config, output_path_for, render_scene_from_config, resolve_quality,
)

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "scenes" / "sample_math.json"
needs_ffprobe = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="requiere ffprobe")


def base_config(**overrides: Any) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "latex_expressions": ["a^2 + b^2 = c^2", "c = \\sqrt{a^2 + b^2}"],
        "text_labels": [{"text": "Teorema de Pitágoras", "position": "UP"}],
        "duration": 1.0,
        "animation_time": 0.5,
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VA_NO_NICE", "1")                      # no bajar la prioridad de pytest
    monkeypatch.setenv("VA_CACHE_DIR", str(tmp_path / "cache"))


# ------------------------------------------------------------- configuración
def test_sample_config_is_valid() -> None:
    cfg = load_scene_config(SAMPLE)
    assert len(cfg.latex_expressions) == 4
    assert cfg.background_color == CHANNEL_BG
    assert [cfg.animation_for(i) for i in range(4)] == ["write", "transform", "transform", "fadein"]
    assert cfg.total_duration() == pytest.approx(11.5)


def test_load_from_json_file(tmp_path: Path) -> None:
    path = tmp_path / "escena.json"
    path.write_text(json.dumps(base_config()), encoding="utf-8")
    cfg = load_scene_config(path)
    assert isinstance(cfg, MathSceneConfig)
    assert cfg.latex_expressions[0].tex == "a^2 + b^2 = c^2"
    assert cfg.text_labels[0].position == "UP"


def test_load_from_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "escena.yaml"
    path.write_text(
        "duration: 1.5\n"
        "latex_expressions:\n"
        "  - 'x + 1 = 3'\n"
        "  - {tex: 'x = 2', animation: FadeIn}\n"
        "text_labels:\n"
        "  - {text: 'Restamos 1', position: abajo, step: 1}\n",
        encoding="utf-8",
    )
    cfg = load_scene_config(path)
    assert cfg.animation_for(1) == "fadein"
    assert cfg.text_labels[0].position == "DOWN"
    assert cfg.text_labels[0].step == 1


def test_load_from_dict_and_shorthand_defaults() -> None:
    cfg = load_scene_config(base_config(text_labels=["Nota al pie"]))
    assert cfg.animation_for(0) == "write"          # la primera se escribe
    assert cfg.animation_for(1) == "transform"      # las siguientes se transforman
    assert cfg.text_labels[0].position == "DOWN"    # posición por defecto
    assert cfg.duration_for(0) == 1.0


def test_per_element_duration_overrides_global() -> None:
    cfg = load_scene_config(base_config(latex_expressions=["a", {"tex": "b", "duration": 3}]))
    assert cfg.duration_for(0) == 1.0 and cfg.duration_for(1) == 3.0
    assert cfg.total_duration() == pytest.approx(4.0)


@pytest.mark.parametrize("bad", [
    {"latex_expressions": []},                                              # sin expresiones
    {"latex_expressions": ["  "]},                                          # LaTeX vacío
    {"latex_expressions": [{"tex": "a", "animation": "transform"}]},        # transform sin origen
    {"latex_expressions": [{"tex": "a", "animation": "spin"}]},             # animación inválida
    {"text_labels": [{"text": "x", "position": "ARRIBITA"}]},               # posición inválida
    {"text_labels": [{"text": "x", "step": 5}]},                            # step fuera de rango
    {"text_labels": [{"text": "x"}, {"text": "y"}]},                        # misma posición y step
    {"duration": 0},                                                        # duración no positiva
    {"background_color": "black"},                                          # color no hex
    {"latex_expresions": ["typo"]},                                         # campo desconocido
])
def test_invalid_configs_raise(bad: Dict[str, Any]) -> None:
    with pytest.raises(SceneConfigError):
        load_scene_config(base_config(**bad))


def test_missing_file_and_bad_format(tmp_path: Path) -> None:
    with pytest.raises(SceneConfigError, match="No existe"):
        load_scene_config(tmp_path / "no_existe.json")
    txt = tmp_path / "escena.txt"
    txt.write_text("{}", encoding="utf-8")
    with pytest.raises(SceneConfigError, match="Formato no soportado"):
        load_scene_config(txt)
    broken = tmp_path / "rota.json"
    broken.write_text("{ latex_expressions: ", encoding="utf-8")
    with pytest.raises(SceneConfigError, match="No se pudo leer"):
        load_scene_config(broken)


# ------------------------------------------------------------------- calidad
@pytest.mark.parametrize("name,res,fps", [
    ("low", (854, 480), 15), ("-ql", (854, 480), 15), ("borrador", (854, 480), 15),
    ("high", (1920, 1080), 60), ("-qh", (1920, 1080), 60), ("Producción", (1920, 1080), 60),
])
def test_quality_presets(name: str, res: Tuple[int, int], fps: int) -> None:
    q = resolve_quality(name)
    assert q.resolution == res and q.fps == fps


def test_unknown_quality() -> None:
    with pytest.raises(ValueError):
        resolve_quality("ultra")


def test_output_paths_are_centralized() -> None:
    assert DEFAULT_OUTPUT_DIR.parts[-3:] == ("data", "renders", "manim")
    assert output_path_for("sample_math", resolve_quality("low")).name == "sample_math_low.mp4"
    assert output_path_for("sample_math", resolve_quality("high")).name == "sample_math.mp4"
    assert output_path_for("Fórmula: x/2", resolve_quality("high"), Path("out")).name == "Fórmula_x_2.mp4"


# ------------------------------------------------------------------- fuente
@pytest.mark.parametrize("env,installed,expected", [
    (None, ["Arial", "Segoe UI"], "Segoe UI"),          # Windows sin DejaVu Sans
    (None, ["DejaVu Sans", "Arial"], "DejaVu Sans"),    # Linux / Docker
    ("Arial", ["DejaVu Sans", "Arial"], "Arial"),       # $VA_FONT tiene prioridad
    ("NoExiste", ["Arial"], "Arial"),                   # $VA_FONT ausente → siguiente
    (None, ["Wingdings"], ""),                          # nada conocido → default de Pango
])
def test_resolve_font_uses_an_installed_font(monkeypatch: pytest.MonkeyPatch, env: Any,
                                             installed: List[str], expected: str) -> None:
    import manimpango

    if env is None:
        monkeypatch.delenv("VA_FONT", raising=False)
    else:
        monkeypatch.setenv("VA_FONT", env)
    monkeypatch.setattr(manimpango, "list_fonts", lambda: installed)
    ma.resolve_font.cache_clear()
    try:
        assert ma.resolve_font() == expected
    finally:
        ma.resolve_font.cache_clear()


# ---------------------------------------------------- render (simulado) y CLI
def _fake_manim(scene_config: MathSceneConfig, quality: Any, media_dir: Path, output_name: str) -> Path:
    raw = media_dir / f"{output_name}.mp4"
    raw.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
    return raw


def test_render_moves_video_to_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ma, "_run_manim", _fake_manim)
    config = tmp_path / "pitagoras.json"
    config.write_text(json.dumps(base_config()), encoding="utf-8")
    out = render_scene_from_config(config, "low", output_dir=tmp_path / "renders" / "manim")
    assert out == tmp_path / "renders" / "manim" / "pitagoras_low.mp4"
    assert out.is_file() and out.stat().st_size > 0
    # Re-render: sobrescribe sin fallar (en Windows rename falla si existe).
    assert render_scene_from_config(config, "low", output_dir=out.parent) == out


def test_cli_parses_flags_and_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ma, "_run_manim", _fake_manim)
    config = tmp_path / "escena.json"
    config.write_text(json.dumps(base_config(name="cli_demo")), encoding="utf-8")
    out_dir = tmp_path / "manim"
    assert ma.main(["--config", str(config), "--quality", "low", "--output-dir", str(out_dir)]) == 0
    assert (out_dir / "cli_demo_low.mp4").is_file()
    assert ma.main(["--config", str(config), "-qh", "--output-dir", str(out_dir)]) == 0
    assert (out_dir / "cli_demo.mp4").is_file()


def test_cli_reports_bad_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "mala.json"
    config.write_text(json.dumps({"latex_expressions": []}), encoding="utf-8")
    assert ma.main(["--config", str(config)]) == 2
    assert "Configuración inválida" in capsys.readouterr().err


def test_cli_rejects_quality_and_flag_together(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ma.build_parser().parse_args(["--config", "x.json", "--quality", "low", "-qh"])


# ------------------------------------------------------------- render real
@needs_ffprobe
def test_real_low_render_creates_clean_mp4(tmp_path: Path) -> None:
    config = tmp_path / "real.json"
    config.write_text(json.dumps(base_config(
        text_labels=[{"text": "Arriba", "position": "UP"},
                     {"text": "Izquierda", "position": "LEFT", "step": 1}],
        fade_out=True,
    )), encoding="utf-8")
    out = render_scene_from_config(config, "low", output_dir=tmp_path / "manim")
    assert out.is_file() and out.suffix == ".mp4"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames,codec_name,pix_fmt",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (854, 480)
    assert stream["r_frame_rate"] == "15/1"
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
    # 2 expresiones de 1 s + fade_out de 0.25 s = 2.25 s → round(2.25*15) = 34 cuadros
    assert int(stream["nb_read_frames"]) == 34
