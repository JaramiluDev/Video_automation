"""
Perfiles de calidad de render (HG): --fast / --low-res / --production.

Objetivo: probar el pipeline sin saturar el equipo y dejar la calidad final
solo para el render de entrega. Un perfil decide:

  - resolución y fps de salida (escalando lo que pida el guion),
  - preset y CRF de libx264 (velocidad de codificación vs. calidad),
  - cuántos hilos puede usar FFmpeg / MoviePy,
  - si el proceso baja su prioridad para que la máquina siga usable,
  - el códec con alfa preferido para overlays (.mov).

  Perfil       Resolución (desde 1080p)  fps   x264            Hilos        Prioridad
  -----------  ------------------------  ----  --------------  -----------  ---------
  fast         854x480  (lado corto 480)  ≤15  ultrafast crf30  2            baja
  low-res      1280x720 (lado corto 720)  ≤30  veryfast  crf26  mitad de CPU baja
  production   la del guion (1920x1080)  guion medium   crf18  todas (auto) normal

Uso en un script:

    from video_automation.render_profiles import add_quality_arguments, profile_from_args
    add_quality_arguments(parser)            # agrega --fast/--low-res/--production/--quality/--threads
    args = parser.parse_args()
    profile = profile_from_args(args)
    profile.apply_process_limits()           # baja prioridad si el perfil lo pide
    res, fps = profile.resolve(res, fps)     # escala lo que pidió el guion

Sin flags se usa la variable de entorno VA_QUALITY (fast | low-res | production)
y, si tampoco existe, "production". Así cada quien puede dejar su máquina de
desarrollo en `VA_QUALITY=fast` sin cambiar los comandos del equipo.

IMPORTANTE: los clips que se unen con `ffmpeg -f concat -c copy`
(simple_concatenator) deben salir del MISMO perfil; mezclar resoluciones o fps
rompe la concatenación sin re-encodar.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

ENV_VAR = "VA_QUALITY"
ENV_THREADS = "VA_THREADS"
DEFAULT_PROFILE = "production"


def _cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def _even(x: float) -> int:
    """libx264 + yuv420p exige dimensiones pares."""
    return max(2, int(round(x / 2.0)) * 2)


@dataclass(frozen=True)
class RenderProfile:
    name: str
    description: str
    #: Lado corto máximo (480 → 854x480 desde 16:9). None = la del guion.
    max_short_side: Optional[int]
    #: Tope de fps. None = el del guion.
    max_fps: Optional[int]
    x264_preset: str
    crf: int
    #: Hilos de FFmpeg. 0 = automático (todos); -1 = mitad de los núcleos.
    threads: int
    low_priority: bool
    #: Códecs con alfa para .mov en orden de preferencia (ver animations/export.py).
    alpha_codecs: Tuple[str, ...] = ("prores_ks", "png", "qtrle")
    #: Sufijo para no sobrescribir los renders de producción con borradores.
    suffix: str = ""
    #: True si los hilos vienen de --threads (entonces $VA_THREADS no los cambia).
    threads_explicit: bool = False

    # -- Resolución / fps --------------------------------------------------
    def resolve(self, resolution: Sequence[int] = (1920, 1080), fps: int = 30) -> Tuple[Tuple[int, int], int]:
        """Escala (resolución, fps) del guion según el perfil, conservando la proporción."""
        w, h = int(resolution[0]), int(resolution[1])
        if self.max_short_side and min(w, h) > self.max_short_side:
            scale = self.max_short_side / float(min(w, h))
            w, h = _even(w * scale), _even(h * scale)
        out_fps = int(fps)
        if self.max_fps and out_fps > self.max_fps:
            out_fps = self.max_fps
        return (w, h), out_fps

    @property
    def is_production(self) -> bool:
        return self.name == "production"

    # -- Hilos -------------------------------------------------------------
    @property
    def thread_count(self) -> int:
        """Hilos efectivos (0 = que FFmpeg decida)."""
        env = os.environ.get(ENV_THREADS)
        if not self.threads_explicit and env and env.strip().isdigit():
            return int(env)
        if self.threads == -1:
            return max(1, _cpu_count() // 2)
        return self.threads

    def ffmpeg_thread_args(self) -> List[str]:
        n = self.thread_count
        return ["-threads", str(n)] if n > 0 else []

    # -- Codificación ------------------------------------------------------
    def x264_args(self) -> List[str]:
        """Argumentos de calidad/velocidad para -c:v libx264 (incluye hilos)."""
        return ["-preset", self.x264_preset, "-crf", str(self.crf)] + self.ffmpeg_thread_args()

    def moviepy_write_kwargs(self) -> Dict:
        """kwargs para VideoClip.write_videofile() de MoviePy."""
        kwargs: Dict = {
            "codec": "libx264",
            "preset": self.x264_preset,
            "ffmpeg_params": ["-crf", str(self.crf)],
        }
        n = self.thread_count
        if n > 0:
            kwargs["threads"] = n
        return kwargs

    # -- Archivos ----------------------------------------------------------
    def tag_path(self, path) -> Path:
        """video.mp4 → video_fast.mp4 (solo en perfiles que no son producción)."""
        p = Path(path)
        if not self.suffix or p.stem.endswith(self.suffix):
            return p
        return p.with_name(f"{p.stem}{self.suffix}{p.suffix}")

    def tag_dir(self, path) -> Path:
        """manim_clips → manim_clips_fast."""
        p = Path(path)
        if not self.suffix or p.name.endswith(self.suffix):
            return p
        return p.with_name(f"{p.name}{self.suffix}")

    # -- Proceso -----------------------------------------------------------
    def apply_process_limits(self) -> bool:
        """
        Baja la prioridad del proceso actual (y de los FFmpeg/LaTeX que lance,
        que la heredan) para que el equipo siga respondiendo durante las
        pruebas. Devuelve True si se aplicó.
        """
        if not self.low_priority or os.environ.get("VA_NO_NICE"):
            return False
        try:
            if sys.platform == "win32":
                import ctypes

                BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
                k32 = ctypes.windll.kernel32
                ok = bool(k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS))
            else:
                os.nice(10)
                ok = True
        except Exception as exc:  # pragma: no cover - depende del SO
            log.warning("No se pudo bajar la prioridad del proceso: %s", exc)
            return False
        if ok:
            log.info("Perfil %s: prioridad del proceso reducida.", self.name)
        return ok

    def summary(self, resolution: Sequence[int], fps: int) -> str:
        n = self.thread_count
        hilos = "auto" if n == 0 else str(n)
        return (f"perfil={self.name} {resolution[0]}x{resolution[1]}@{fps}fps "
                f"x264={self.x264_preset}/crf{self.crf} hilos={hilos}"
                f"{' prioridad=baja' if self.low_priority else ''}")


PROFILES: Dict[str, RenderProfile] = {
    "fast": RenderProfile(
        name="fast",
        description="Borrador rápido: 480p, ≤15 fps, ultrafast, 2 hilos, prioridad baja.",
        max_short_side=480, max_fps=15, x264_preset="ultrafast", crf=30, threads=2,
        low_priority=True, alpha_codecs=("qtrle", "png", "prores_ks"), suffix="_fast",
    ),
    "low-res": RenderProfile(
        name="low-res",
        description="Revisión: 720p, ≤30 fps, veryfast, mitad de los núcleos, prioridad baja.",
        max_short_side=720, max_fps=30, x264_preset="veryfast", crf=26, threads=-1,
        low_priority=True, alpha_codecs=("qtrle", "png", "prores_ks"), suffix="_lowres",
    ),
    "production": RenderProfile(
        name="production",
        description="Entrega: resolución/fps del guion (1080p), medium crf18, todos los núcleos.",
        max_short_side=None, max_fps=None, x264_preset="medium", crf=18, threads=0,
        low_priority=False,
    ),
}

ALIASES: Dict[str, str] = {
    "draft": "fast", "preview": "fast", "rapido": "fast", "rápido": "fast",
    "low": "low-res", "lowres": "low-res", "low_res": "low-res", "720p": "low-res",
    "prod": "production", "final": "production", "1080p": "production",
}


def get_profile(name: Optional[str] = None) -> RenderProfile:
    """Perfil por nombre/alias; None → $VA_QUALITY → production."""
    raw = (name or os.environ.get(ENV_VAR) or DEFAULT_PROFILE).strip().lower()
    key = ALIASES.get(raw, raw)
    if key not in PROFILES:
        raise ValueError(f"Perfil de calidad desconocido {raw!r}. Usa uno de: "
                         f"{', '.join(PROFILES)} (alias: {', '.join(sorted(ALIASES))})")
    return PROFILES[key]


def default_profile() -> RenderProfile:
    """Perfil para funciones de librería llamadas sin perfil explícito."""
    return get_profile(None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_quality_arguments(parser: argparse.ArgumentParser, preview_alias: bool = False) -> None:
    """
    Agrega al parser:
      --fast | --low-res | --production | --quality NOMBRE   (mutuamente excluyentes)
      --threads N                                             (sobrescribe los hilos del perfil)
    Con preview_alias=True también acepta --preview como sinónimo de --fast
    (compatibilidad con los scripts que ya lo tenían).
    """
    group = parser.add_argument_group("calidad de render")
    mx = group.add_mutually_exclusive_group()
    mx.add_argument("--fast", dest="quality", action="store_const", const="fast",
                    help=PROFILES["fast"].description)
    mx.add_argument("--low-res", dest="quality", action="store_const", const="low-res",
                    help=PROFILES["low-res"].description)
    mx.add_argument("--production", dest="quality", action="store_const", const="production",
                    help=PROFILES["production"].description)
    if preview_alias:
        mx.add_argument("--preview", dest="quality", action="store_const", const="fast",
                        help="Sinónimo de --fast.")
    mx.add_argument("--quality", dest="quality", metavar="PERFIL",
                    help=f"Perfil por nombre ({', '.join(PROFILES)}). "
                         f"Sin flag: ${ENV_VAR} o '{DEFAULT_PROFILE}'.")
    group.add_argument("--threads", type=int, default=None, metavar="N",
                       help="Hilos máximos para FFmpeg (0 = automático). Sobrescribe el perfil.")


def profile_from_args(args: argparse.Namespace) -> RenderProfile:
    profile = get_profile(getattr(args, "quality", None))
    threads = getattr(args, "threads", None)
    if threads is not None:
        if threads < 0:
            raise ValueError("--threads debe ser >= 0")
        profile = replace(profile, threads=threads, threads_explicit=True)
    return profile
