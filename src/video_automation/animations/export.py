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

from ..manim_timing import (
    DEFAULT_FPS, DEFAULT_RESOLUTION, VALID_FPS, cached_clip_is_valid, clip_cache_key, manim_config,
    normalize_clip, probe_video, store_cache_key,
)
from ..render_profiles import RenderProfile, default_profile
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


def normalize_alpha_clip(src: str, dst: str, fps: int, resolution: Tuple[int, int], frames: int,
                         profile: Optional[RenderProfile] = None) -> str:
    """
    Re-encoda conservando alfa, con cuadros exactos y fps constante.
    El perfil decide los hilos y el orden de códecs .mov (producción: ProRes
    4444; fast/low-res: qtrle, que codifica mucho más rápido).
    """
    profile = profile or default_profile()
    ext = Path(dst).suffix.lower()
    base = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", _alpha_filter(fps, resolution),
            "-frames:v", str(frames), "-r", str(fps), "-fps_mode", "cfr", "-an",
            *profile.ffmpeg_thread_args()]
    if ext == ".webm":
        webm = list(WEBM_ALPHA_ARGS)
        if not profile.is_production:
            # deadline good + cpu-used 5: VP9 bastante más rápido. (realtime
            # es aún más rápido pero ensucia el alfa del fondo: queda en 1, no en 0.)
            webm += ["-deadline", "good", "-cpu-used", "5"]
        res = _run_ffmpeg(base + webm + [str(dst)])
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo exportar {dst} (VP9 con alfa):\n{res.stderr}")
        return str(dst)

    available = _encoders()
    errors = []
    by_name = {c[0]: c for c in MOV_ALPHA_CODECS}
    ordered = [by_name[n] for n in profile.alpha_codecs if n in by_name]
    ordered += [c for c in MOV_ALPHA_CODECS if c not in ordered]
    preferred = ordered[0][0]
    for name, args, _ in ordered:
        if f" {name} " not in available:
            errors.append(f"{name}: encoder no disponible")
            continue
        res = _run_ffmpeg(base + args + [str(dst)])
        if res.returncode == 0:
            if name != preferred:
                log.warning("%s no disponible; %s exportado con %s.", preferred, dst, name)
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
    profile: Optional[RenderProfile] = None,
    use_cache: bool = False,
) -> Dict:
    """
    Renderiza una escena de animations/ a `output_path`.

    La extensión decide el formato (.mp4 opaco, .mov/.webm con alfa).
    resolution/fps son los finales (ya escalados por el perfil); el perfil
    decide códec/hilos. Con use_cache=True no re-renderiza si la clave
    (<clip>.key) coincide. Devuelve el resultado de ffprobe de la salida (dict).
    """
    profile = profile or default_profile()
    if fps not in VALID_FPS and profile.is_production:
        log.warning("fps=%s no es 30 ni 60; los clips de simple_animator.py van a 30.", fps)
    alpha = wants_alpha(output_path)
    scene_cls = get_overlay_scene(scene_name) if isinstance(scene_name, str) else scene_name
    name = scene_cls.__name__
    duration = float(duration or scene_cls.DEFAULT_DURATION)
    frames = int(round(duration * fps))
    resolution = (int(resolution[0]), int(resolution[1]))

    key = None
    if use_cache:
        key = clip_cache_key(scene_cls, duration, params, resolution, fps, profile,
                             {"alpha": alpha, "ext": Path(output_path).suffix.lower()})
        if cached_clip_is_valid(output_path, key):
            log.info("%s: overlay en caché, no se re-renderiza (%s)", name, output_path)
            return probe_overlay(output_path)

    work = tempfile.mkdtemp(prefix=f"manim_{name}_")
    try:
        cfg = manim_config(work, resolution, fps, name)
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
            normalize_alpha_clip(raw, output_path, fps, resolution, frames, profile=profile)
        else:
            normalize_clip(raw, output_path, fps, resolution, frames, profile=profile)
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
    if key:
        store_cache_key(output_path, key)
    return info
