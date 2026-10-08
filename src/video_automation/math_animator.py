"""
Módulo Visual y Animaciones Dinámicas (math_animator.py) — HG.

Motor base de animaciones matemáticas parametrizables con Manim. La escena NO
tiene contenido escrito en código: todo sale de un archivo de configuración
(JSON o YAML) o de un diccionario con la misma estructura.

Esquema de la configuración
---------------------------

    {
      "name": "formula_general",          # opcional: nombre del .mp4 (por defecto, el del archivo)
      "duration": 2.5,                    # segundos POR ELEMENTO (animación + pausa)
      "animation_time": 1.0,              # duración de la animación dentro de ese tiempo
      "latex_expressions": [
        "ax^2 + bx + c = 0",              # forma corta: solo el LaTeX
        {"tex": "x^2 + \\frac{b}{a}x = -\\frac{c}{a}",
         "animation": "transform",        # write | transform | fadein
         "duration": 3.0}                 # sobrescribe la duración global
      ],
      "text_labels": [
        {"text": "La fórmula general", "position": "UP"},          # aparece con la expresión 0
        {"text": "Dividimos entre a", "position": "DOWN", "step": 1}
      ]
    }

Reglas:
  - Las expresiones se muestran en orden, una a la vez, al centro. Por defecto
    la primera usa Write y las siguientes Transform (la anterior se convierte
    en la nueva). Con write/fadein la anterior se desvanece primero.
  - Cada etiqueta entra junto con la expresión indicada en `step` (0 = la
    primera). Una etiqueta nueva en la misma posición reemplaza a la anterior.
  - Posiciones: UP, DOWN, LEFT, RIGHT, UL, UR, DL, DR, CENTER.
  - Duración total del clip = suma de las duraciones de cada expresión.
  - Fondo oscuro del canal (#1E3A2F, el mismo pizarrón de scenes_video2 y de
    los overlays) salvo que la configuración diga otra cosa.

Calidad (banderas equivalentes a las de Manim):
  - low  / -ql : borrador, 854x480 a 15 fps → <nombre>_low.mp4
  - high / -qh : producción, 1920x1080 a 60 fps → <nombre>.mp4

Los .mp4 se centralizan en data/renders/manim/.

Uso:
    python -m src.video_automation.math_animator --config data/scenes/sample_math.json --quality low
    python -m src.video_automation.math_animator --config data/scenes/sample_math.json -qh
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, Union

import yaml
from manim import (
    DL, DOWN, DR, LEFT, ORIGIN, RIGHT, UL, UP, UR,
    Animation, AnimationGroup, Camera, FadeIn, ManimColor, FadeOut, Mobject, ReplacementTransform,
    Scene, Text, VMobject, Wait, Write, tempconfig,
)
from manim import config as mconfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .manim_timing import manim_config, tex
from .render_profiles import get_profile

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "renders" / "manim"

CHANNEL_BG = "#1E3A2F"      # pizarrón del canal (scenes_video2.BG / OverlayScene.BACKGROUND)
CHALK = "#F5F1E6"           # gis
#: Fuentes en orden de preferencia; se usa la primera instalada (DejaVu en Linux/Docker,
#: Segoe UI o Arial en Windows). $VA_FONT tiene prioridad si existe en el sistema.
FONT_CANDIDATES: Tuple[str, ...] = ("DejaVu Sans", "Segoe UI", "Arial", "Helvetica",
                                    "Liberation Sans", "Noto Sans", "Sans")

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"

Position = Literal["UP", "DOWN", "LEFT", "RIGHT", "UL", "UR", "DL", "DR", "CENTER"]
AnimationKind = Literal["write", "transform", "fadein"]
QualityName = Literal["low", "high"]

_ANIMATION_ALIASES: Dict[str, str] = {
    "write": "write", "escribir": "write",
    "transform": "transform", "transformar": "transform", "replacementtransform": "transform",
    "fadein": "fadein", "fade_in": "fadein", "fade-in": "fadein", "fade": "fadein",
}
_POSITION_ALIASES: Dict[str, str] = {
    "ARRIBA": "UP", "TOP": "UP", "ABAJO": "DOWN", "BOTTOM": "DOWN",
    "IZQUIERDA": "LEFT", "DERECHA": "RIGHT", "CENTRO": "CENTER", "ORIGIN": "CENTER",
    "UP_LEFT": "UL", "UP_RIGHT": "UR", "DOWN_LEFT": "DL", "DOWN_RIGHT": "DR",
}


@lru_cache(maxsize=1)
def resolve_font() -> str:
    """
    Primera fuente disponible de $VA_FONT + FONT_CANDIDATES. Evita el aviso
    "Font DejaVu Sans not in [...]" de Manim en equipos que no la tienen
    (Windows). "" = fuente por defecto de Pango.
    """
    preferred = os.environ.get("VA_FONT", "").strip()
    candidates = ((preferred,) if preferred else ()) + FONT_CANDIDATES
    try:
        import manimpango

        available = set(manimpango.list_fonts())
    except Exception:  # noqa: BLE001 - sin lista de fuentes, se intenta la primera
        return candidates[0]
    if preferred and preferred not in available:
        log.warning("VA_FONT=%r no está instalada; se usa otra fuente.", preferred)
    for name in candidates:
        if name in available:
            return name
    return ""


class SceneConfigError(ValueError):
    """La configuración de la escena no existe, no se puede leer o no es válida."""


# ---------------------------------------------------------------------------
# Esquema de configuración (pydantic)
# ---------------------------------------------------------------------------

class LatexStep(BaseModel):
    """Una expresión LaTeX (sin $ ni \\[ \\]) y cómo entra a escena."""

    model_config = ConfigDict(extra="forbid")

    tex: str = Field(min_length=1)
    animation: Optional[AnimationKind] = None
    duration: Optional[float] = Field(default=None, gt=0)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    font_size: Optional[float] = Field(default=None, gt=0)

    @field_validator("tex")
    @classmethod
    def _strip_tex(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("la expresión LaTeX está vacía")
        return value

    @field_validator("animation", mode="before")
    @classmethod
    def _normalize_animation(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().lower()
            return _ANIMATION_ALIASES.get(key, key)
        return value


class TextLabel(BaseModel):
    """Texto explicativo con posición en pantalla."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    position: Position = "DOWN"
    #: Índice de la expresión con la que aparece (0 = la primera).
    step: int = Field(default=0, ge=0)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    font_size: Optional[float] = Field(default=None, gt=0)

    @field_validator("position", mode="before")
    @classmethod
    def _normalize_position(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().upper()
            return _POSITION_ALIASES.get(key, key)
        return value


class MathSceneConfig(BaseModel):
    """Estructura completa de una escena matemática dinámica."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    title: Optional[str] = None          # solo informativo
    description: Optional[str] = None    # solo informativo
    latex_expressions: List[LatexStep] = Field(min_length=1)
    text_labels: List[TextLabel] = Field(default_factory=list)
    #: Segundos por elemento (animación + pausa).
    duration: float = Field(default=2.0, gt=0)
    #: Segundos de animación dentro de `duration` (el resto es pausa).
    animation_time: float = Field(default=1.0, gt=0)
    background_color: str = Field(default=CHANNEL_BG, pattern=HEX_COLOR)
    text_color: str = Field(default=CHALK, pattern=HEX_COLOR)
    tex_font_size: float = Field(default=64, gt=0)
    label_font_size: float = Field(default=34, gt=0)
    #: Desvanecer todo al final (agrega `animation_time` / 2 segundos).
    fade_out: bool = False

    @field_validator("latex_expressions", mode="before")
    @classmethod
    def _expand_latex_shorthand(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"tex": item} if isinstance(item, str) else item for item in value]
        return value

    @field_validator("text_labels", mode="before")
    @classmethod
    def _expand_label_shorthand(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, list):
            return [{"text": item} if isinstance(item, str) else item for item in value]
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "MathSceneConfig":
        if self.latex_expressions[0].animation == "transform":
            raise ValueError("la primera expresión no puede usar 'transform' (no hay nada que "
                             "transformar); usa 'write' o 'fadein'")
        n = len(self.latex_expressions)
        seen: set[Tuple[int, str]] = set()
        for label in self.text_labels:
            if label.step >= n:
                raise ValueError(f"la etiqueta {label.text!r} usa step={label.step}, pero solo hay "
                                 f"{n} expresiones (0..{n - 1})")
            slot = (label.step, label.position)
            if slot in seen:
                raise ValueError(f"dos etiquetas en la posición {label.position} del step {label.step}")
            seen.add(slot)
        return self

    # -- Helpers ------------------------------------------------------------
    def animation_for(self, index: int) -> AnimationKind:
        explicit = self.latex_expressions[index].animation
        if explicit is not None:
            return explicit
        return "write" if index == 0 else "transform"

    def duration_for(self, index: int) -> float:
        step_duration = self.latex_expressions[index].duration
        return float(step_duration if step_duration is not None else self.duration)

    def labels_for_step(self, index: int) -> List[TextLabel]:
        return [label for label in self.text_labels if label.step == index]

    def total_duration(self) -> float:
        total = sum(self.duration_for(i) for i in range(len(self.latex_expressions)))
        if self.fade_out:
            total += self.animation_time / 2
        return total


def load_scene_config(source: Union[Path, str, Mapping[str, Any]]) -> MathSceneConfig:
    """
    Lee y valida la configuración desde un .json, .yaml/.yml o un diccionario.
    Lanza SceneConfigError con un mensaje claro si algo falla.
    """
    origin = "diccionario"
    if isinstance(source, Mapping):
        raw: Any = dict(source)
    else:
        path = Path(source)
        origin = str(path)
        if not path.is_file():
            raise SceneConfigError(f"No existe el archivo de configuración: {path}")
        suffix = path.suffix.lower()
        try:
            text = path.read_text(encoding="utf-8")
            if suffix == ".json":
                raw = json.loads(text)
            elif suffix in (".yaml", ".yml"):
                raw = yaml.safe_load(text)
            else:
                raise SceneConfigError(f"Formato no soportado {suffix!r} en {path}; usa .json, .yaml o .yml")
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise SceneConfigError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SceneConfigError(f"{origin}: la raíz de la configuración debe ser un objeto/diccionario")
    try:
        return MathSceneConfig.model_validate(raw)
    except ValidationError as exc:
        raise SceneConfigError(f"Configuración inválida en {origin}:\n{exc}") from exc


# ---------------------------------------------------------------------------
# Calidad de render
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualitySettings:
    name: QualityName
    flag: str
    resolution: Tuple[int, int]
    fps: int
    #: Perfil de render_profiles.py asociado (prioridad del proceso).
    profile_name: str
    #: Sufijo del archivo: los borradores no pisan el render de producción.
    suffix: str
    description: str


QUALITY_PRESETS: Dict[str, QualitySettings] = {
    "low": QualitySettings(
        name="low", flag="-ql", resolution=(854, 480), fps=15, profile_name="fast",
        suffix="_low", description="Borrador: 480p a 15 fps para previsualizar rápido.",
    ),
    "high": QualitySettings(
        name="high", flag="-qh", resolution=(1920, 1080), fps=60, profile_name="production",
        suffix="", description="Producción: 1080p a 60 fps para el ensamble final.",
    ),
}

QUALITY_ALIASES: Dict[str, str] = {
    "l": "low", "ql": "low", "-ql": "low", "draft": "low", "borrador": "low",
    "fast": "low", "preview": "low", "480p": "low",
    "h": "high", "qh": "high", "-qh": "high", "production": "high", "produccion": "high",
    "producción": "high", "prod": "high", "final": "high", "1080p": "high",
}


def resolve_quality(quality: str) -> QualitySettings:
    """Nombre o alias (low, -ql, borrador, high, -qh, producción...) → QualitySettings."""
    key = quality.strip().lower()
    key = QUALITY_ALIASES.get(key, key)
    if key not in QUALITY_PRESETS:
        raise ValueError(f"Calidad desconocida {quality!r}. Usa 'low' (-ql) o 'high' (-qh).")
    return QUALITY_PRESETS[key]


def safe_name(name: str) -> str:
    """Nombre de archivo seguro en Windows y Linux."""
    cleaned = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return cleaned or "math_scene"


def output_path_for(name: str, quality: QualitySettings, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return Path(output_dir) / f"{safe_name(name)}{quality.suffix}.mp4"


# ---------------------------------------------------------------------------
# Escena Manim
# ---------------------------------------------------------------------------

_DIRECTIONS = {
    "UP": UP, "DOWN": DOWN, "LEFT": LEFT, "RIGHT": RIGHT,
    "UL": UL, "UR": UR, "DL": DL, "DR": DR,
}


class DynamicMathScene(Scene):
    """
    Escena genérica: anima las expresiones y etiquetas que trae la
    configuración. No tiene contenido propio.
    """

    EDGE_BUFF = 0.5

    def __init__(self, scene_config: Union[MathSceneConfig, Mapping[str, Any]], **kwargs: Any) -> None:
        self.scene_config: MathSceneConfig = (
            scene_config if isinstance(scene_config, MathSceneConfig) else load_scene_config(scene_config)
        )
        super().__init__(**kwargs)

    # -- Construcción de mobjects -----------------------------------------
    def setup(self) -> None:
        super().setup()
        camera = self.camera
        if isinstance(camera, Camera):  # renderer Cairo (el que usa el pipeline)
            camera.background_color = ManimColor(self.scene_config.background_color)
            camera.init_background()

    def _has_side_labels(self) -> bool:
        return any(label.position in ("LEFT", "RIGHT") for label in self.scene_config.text_labels)

    def build_expression(self, step: LatexStep) -> VMobject:
        cfg = self.scene_config
        expr: VMobject = tex(step.tex, font_size=step.font_size or cfg.tex_font_size,
                             color=step.color or cfg.text_color)
        frame_w, frame_h = mconfig.frame_width, mconfig.frame_height
        max_w = frame_w * (0.55 if self._has_side_labels() else 0.85)
        if expr.width > max_w:
            expr.scale_to_fit_width(max_w)
        if expr.height > frame_h * 0.5:
            expr.scale_to_fit_height(frame_h * 0.5)
        return expr.move_to(ORIGIN)

    def build_label(self, label: TextLabel) -> Text:
        cfg = self.scene_config
        mob = Text(label.text, font=resolve_font(), font_size=label.font_size or cfg.label_font_size,
                   color=label.color or cfg.text_color)
        frame_w = mconfig.frame_width
        max_w = frame_w * (0.2 if label.position in ("LEFT", "RIGHT") else 0.9)
        if mob.width > max_w:
            mob.scale_to_fit_width(max_w)
        if label.position == "CENTER":
            return mob.move_to(ORIGIN)
        direction = _DIRECTIONS[label.position]
        if label.position in ("UL", "UR", "DL", "DR"):
            return mob.to_corner(direction, buff=self.EDGE_BUFF)
        return mob.to_edge(direction, buff=self.EDGE_BUFF)

    # -- Línea de tiempo --------------------------------------------------
    def entry_animation(self, kind: AnimationKind, current: Optional[Mobject], new: VMobject) -> Animation:
        if kind == "transform" and current is not None:
            return ReplacementTransform(current, new)
        enter: Animation = Write(new) if kind == "write" else FadeIn(new, shift=UP * 0.3)
        if current is None:
            return enter
        # Primero sale la expresión anterior y después entra la nueva.
        return AnimationGroup(FadeOut(current), enter, lag_ratio=1.0)

    # -- Control de cuadros (duración exacta, igual que manim_timing.TimedScene)
    @property
    def fps(self) -> int:
        return int(round(self.camera.frame_rate))

    def frames_written(self) -> int:
        return int(round(self.renderer.time * self.fps))

    def play_frames(self, *animations: Animation, frames: int) -> None:
        """Manim genera ceil(run_time*fps) cuadros: (n-0.5)/fps da exactamente n."""
        self.play(*animations, run_time=(max(frames, 1) - 0.5) / self.fps)

    def hold_until(self, edge: int) -> None:
        """Pausa congelada hasta el cuadro absoluto `edge` (se autocorrige)."""
        n = edge - self.frames_written()
        if n > 0:
            # Wait congelado usa int(duration*fps) cuadros → (n+0.25)/fps da n.
            self.play(Wait(run_time=(n + 0.25) / self.fps, frozen_frame=True))

    def construct(self) -> None:
        cfg = self.scene_config
        current: Optional[Mobject] = None
        labels_on_screen: Dict[str, Mobject] = {}
        elapsed = 0.0

        for index, step in enumerate(cfg.latex_expressions):
            expr = self.build_expression(step)
            animations: List[Animation] = [self.entry_animation(cfg.animation_for(index), current, expr)]

            for label in cfg.labels_for_step(index):
                mob = self.build_label(label)
                previous = labels_on_screen.pop(label.position, None)
                if previous is not None:
                    animations.append(FadeOut(previous))
                animations.append(FadeIn(mob))
                labels_on_screen[label.position] = mob

            total = cfg.duration_for(index)
            run_time = min(cfg.animation_time, total)
            # Fronteras acumuladas redondeadas: la duración total no arrastra error.
            edge = int(round((elapsed + total) * self.fps))
            anim_frames = min(int(round(run_time * self.fps)), edge - self.frames_written())
            self.play_frames(*animations, frames=anim_frames)
            self.hold_until(edge)
            elapsed += total
            current = expr

        if cfg.fade_out and self.mobjects:
            fade = cfg.animation_time / 2
            edge = int(round((elapsed + fade) * self.fps))
            self.play_frames(*(FadeOut(m) for m in list(self.mobjects)),
                             frames=edge - self.frames_written())


# ---------------------------------------------------------------------------
# Render programático
# ---------------------------------------------------------------------------

def _run_manim(scene_config: MathSceneConfig, quality: QualitySettings, media_dir: Path,
               output_name: str) -> Path:
    """Renderiza la escena con Manim dentro de media_dir y devuelve el .mp4 crudo."""
    cfg: Dict[str, Any] = manim_config(str(media_dir), quality.resolution, quality.fps, output_name)
    cfg["background_color"] = scene_config.background_color
    with tempconfig(cfg):
        scene = DynamicMathScene(scene_config)
        scene.render()
        movie = Path(scene.renderer.file_writer.movie_file_path)
    if not movie.is_file():
        raise RuntimeError(f"Manim no generó el video esperado: {movie}")
    return movie


def render_scene_from_config(config_path: Path, quality: str = "low",
                             output_dir: Optional[Path] = None) -> Path:
    """
    Lee la configuración, renderiza DynamicMathScene con Manim y deja el .mp4
    en data/renders/manim/ (u output_dir). Devuelve la ruta del video.

    quality: "low" (-ql, 480p@15) o "high" (-qh, 1080p@60); acepta alias.
    """
    config_path = Path(config_path)
    scene_config = load_scene_config(config_path)
    settings = resolve_quality(quality)
    name = scene_config.name or config_path.stem
    target = output_path_for(name, settings, Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR)
    target.parent.mkdir(parents=True, exist_ok=True)

    w, h = settings.resolution
    print(f"🎬 {config_path.name} → {target} [{settings.name} {settings.flag} {w}x{h}@{settings.fps}fps, "
          f"{len(scene_config.latex_expressions)} expresiones, ~{scene_config.total_duration():.1f}s]")

    work = Path(tempfile.mkdtemp(prefix="math_animator_"))
    try:
        raw = _run_manim(scene_config, settings, work, safe_name(name))
        if target.exists():
            target.unlink()
        shutil.move(str(raw), str(target))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError(f"El render terminó pero no se encontró un video válido en {target}")
    print(f"✅ Video listo: {target}")
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.video_automation.math_animator",
        description="Renderiza una escena matemática dinámica de Manim a partir de un JSON/YAML.",
    )
    parser.add_argument("--config", required=True, type=Path,
                        help="Ruta al archivo de escena (.json, .yaml o .yml)")
    quality = parser.add_mutually_exclusive_group()
    quality.add_argument("--quality", default=None, metavar="CALIDAD",
                         help="low (borrador 480p@15) o high (producción 1080p@60). Por defecto: low")
    quality.add_argument("-ql", dest="quality", action="store_const", const="low",
                         help=QUALITY_PRESETS["low"].description)
    quality.add_argument("-qh", dest="quality", action="store_const", const="high",
                         help=QUALITY_PRESETS["high"].description)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help=f"Carpeta de salida (por defecto: {DEFAULT_OUTPUT_DIR})")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    quality_name: str = args.quality or "low"
    try:
        settings = resolve_quality(quality_name)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    get_profile(settings.profile_name).apply_process_limits()
    try:
        render_scene_from_config(args.config, settings.name, args.output_dir)
    except SceneConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - la CLI reporta cualquier falla de render
        log.exception("Falló el render")
        print(f"❌ Error al renderizar: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
