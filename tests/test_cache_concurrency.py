"""
Pruebas de la caché Manim con renders simultáneos (HG).

Antes, dos renders a la vez (dos terminales, `bench_render.py --jobs`, dos
contenedores con el mismo volumen) compartían <cache>/manim/texts y Tex: uno
leía el SVG que el otro aún escribía ("no element found: line 1, column 0") y
el SVG vacío se quedaba en caché, haciendo fallar TODOS los renders siguientes.
Ahora cada proceso toma un slot con candado y al tomarlo purga SVG dañados.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from video_automation import manim_timing as mt

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fresh_slots(monkeypatch, tmp_path):
    monkeypatch.setenv("VA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(mt, "_slot_for", {})
    held = {}
    monkeypatch.setattr(mt, "_held_locks", held)
    yield tmp_path / "cache" / "manim"
    for fh in held.values():
        fh.close()


def test_purge_broken_svgs(tmp_path):
    d = tmp_path / "texts"
    d.mkdir()
    (d / "vacio.svg").write_bytes(b"")
    (d / "truncado.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0', encoding="utf-8")
    (d / "bueno.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>\n', encoding="utf-8")
    assert mt._purge_broken_svgs(d) == 2
    assert [p.name for p in d.iterdir()] == ["bueno.svg"]


def test_first_process_uses_the_usual_cache_dir(fresh_slots):
    root = mt.manim_cache_root()
    assert root == fresh_slots
    assert mt.manim_cache_root() is root            # mismo proceso → mismo slot
    cfg = mt.manim_config("/tmp/x", (854, 480), 15, "demo")
    assert cfg["tex_dir"] == str(root / "Tex") and cfg["text_dir"] == str(root / "texts")


def test_slot_purges_poisoned_cache(fresh_slots):
    texts = fresh_slots / "texts"
    texts.mkdir(parents=True)
    (texts / "0583ce3ea3ec4f19.svg").write_bytes(b"")   # el que se vio en Docker
    mt.manim_cache_root()
    assert not (texts / "0583ce3ea3ec4f19.svg").exists()


def test_concurrent_process_gets_its_own_slot(fresh_slots, tmp_path):
    holder = textwrap.dedent(f"""
        import os, sys
        sys.path[:0] = [{str(ROOT / 'src')!r}, {str(ROOT)!r}]
        os.environ["VA_CACHE_DIR"] = {str(tmp_path / 'cache')!r}
        from video_automation import manim_timing as mt
        print(mt.manim_cache_root(), flush=True)
        sys.stdin.read()          # mantiene el candado hasta que la prueba cierre stdin
    """)
    proc = subprocess.Popen([sys.executable, "-c", holder], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    try:
        other = Path(proc.stdout.readline().strip())
        assert other == fresh_slots                   # el otro proceso tomó el slot 0
        mine = mt.manim_cache_root()
        assert mine == fresh_slots / "slot1"
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)


@pytest.mark.parametrize("value,windows,expected", [
    ("/app/data/.cache", True, None),            # ruta de Docker que MoviePy trae del .env
    ("\\app\\data\\.cache", True, None),
    ("C:\\Users\\hg\\cache", True, "C:\\Users\\hg\\cache"),
    ("\\\\servidor\\cache", True, "\\\\servidor\\cache"),   # ruta UNC: sí sirve
    ("/app/data/.cache", False, "/app/data/.cache"),          # en Linux/Docker es válida
    ("", True, None), (None, False, None),
])
def test_cache_env_value(value, windows, expected):
    assert mt._cache_env_value(value, windows) == expected
