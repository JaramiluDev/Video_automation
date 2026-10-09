"""
Base para overlays de Manim que se incrustan sobre la base visual (Ken Burns).

OverlayScene extiende TimedScene (manim_timing.py) con dos cosas:

1. TRAMOS ALINEADOS A LA BASE. La base visual de cada escena del guion son
   clips de 5 s por imagen (simple_animator.py). Un overlay que acompaña a
   varias imágenes se divide en tramos y cada tramo recibe EXACTAMENTE sus
   cuadros (fronteras redondeadas acumuladas), así el cambio de contenido del
   overlay cae en el mismo cuadro que el corte de imagen de la base.

       def timeline(self):
           self.segment()              # tramo 1
           self.beat(Write(a), t=1.0)
           self.hold(2.0)
           self.segment()              # tramo 2
           ...

   Dentro de cada tramo rigen las mismas reglas de TimedScene: si sobra tiempo
   se alargan las pausas (hold) y si falta se comprime todo.

2. FONDO TRANSPARENTE OPCIONAL. Con transparent=True la cámara no pinta el
   pizarrón de fondo: solo se ven los paneles, que llevan su propio relleno
   semitransparente para que el texto se lea sobre cualquier ilustración.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from ..manim_timing import TimedScene, plan_frames

log = logging.getLogger(__name__)


def segment_frames(durations: Sequence[float], fps: int) -> List[int]:
    """Cuadros por tramo con fronteras acumuladas redondeadas (la suma cuadra)."""
    frames, acc, prev = [], 0.0, 0
    for d in durations:
        acc += float(d)
        edge = int(round(acc * fps))
        frames.append(edge - prev)
        prev = edge
    return frames


class OverlayScene(TimedScene):
    """TimedScene dividida en tramos y con fondo transparente opcional."""

    #: Duración nominal de cada tramo (s). Por defecto 5 s = un clip de simple_animator.
    SEGMENTS: Tuple[float, ...] = ()
    #: Color de fondo cuando el render es opaco (.mp4).
    BACKGROUND: str = "#1E3A2F"

    def __init__(self, target_duration: Optional[float] = None, params: Optional[Dict] = None,
                 transparent: bool = False, **kwargs):
        self.transparent = bool(transparent)
        self._seg_index = -1
        self._beat_segments: List[int] = []
        super().__init__(target_duration=target_duration, params=params, **kwargs)

    # -- Configuración de tramos -------------------------------------------
    def segment_durations(self) -> List[float]:
        """
        Duración final de cada tramo.

        - params["tramos"] = [5, 5, 5] fija cada tramo (su suma debe ser la
          duración total; si no, se escala proporcionalmente).
        - Sin "tramos", se escalan los SEGMENTS nominales a la duración objetivo.
        """
        base = [float(x) for x in (self.params.get("tramos") or self.default_segments())]
        if not base or any(d <= 0 for d in base):
            raise ValueError(f"Tramos inválidos: {base}")
        total = sum(base)
        if abs(total - self.target_duration) > 1e-6:
            factor = self.target_duration / total
            base = [d * factor for d in base]
        return base

    def default_segments(self) -> List[float]:
        return list(self.SEGMENTS) or [self.target_duration]

    def segment(self):
        """Marca el inicio de un tramo nuevo dentro de timeline()."""
        self._seg_index += 1

    # -- Integración con TimedScene ----------------------------------------
    def beat(self, *animations, t: float = 1.0, **play_kwargs):
        if self._dry:
            self._beat_segments.append(max(self._seg_index, 0))
        super().beat(*animations, t=t, **play_kwargs)

    def hold(self, t: float = 1.0):
        if self._dry:
            self._beat_segments.append(max(self._seg_index, 0))
        super().hold(t=t)

    def setup(self):
        super().setup()
        if not self.transparent:
            self.camera.background_color = self.BACKGROUND
            if hasattr(self.camera, "init_background"):
                self.camera.init_background()

    def build_plan(self) -> List[int]:
        durations = self.segment_durations()
        n_seg = max(self._beat_segments, default=0) + 1
        if n_seg != len(durations):
            raise ValueError(f"{type(self).__name__}: timeline() declaró {n_seg} tramo(s) "
                             f"pero hay {len(durations)} duración(es): {durations}")
        seg_frames = segment_frames(durations, self.fps)
        plan: List[int] = []
        for s, n_frames in enumerate(seg_frames):
            beats = [b for b, seg in zip(self._beats, self._beat_segments) if seg == s]
            if not beats:
                raise ValueError(f"El tramo {s + 1} no tiene beats.")
            plan.extend(plan_frames(beats, n_frames / self.fps, self.fps))
        log.info("%s: tramos %s s → cuadros %s @%dfps", type(self).__name__,
                 [round(d, 3) for d in durations], seg_frames, self.fps)
        return plan

    def construct(self):
        # 1) Pasada en seco: registra beats y a qué tramo pertenece cada uno.
        self._dry = True
        self._beats, self._beat_segments, self._seg_index = [], [], -1
        self.timeline()
        self.clear()
        self._dry = False

        # 2) Plan exacto, tramo por tramo.
        self._plan = self.build_plan()
        self._cursor, self._edge, self._seg_index = 0, 0, -1

        # 3) Pasada real.
        self.timeline()

        # 4) Relleno final por si algún beat quedó corto.
        remaining = self.total_frames - self.frames_written()
        if remaining > 0:
            self._freeze(remaining)
        elif remaining < 0:
            log.warning("%s excedió %d cuadro(s); la exportación lo recorta.",
                        type(self).__name__, -remaining)
