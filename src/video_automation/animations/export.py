"""
Exportación de overlays Manim al formato del pipeline.

Formatos según la extensión de salida:

  .mp4   Opaco. libx264 + yuv420p + CFR + sin audio, IGUAL que
         simple_animator.py → se puede concatenar con los Ken Burns
         (`ffmpeg -f concat -c copy`). No admite canal alfa.
  .mov   Con alfa. QuickTime ProRes 4444 (prores_ks, yuva444p10le). Si el
         FFmpeg instalado no trae prores_ks se usa PNG-en-MOV y luego qtrle.
  .webm  Con alfa. VP9 (libvpx-vp9, yuva420p). Para LEER el alfa hay que
         forzar el decodificador: `ffmpeg -c:v libvpx-vp9 -i overlay.webm ...`.

En todos los casos: 1920x1080 por defecto, fps constante (30 por defecto) y
número de cuadros EXACTO = round(duración * fps).

Incrustar sobre la base (ejemplo, overlay desde el segundo 15):
    ffmpeg -i video2_base_render.mp4 -itsoffset 15 -i manim_overlay.mov \
      -filter_complex "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto" \
      -c:v libx264 -pix_fmt yuv420p -r 30 -c:a copy salida.mp4
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from manim import tempconfig

from ..manim_timing import DEFAULT_FPS, DEFAULT_RESOLUTION, VALID_FPS, normalize_clip, probe_video
from .base import OverlayScene

log = logging.getLogger(__name__)

ALPHA_EXTENSIONS = (".mov", ".webm")
OPAQUE_EXTENSIONS = (".mp4",)
SUPPORTED_EXTENSIONS = OPAQUE_EXTENSIONS + ALPHA_EXTENSIONS

# Códecs con alfa para .mov, en orden de preferencia.
MOV_ALPHA_CODECS: List[Tuple[str, List[str], str]] = [
    ("prores_ks", ["-c:v", "prores_ks", "-profile:v", "4444", "-vendor", "apl0",
                   "-pix_fmt", "yuva444p10le"], "yuva444p10le"),
    ("png", ["-c:v", "png", "-pix_fmt", "rgba"], "rgba"),
    ("qtrle", ["-c:v", "qtrle", "-pix_fmt", "argb"], "argb"),
]
WEBM_ALPHA_ARGS = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24",
                   "-row-mt", "1", "-auto-alt-ref", "0"]


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def get_overlay_scene(name: str) -> Type[OverlayScene]:
    from .math_scenes import SCENE_REGISTRY

    if name in SCENE_REGISTRY:
        return SCENE_REGISTRY[name]
    raise KeyError(f"Escena desconocida: {name!r}. Disponibles: {sorted(SCENE_REGISTRY)}")


def wants_alpha(output_path: str) -> bool:
    ext = Path(output_path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Extensión {ext!r} no soportada; usa una de {SUPPORTED_EXTENSIONS}")
    return ext in ALPHA_EXTENSIONS


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------

def _encoders() -> str:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return res.stdout


def _alpha_filter(fps: int, resolution: Tuple[int, int]) -> str:
    w, h = resolution
    return (f"format=rgba,scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1,fps={fps},"
            f"tpad=stop_mode=clone:stop=-1")


def _run_ffmpeg(cmd: List[str]) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 and "-fps_mode" in cmd:
        # ffmpeg < 5.1 no conoce -fps_mode.
        i = cmd.index("-fps_mode")
        cmd = cmd[:i] + ["-vsync", "cfr"] + cmd[i + 2:]
        res = subprocess.run(cmd, capture_output=True, text=True)
    return res


def normalize_alpha_clip(src: str, dst: str, fps: int, resolution: Tuple[int, int], frames: int) -> str:
    """Re-encoda conservando alfa, con cuadros exactos y fps constante."""
    ext = Path(dst).suffix.lower()
    base = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", _alpha_filter(fps, resolution),
            "-frames:v", str(frames), "-r", str(fps), "-fps_mode", "cfr", "-an"]
    if ext == ".webm":
        res = _run_ffmpeg(base + WEBM_ALPHA_ARGS + [str(dst)])
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo exportar {dst} (VP9 con alfa):\n{res.stderr}")
        return str(dst)

    available = _encoders()
    errors = []
    for name, args, _ in MOV_ALPHA_CODECS:
        if f" {name} " not in available:
            errors.append(f"{name}: encoder no disponible")
            continue
        res = _run_ffmpeg(base + args + [str(dst)])
        if res.returncode == 0:
            if name != "prores_ks":
                log.warning("prores_ks no disponible; %s exportado con %s.", dst, name)
            return str(dst)
        errors.append(f"{name}: {res.stderr.strip()[-300:]}")
    raise RuntimeError(f"ffmpeg no pudo exportar {dst} con alfa:\n" + "\n".join(errors))


def probe_overlay(path: str) -> Dict:
    """probe_video + datos de alfa (pix_fmt con 'a' o etiqueta alpha_mode de VP9)."""
    ext = Path(path).suffix.lower()
    if ext == ".webm":
        # El decodificador nativo de VP9 ignora el alfa; libvpx lo respeta.
        info = probe_video(path)
        tags = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                               "-show_entries", "stream_tags=alpha_mode", "-of", "csv=p=0", str(path)],
                              capture_output=True, text=True).stdout.strip()
        info["has_alpha"] = tags == "1"
    else:
        info = probe_video(path)
        info["has_alpha"] = any(k in info["pix_fmt"] for k in ("yuva", "rgba", "argb", "bgra", "gbrap"))
    return info


def corner_alpha(path: str, at: float) -> int:
    """Alfa (0-255) del píxel superior izquierdo en el segundo `at`."""
    cmd = ["ffmpeg", "-v", "error"]
    if Path(path).suffix.lower() == ".webm":
        cmd += ["-c:v", "libvpx-vp9"]
    cmd += ["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
            "-vf", "crop=1:1:0:0,format=rgba", "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    if len(out) < 4:
        raise RuntimeError(f"No se pudo leer un cuadro de {path}")
    return out[3]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_overlay(
    scene_name: str,
    output_path: str,
    duration: Optional[float] = None,
    params: Optional[Dict] = None,
    resolution: Tuple[int, int] = DEFAULT_RESOLUTION,
    fps: int = DEFAULT_FPS,
    verify: bool = True,
) -> Dict:
    """
    Renderiza una escena de animations/ a `output_path`.

    La extensión decide el formato (.mp4 opaco, .mov/.webm con alfa).
    Devuelve el resultado de ffprobe de la salida (dict).
    """
    if fps not in VALID_FPS:
        log.warning("fps=%s no es 30 ni 60; los clips de simple_animator.py van a 30.", fps)
    alpha = wants_alpha(output_path)
    scene_cls = get_overlay_scene(scene_name) if isinstance(scene_name, str) else scene_name
    name = scene_cls.__name__
    duration = float(duration or scene_cls.DEFAULT_DURATION)
    frames = int(round(duration * fps))
    width, height = resolution

    work = tempfile.mkdtemp(prefix=f"manim_{name}_")
    try:
        cfg = {
            "media_dir": work,
            "pixel_width": width,
            "pixel_height": height,
            "frame_rate": fps,
            "output_file": name,
            "disable_caching": True,
            "progress_bar": "none",
            "verbosity": "WARNING",
        }
        if alpha:
            # background_opacity < 1 → Manim escribe .mov qtrle/argb sin fondo.
            cfg.update({"background_opacity": 0.0, "movie_file_extension": ".mov"})
        with tempconfig(cfg):
            scene = scene_cls(target_duration=duration, params=params, transparent=alpha)
            scene.render()
            raw = str(scene.renderer.file_writer.movie_file_path)

        raw_frames = probe_video(raw)["frames"]
        if raw_frames != frames:
            log.warning("%s: Manim escribió %d cuadros (esperados %d); se corrige al exportar.",
                        name, raw_frames, frames)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if alpha:
            normalize_alpha_clip(raw, output_path, fps, resolution, frames)
        else:
            normalize_clip(raw, output_path, fps, resolution, frames)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    info = probe_overlay(output_path)
    if verify:
        problems = []
        if (info["width"], info["height"]) != tuple(resolution):
            problems.append(f"resolución {info['width']}x{info['height']}")
        if abs(info["fps"] - fps) > 1e-6 or abs(info["avg_fps"] - fps) > 0.01:
            problems.append(f"fps {info['fps']}/{info['avg_fps']}")
        if info["frames"] != frames:
            problems.append(f"cuadros {info['frames']} != {frames}")
        if alpha:
            if not info["has_alpha"]:
                problems.append(f"sin canal alfa (pix_fmt {info['pix_fmt']})")
            elif corner_alpha(output_path, duration / 2) != 0:
                problems.append("el fondo no es transparente")
        if problems:
            raise RuntimeError(f"{name}: salida fuera de especificación: {', '.join(problems)}")
        log.info("%s OK: %dx%d @%sfps, %d cuadros, alfa=%s → %s", name, info["width"],
                 info["height"], fps, info["frames"], info["has_alpha"], output_path)
    return info
