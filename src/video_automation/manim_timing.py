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

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Type

from manim import MathTex, Scene, Text, Wait, tempconfig

from .render_profiles import RenderProfile, default_profile

log = logging.getLogger(__name__)

# Módulos donde se buscan clases por nombre (manim_scene: "..." en el YAML).
# animations.math_scenes son overlays (OverlayScene); también se pueden usar
# como escena completa (fondo de pizarrón opaco).
SCENE_MODULES = ["scenes_video2", "animations.math_scenes"]

# Archivos cuyo contenido invalida la caché de clips Manim si cambian.
_PKG_DIR = Path(__file__).resolve().parent
CACHE_SOURCES = ["manim_timing.py", "scenes_video2.py", "fracciones.py", "ecuaciones.py",
                 "animations/base.py", "animations/components.py", "animations/math_scenes.py",
                 "animations/export.py"]

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


#: True cuando LaTeX/dvisvgm no funcionan en este equipo (se detecta con el primer
#: MathTex que falla por la instalación, no por la fórmula). Desde ahí ya no se
#: intenta compilar cada fórmula: se usa Text directo y se avisa UNA vez.
_latex_broken = False
_INSTALL_ERRORS = ("does not support converting", "latex failed", "no such file", "not recognized",
                   "cannot find the file", "winerror 2")

#: LaTeX → texto legible para el respaldo sin LaTeX (orden importa).
_PLAIN = [("\\left(", "("), ("\\right)", ")"), ("\\left[", "["), ("\\right]", "]"),
          ("\\qquad", "    "), ("\\quad", "  "), ("\\times", "×"), ("\\cdot", "·"),
          ("\\div", "÷"), ("\\neq", "≠"), ("\\pm", "±"), ("\\leq", "≤"), ("\\geq", "≥"),
          ("\\sqrt", "√"), ("^{2}", "²"), ("^2", "²"), ("^{3}", "³"), ("^3", "³"), ("\\,", " ")]


def latex_to_plain(latex: str) -> str:
    """Versión en texto plano de una fórmula sencilla (\\frac{a}{b} → a/b)."""
    import re

    out = latex
    for a, b in _PLAIN:
        out = out.replace(a, b)
    for _ in range(10):        # de adentro hacia afuera: \\frac{-b ± √{...}}{2a}
        new = re.sub(r"√\{([^{}]*)\}", r"√(\1)", out)
        new = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}",
                     lambda m: "/".join(x if len(x) <= 1 or x.isalnum() else f"({x})"
                                        for x in m.groups()), new)
        if new == out:
            break
        out = new
    return out.replace("{", "").replace("}", "").replace("\\", "").strip()


def _dvisvgm_detail() -> str:
    """
    Manim esconde la salida de dvisvgm. Si falló, se vuelve a correr sobre el
    .dvi más reciente de tex_dir para mostrar el error real en el aviso.
    """
    try:
        from manim import config as _cfg

        tex_dir = Path(_cfg.get_dir("tex_dir"))
        dvis = sorted(tex_dir.glob("*.dvi"), key=lambda p: p.stat().st_mtime)
        if not dvis:
            return f"no hay .dvi en {tex_dir}"
        out = dvis[-1].with_suffix(".diag.svg")
        res = subprocess.run(["dvisvgm", "--no-fonts", "--verbosity=3", f"--output={out.as_posix()}",
                              dvis[-1].as_posix()], capture_output=True, text=True, timeout=60)
        out.unlink(missing_ok=True)
        lines = [ln for ln in (res.stderr + res.stdout).splitlines() if ln.strip()]
        return f"dvisvgm {dvis[-1].name} → código {res.returncode}: " + " | ".join(lines[-6:])
    except Exception as exc:  # noqa: BLE001 - solo es diagnóstico
        return f"(sin detalle: {exc})"


def latex_available() -> bool:
    """False si ya se detectó que LaTeX/dvisvgm no funcionan en este proceso."""
    return not _latex_broken


def tex(latex: str, **kwargs):
    """MathTex con fallback a Text si LaTeX no existe (salvo VA_STRICT_LATEX=1)."""
    global _latex_broken
    if not _latex_broken or strict_latex():
        try:
            return MathTex(latex, **kwargs)
        except Exception as exc:  # LaTeX ausente o paquete faltante
            if strict_latex():
                raise
            msg = str(exc).lower()
            if any(k in msg for k in _INSTALL_ERRORS) or isinstance(exc, (FileNotFoundError, OSError)):
                _latex_broken = True
                log.warning(
                    "LaTeX no funciona en este equipo (%s). Todas las fórmulas de este render "
                    "saldrán como texto plano y no se guardarán en caché. Detalle: %s",
                    str(exc).splitlines()[0][:120], _dvisvgm_detail())
            else:
                log.warning("MathTex falló para %r (%s); se usa texto plano.", latex, exc)
    font_size = kwargs.get("font_size", 48)
    color = kwargs.get("color")
    return Text(latex_to_plain(latex), font_size=font_size * 0.8,
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
# Configuración de Manim y caché
# ---------------------------------------------------------------------------

def _cache_env_value(value: Optional[str], windows: bool) -> Optional[str]:
    """
    $VA_CACHE_DIR utilizable en este sistema, o None.

    En Windows se ignora una ruta de contenedor como "/app/data/.cache" (sin
    unidad C:). Llega ahí porque MoviePy carga el .env del repo al importarse
    (moviepy/config.py → load_dotenv) y el .env trae la ruta de Docker. Python
    la convierte en C:\\app\\data\\.cache, pero dvisvgm de MiKTeX no puede escribir
    en "/app/..." y TODAS las fórmulas caían a texto plano.
    """
    if not value or not value.strip():
        return None
    value = value.strip()
    if windows and value.startswith(("/", "\\")) and not value.startswith("\\\\"):
        return None
    return value


_warned_cache_env = False


def cache_dir() -> Path:
    """Carpeta persistente para LaTeX/textos de Manim y claves de clips ($VA_CACHE_DIR)."""
    global _warned_cache_env
    raw = os.environ.get("VA_CACHE_DIR")
    root = _cache_env_value(raw, os.name == "nt")
    if raw and root is None and not _warned_cache_env:
        _warned_cache_env = True
        log.warning("VA_CACHE_DIR=%r es una ruta de Docker; en Windows se ignora y se usa %s",
                    raw, Path.home() / ".cache" / "video_automation")
    return Path(root or str(Path.home() / ".cache" / "video_automation"))


#: Máximo de renders simultáneos con caché propia; el siguiente usa una temporal.
MAX_CACHE_SLOTS = 16
_held_locks: Dict[str, object] = {}     # base → archivo con el candado (vive lo que el proceso)
_slot_for: Dict[str, Path] = {}


def _try_lock(fh) -> bool:
    """Candado exclusivo NO bloqueante entre procesos (Linux/Docker y Windows)."""
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _purge_broken_svgs(root: Path) -> int:
    """
    Borra SVG vacíos o truncados de la caché (un render matado a la mitad, o
    la carrera entre procesos que había antes de los slots). Uno solo basta
    para que TODOS los renders siguientes fallen con
    "no element found: line 1, column 0" al leer ese texto/fórmula.
    """
    removed = 0
    for svg in root.rglob("*.svg"):
        try:
            size = svg.stat().st_size
            ok = size > 0
            if ok:
                with svg.open("rb") as fh:
                    fh.seek(max(0, size - 64))
                    ok = b"</svg>" in fh.read()
            if not ok:
                svg.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        log.warning("Caché Manim: %d SVG dañado(s) eliminado(s) en %s", removed, root)
    return removed


def manim_cache_root() -> Path:
    """
    Carpeta de caché de LaTeX/Text de ESTE proceso.

    Manim no protege su caché contra procesos simultáneos: si dos renders
    (dos terminales, `--jobs`, dos contenedores con el mismo volumen) generan
    el mismo SVG a la vez, uno lee el archivo a medio escribir y truena — y
    el SVG vacío se queda en caché envenenando los renders siguientes. Cada
    proceso toma un "slot" con candado: el primero usa <cache>/manim (la de
    siempre), el segundo <cache>/manim/slot1, etc. El candado lo libera el
    sistema operativo al terminar el proceso, aunque lo maten.
    """
    base = cache_dir() / "manim"
    key = str(base)
    if key in _slot_for:
        return _slot_for[key]
    for slot in range(MAX_CACHE_SLOTS):
        d = base if slot == 0 else base / f"slot{slot}"
        try:
            d.mkdir(parents=True, exist_ok=True)
            fh = open(d / ".lock", "a+")
        except OSError:
            continue
        if _try_lock(fh):
            _held_locks[key] = fh
            _purge_broken_svgs(d / "Tex")
            _purge_broken_svgs(d / "texts")
            _slot_for[key] = d
            if slot:
                log.info("Caché Manim ocupada por otro render; este usa %s", d)
            return d
        fh.close()
    d = Path(tempfile.mkdtemp(prefix="manim_cache_"))
    log.warning("Hay %d renders usando la caché Manim; este usa una temporal: %s", MAX_CACHE_SLOTS, d)
    _slot_for[key] = d
    return d


def manim_config(media_dir: str, resolution: Tuple[int, int], fps: int, output_file: str) -> Dict:
    """
    Config común para tempconfig(). media_dir es temporal (se borra al
    terminar), pero los SVG de LaTeX y de Text van a una caché persistente:
    así cada render no vuelve a compilar las mismas fórmulas, que es la parte
    más lenta de las escenas con MathTex. La caché es por slot
    (manim_cache_root): segura con varios renders en paralelo.
    """
    width, height = resolution
    cache = manim_cache_root()
    return {
        "media_dir": media_dir,
        "tex_dir": str(cache / "Tex"),
        "text_dir": str(cache / "texts"),
        "pixel_width": width,
        "pixel_height": height,
        "frame_rate": fps,
        "output_file": output_file,
        "disable_caching": True,
        "progress_bar": "none",
        "verbosity": "WARNING",
    }


def _sources_digest(extra_files: Sequence[str] = ()) -> str:
    h = hashlib.sha256()
    for rel in list(CACHE_SOURCES) + list(extra_files):
        f = Path(rel) if Path(rel).is_absolute() else _PKG_DIR / rel
        try:
            h.update(f.read_bytes())
        except OSError:
            h.update(rel.encode())
    return h.hexdigest()


def clip_cache_key(scene_cls, duration: float, params: Optional[Dict], resolution: Tuple[int, int],
                   fps: int, profile: RenderProfile, extra: Optional[Dict] = None) -> str:
    """Huella de todo lo que cambia el clip: escena, parámetros, tiempo, formato, perfil y código."""
    import inspect

    try:
        src_file = inspect.getsourcefile(scene_cls) or ""
    except TypeError:
        src_file = ""
    payload = {
        "scene": f"{scene_cls.__module__}.{scene_cls.__qualname__}",
        "duration": round(float(duration), 6),
        "params": params or {},
        "resolution": list(resolution),
        "fps": fps,
        "profile": [profile.name, profile.x264_preset, profile.crf],
        "extra": extra or {},
        "code": _sources_digest([src_file] if src_file else []),
    }
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _key_path(output_path: str) -> Path:
    p = Path(output_path)
    return p.with_name(p.name + ".key")


def cached_clip_is_valid(output_path: str, key: str) -> bool:
    kp = _key_path(output_path)
    try:
        return Path(output_path).is_file() and kp.read_text(encoding="utf-8").strip() == key
    except OSError:
        return False


def store_cache_key(output_path: str, key: str) -> None:
    try:
        _key_path(output_path).write_text(key, encoding="utf-8")
    except OSError as exc:  # la caché nunca debe tumbar un render
        log.warning("No se pudo guardar la clave de caché de %s: %s", output_path, exc)


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


def normalize_clip(src: str, dst: str, fps: int, resolution: Tuple[int, int], frames: int,
                   profile: Optional[RenderProfile] = None) -> str:
    """
    Re-encoda al formato común del pipeline con número de cuadros EXACTO:
    libx264 + yuv420p + CFR + sin audio (igual que simple_animator.py).
    tpad clona el último cuadro si faltara alguno y -frames:v recorta si sobra.
    El perfil decide preset/CRF/hilos de libx264.
    """
    profile = profile or default_profile()
    w, h = resolution
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},"
          f"tpad=stop_mode=clone:stop=-1")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf,
           "-frames:v", str(frames), "-c:v", "libx264", *profile.x264_args(), "-pix_fmt", "yuv420p",
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
    profile: Optional[RenderProfile] = None,
    use_cache: bool = False,
    cache_extra: Optional[Dict] = None,
) -> str:
    """
    Renderiza una escena (nombre registrado o clase TimedScene) a `output_path`
    con duración exacta. Devuelve la ruta del .mp4 normalizado.

    resolution/fps son los FINALES (ya escalados por el perfil); `profile`
    solo decide la codificación (preset/CRF/hilos).

    use_cache=True: si `output_path` ya existe y su clave (<clip>.mp4.key)
    coincide con escena + parámetros + duración + formato + perfil + código
    fuente, no se vuelve a renderizar. cache_extra agrega datos a la clave
    (p. ej. el texto de una FormulaCard generada al vuelo).
    """
    profile = profile or default_profile()
    if fps not in VALID_FPS and profile.is_production:
        log.warning("fps=%s no es 30 ni 60; el compositor espera uno de %s", fps, VALID_FPS)
    if isinstance(scene_name, str):
        scene_cls = get_scene_class(scene_name)
    else:
        scene_cls, scene_name = scene_name, scene_name.__name__
    duration = float(duration or scene_cls.DEFAULT_DURATION)
    resolution = (int(resolution[0]), int(resolution[1]))

    key = None
    if use_cache:
        key = clip_cache_key(scene_cls, duration, params, resolution, fps, profile, cache_extra)
        if cached_clip_is_valid(output_path, key):
            log.info("%s: clip en caché, no se re-renderiza (%s)", scene_name, output_path)
            return str(output_path)

    work = tempfile.mkdtemp(prefix=f"manim_{scene_name}_")
    try:
        with tempconfig(manim_config(work, resolution, fps, scene_name)):
            scene = scene_cls(target_duration=duration, params=params)
            scene.render()
            raw = scene.renderer.file_writer.movie_file_path

        frames = int(round(duration * fps))
        raw_frames = probe_video(str(raw))["frames"]
        if raw_frames != frames:
            log.warning("%s: Manim escribió %d cuadros (esperados %d); se corrige al normalizar.",
                        scene_name, raw_frames, frames)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        normalize_clip(str(raw), output_path, fps, resolution, frames, profile=profile)
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
    # Si este render tuvo que usar texto plano porque LaTeX falló, no se guarda
    # en caché: la próxima corrida (con LaTeX ya arreglado) lo vuelve a generar.
    if key and latex_available():
        store_cache_key(output_path, key)
    return str(output_path)
