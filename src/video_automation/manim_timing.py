"""
Infraestructura de tiempo y exportación para escenas de Manim.

Resuelve los tres requerimientos técnicos que no dependen del contenido:

1. DURACIÓN EXACTA. El parser inyecta `scene.duration` (segundos) y el
   compositor necesita que cada clip dure exactamente eso. TimedScene
   convierte la duración objetivo en un número entero de cuadros
   (round(duration * fps)) y reparte ese presupuesto entre los "beats" de la
   escena. Si el guion da más tiempo, se alargan las pausas (no las
   animaciones); si da menos, se comprime todo proporcionalmente.

2. 1920x1080 A FPS CONSTANTE. render_timed_scene() configura Manim con la
   resolución/fps de OutputSettings y después normalize_clip() re-encoda con
   los MISMOS parámetros que usa simple_animator.py (libx264, yuv420p, -r fps,
   sin audio). Así los clips de Manim y los Ken Burns se pueden unir incluso
   con `ffmpeg -f concat -c copy` sin re-encodar.

3. LATEX. tex() usa MathTex; si LaTeX no está instalado (desarrollo fuera de
   Docker) cae a Text plano, salvo que VA_STRICT_LATEX=1, que es como corre la
   prueba de fuego dentro del contenedor: ahí cualquier paquete faltante debe
   romper el build, no esconderse.

Cómo escribir una escena nueva (ver scenes_video2.py):

    class MiEscena(TimedScene):
        DEFAULT_DURATION = 8.0
        DEFAULT_PARAMS = {"fraccion": "2/4"}

        def timeline(self):
            titulo = Text("Hola")
            self.beat(Write(titulo), t=1.5)   # animación (~1.5 s nominales)
            self.hold(2.0)                    # pausa estirable
            self.beat(FadeOut(titulo), t=0.8)

    NUNCA llames self.play()/self.wait() directo dentro de timeline(): usa
    beat()/hold() para que el presupuesto de cuadros cuadre.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from manim import MathTex, Scene, Text, Wait, tempconfig

log = logging.getLogger(__name__)

# Módulos donde se buscan clases por nombre (manim_scene: "..." en el YAML).
SCENE_MODULES = ["scenes_video2"]

VALID_FPS = (30, 60)
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30
# Duración mínima razonable de una animación cuando el guion comprime mucho.
MIN_ANIM_FRAMES = 2


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def strict_latex() -> bool:
    return os.environ.get("VA_STRICT_LATEX", "0").lower() in ("1", "true", "yes")


def tex(latex: str, **kwargs):
    """MathTex con fallback a Text si LaTeX no existe (salvo VA_STRICT_LATEX=1)."""
    try:
        return MathTex(latex, **kwargs)
    except Exception as exc:  # LaTeX ausente o paquete faltante
        if strict_latex():
            raise
        log.warning("MathTex falló (%s); usando Text como fallback para %r", exc, latex)
        font_size = kwargs.get("font_size", 48)
        color = kwargs.get("color")
        plain = (latex.replace("\\times", "×").replace("\\neq", "≠").replace("\\frac", "")
                 .replace("{", "").replace("}", "/").replace("\\,", " ").replace("\\", ""))
        return Text(plain.rstrip("/"), font_size=font_size * 0.8,
                    **({"color": color} if color else {}))


def check_latex() -> Tuple[bool, str]:
    """Pre-vuelo: compila un MathTex representativo del Video 2."""
    probe = r"\frac{2}{4} = \frac{4}{8} \quad 2 \times 8 = 4 \times 4 \quad \frac{2}{4} \neq \frac{2}{8}"
    try:
        with tempconfig({"media_dir": tempfile.mkdtemp(prefix="latex_check_"), "verbosity": "ERROR"}):
            MathTex(probe)
        return True, "LaTeX OK (latex + dvisvgm + amsmath/amssymb/standalone)"
    except Exception as exc:
        return False, f"LaTeX NO disponible: {exc}"


# ---------------------------------------------------------------------------
# Planeación de cuadros
# ---------------------------------------------------------------------------

def plan_frames(beats: List[Tuple[str, float]], target_duration: float, fps: int) -> List[int]:
    """
    Reparte round(target_duration*fps) cuadros entre los beats.

    beats: [("anim", segundos_nominales) | ("hold", segundos_nominales), ...]
    Regla:
      - Si sobra tiempo: animaciones a velocidad nominal, el excedente se
        reparte entre las pausas (si no hay pausas, se estiran animaciones).
      - Si falta tiempo: todo se comprime por el mismo factor.
    Devuelve cuadros por beat; la suma es EXACTAMENTE el total.
    """
    total_frames = int(round(target_duration * fps))
    if not beats:
        return []
    anim = sum(t for k, t in beats if k == "anim")
    hold = sum(t for k, t in beats if k == "hold")
    nominal = anim + hold
    if nominal <= 0:
        raise ValueError("La escena no declaró ningún beat con duración.")

    if target_duration >= nominal and hold > 0:
        hold_scale = (target_duration - anim) / hold
        scaled = [t if k == "anim" else t * hold_scale for k, t in beats]
    else:
        factor = target_duration / nominal
        scaled = [t * factor for _, t in beats]

    # Fronteras acumuladas redondeadas → la suma cuadra sin error acumulado.
    frames, acc, prev = [], 0.0, 0
    for s in scaled:
        acc += s
        edge = int(round(acc * fps))
        frames.append(edge - prev)
        prev = edge
    frames[-1] += total_frames - sum(frames)

    # Garantiza un mínimo por animación robando al beat más largo.
    for i, (k, _) in enumerate(beats):
        need = (MIN_ANIM_FRAMES if k == "anim" else 0) - frames[i]
        while need > 0:
            j = max(range(len(frames)), key=lambda x: frames[x])
            if j == i or frames[j] <= MIN_ANIM_FRAMES:
                break
            frames[j] -= 1
            frames[i] += 1
            need -= 1
    return frames


# ---------------------------------------------------------------------------
# Escena base
# ---------------------------------------------------------------------------

class TimedScene(Scene):
    """Escena de Manim cuya duración total es exactamente target_duration."""

    DEFAULT_DURATION: float = 6.0
    DEFAULT_PARAMS: Dict = {}

    def __init__(self, target_duration: Optional[float] = None, params: Optional[Dict] = None, **kwargs):
        self.target_duration = float(target_duration or self.DEFAULT_DURATION)
        if self.target_duration <= 0:
            raise ValueError("La duración objetivo debe ser > 0")
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._dry = False
        self._beats: List[Tuple[str, float]] = []
        self._plan: List[int] = []
        self._cursor = 0
        self._edge = 0
        super().__init__(**kwargs)

    # -- API para las subclases -------------------------------------------
    def timeline(self):  # pragma: no cover - lo implementan las subclases
        raise NotImplementedError

    def beat(self, *animations, t: float = 1.0, **play_kwargs):
        """Reproduce animaciones ocupando su parte del presupuesto (t nominal)."""
        if self._dry:
            self._beats.append(("anim", float(t)))
            return
        n = self._next_frames()
        if n < 1:
            n = 1  # una animación necesita al menos un cuadro para aplicar su estado final
        # Manim genera ceil(run_time*fps) cuadros: (n-0.5)/fps da exactamente n.
        self.play(*animations, run_time=(n - 0.5) / self.fps, **play_kwargs)

    def hold(self, t: float = 1.0):
        """Pausa estática (se estira cuando el guion da más tiempo)."""
        if self._dry:
            self._beats.append(("hold", float(t)))
            return
        n = self._next_frames()
        if n > 0:
            self._freeze(n)

    # -- Motor -------------------------------------------------------------
    @property
    def fps(self) -> int:
        return int(round(self.camera.frame_rate))

    @property
    def total_frames(self) -> int:
        return int(round(self.target_duration * self.fps))

    def frames_written(self) -> int:
        return int(round(self.renderer.time * self.fps))

    def _next_frames(self) -> int:
        # Frontera absoluta: se autocorrige si algún play() escribió de más/menos.
        self._edge += self._plan[self._cursor]
        self._cursor += 1
        return self._edge - self.frames_written()

    def _freeze(self, n: int):
        # Wait congelado usa int(duration*fps) cuadros → (n+0.25)/fps da n.
        self.play(Wait(run_time=(n + 0.25) / self.fps, frozen_frame=True))

    def construct(self):
        # 1) Pasada en seco: solo se registran los beats y su duración nominal.
        self._dry = True
        self._beats = []
        self.timeline()
        self.clear()
        self._dry = False

        # 2) Plan de cuadros exacto para la duración pedida.
        self._plan = plan_frames(self._beats, self.target_duration, self.fps)
        self._cursor, self._edge = 0, 0
        nominal = sum(t for _, t in self._beats)
        log.info("%s: %d beats, nominal %.2fs → objetivo %.2fs (%d cuadros @%dfps)",
                 type(self).__name__, len(self._beats), nominal,
                 self.target_duration, self.total_frames, self.fps)

        # 3) Pasada real.
        self.timeline()

        # 4) Relleno final por si algún beat quedó corto.
        remaining = self.total_frames - self.frames_written()
        if remaining > 0:
            self._freeze(remaining)
        elif remaining < 0:
            log.warning("%s excedió %d cuadro(s); normalize_clip lo recorta.",
                        type(self).__name__, -remaining)


# ---------------------------------------------------------------------------
# Registro de escenas
# ---------------------------------------------------------------------------

def get_scene_class(name: str) -> Type[TimedScene]:
    for mod_name in SCENE_MODULES:
        mod = import_module(f"{__package__}.{mod_name}")
        registry = getattr(mod, "SCENE_REGISTRY", {})
        if name in registry:
            return registry[name]
    available = sorted(k for m in SCENE_MODULES
                       for k in getattr(import_module(f"{__package__}.{m}"), "SCENE_REGISTRY", {}))
    raise KeyError(f"Escena Manim desconocida: {name!r}. Disponibles: {available}")


# ---------------------------------------------------------------------------
# Render + normalización + verificación
# ---------------------------------------------------------------------------

def probe_video(path: str) -> Dict:
    """ffprobe → width, height, fps, frames, duration, codec, pix_fmt."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames,codec_name,pix_fmt",
           "-show_entries", "format=duration", "-of", "json", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    st = data["streams"][0]
    num, den = (int(x) for x in st["r_frame_rate"].split("/"))
    anum, aden = (int(x) for x in st["avg_frame_rate"].split("/"))
    return {
        "width": st["width"], "height": st["height"],
        "fps": num / den, "avg_fps": anum / aden if aden else 0.0,
        "frames": int(st["nb_read_frames"]),
        "duration": float(data["format"]["duration"]),
        "codec": st["codec_name"], "pix_fmt": st["pix_fmt"],
    }


def normalize_clip(src: str, dst: str, fps: int, resolution: Tuple[int, int], frames: int) -> str:
    """
    Re-encoda al formato común del pipeline con número de cuadros EXACTO:
    libx264 + yuv420p + CFR + sin audio (igual que simple_animator.py).
    tpad clona el último cuadro si faltara alguno y -frames:v recorta si sobra.
    """
    w, h = resolution
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},"
          f"tpad=stop_mode=clone:stop=-1")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf,
           "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-r", str(fps), "-fps_mode", "cfr", "-an", "-movflags", "+faststart", str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # ffmpeg < 5.1 no conoce -fps_mode; usa el equivalente anterior.
        cmd[cmd.index("-fps_mode"):cmd.index("-fps_mode") + 2] = ["-vsync", "cfr"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo normalizar {src}:\n{res.stderr}")
    return str(dst)


def render_timed_scene(
    scene_name,
    output_path: str,
    duration: Optional[float] = None,
    params: Optional[Dict] = None,
    resolution: Tuple[int, int] = DEFAULT_RESOLUTION,
    fps: int = DEFAULT_FPS,
    verify: bool = True,
) -> str:
    """
    Renderiza una escena (nombre registrado o clase TimedScene) a `output_path`
    con duración exacta. Devuelve la ruta del .mp4 normalizado.
    """
    if fps not in VALID_FPS:
        log.warning("fps=%s no es 30 ni 60; el compositor espera uno de %s", fps, VALID_FPS)
    if isinstance(scene_name, str):
        scene_cls = get_scene_class(scene_name)
    else:
        scene_cls, scene_name = scene_name, scene_name.__name__
    duration = float(duration or scene_cls.DEFAULT_DURATION)
    width, height = resolution
    work = tempfile.mkdtemp(prefix=f"manim_{scene_name}_")
    try:
        with tempconfig({
            "media_dir": work,
            "pixel_width": width,
            "pixel_height": height,
            "frame_rate": fps,
            "output_file": scene_name,
            "disable_caching": True,
            "progress_bar": "none",
            "verbosity": "WARNING",
        }):
            scene = scene_cls(target_duration=duration, params=params)
            scene.render()
            raw = scene.renderer.file_writer.movie_file_path

        frames = int(round(duration * fps))
        raw_frames = probe_video(str(raw))["frames"]
        if raw_frames != frames:
            log.warning("%s: Manim escribió %d cuadros (esperados %d); se corrige al normalizar.",
                        scene_name, raw_frames, frames)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        normalize_clip(str(raw), output_path, fps, resolution, frames)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if verify:
        info = probe_video(output_path)
        problems = []
        if (info["width"], info["height"]) != tuple(resolution):
            problems.append(f"resolución {info['width']}x{info['height']}")
        if abs(info["fps"] - fps) > 1e-6 or abs(info["avg_fps"] - fps) > 0.01:
            problems.append(f"fps {info['fps']}/{info['avg_fps']}")
        if info["frames"] != frames:
            problems.append(f"cuadros {info['frames']} != {frames}")
        if problems:
            raise RuntimeError(f"{scene_name}: salida fuera de especificación: {', '.join(problems)}")
        log.info("%s OK: %dx%d @%sfps, %d cuadros (%.3fs)", scene_name,
                 info["width"], info["height"], fps, info["frames"], frames / fps)
    return str(output_path)
