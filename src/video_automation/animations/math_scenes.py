"""
Escenas Manim de overlay (HG) — se incrustan SOBRE la base visual del guion.

Aquí viven EXCLUSIVAMENTE las clases de escena. La infraestructura de tramos
y transparencia está en animations/base.py, la exportación en
animations/export.py y las matemáticas puras en fracciones.py.

  Clase         Guion                                   Qué superpone
  ------------  --------------------------------------  -------------------------------------------
  Scene02Math   GUION-02 · Escena 2 · Imágenes 4-5-6    Tercio inferior con:
                «Definir el aprendizaje antes del        - Img 4: borrador del prompt y campos del grupo
                programa»                                - Img 5: 2/4 y 4/8 en unidades iguales = 1/2
                                                         - Img 6: productos cruzados 2×8 = 4×4 = 16 ✓

Diseño de overlay:
  - Todo el contenido vive en un PANEL de pizarrón semitransparente en el
    tercio inferior (posicion="abajo"), que en las ilustraciones es la mesa:
    no tapa caras ni el pizarrón dibujado. También hay "arriba" y "centro".
  - Cada imagen de la base dura 5 s (simple_animator.py), así que la escena
    tiene 3 tramos de 5 s = 15 s y el contenido cambia justo en cada corte.
  - El orden de los tramos es configurable (`orden`) por si la base se arma
    en otro orden.

Render (ver scripts/render_manim_clips.py):
    python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mov
"""

from __future__ import annotations

from typing import Callable, Dict, List

import numpy as np
from manim import (
    DOWN, LEFT, RIGHT, UP,
    Arrow, Create, DashedLine, FadeIn, FadeOut, GrowArrow, Indicate, LaggedStart,
    RoundedRectangle, TransformFromCopy, VGroup, Write,
)

from ..fracciones import are_equivalent, cross_products, parse_fraction, simplify
from ..scenes_video2 import BAD, BG, CHALK, GOLD, MUTED, OK, SHADE, T, check_mark, frac, fraction_rect
from ..manim_timing import tex
from .base import OverlayScene

# Geometría del cuadro de Manim a 16:9: 14.22 x 8 unidades.
FRAME_W, FRAME_H = 14.222, 8.0
PANEL_FILL_OPACITY = 0.9

# Panel por posición: (ancho, alto, centro_y)
PANEL_LAYOUTS: Dict[str, tuple] = {
    "abajo": (13.0, 2.45, -FRAME_H / 2 + 0.2 + 2.45 / 2),
    "arriba": (13.0, 2.45, FRAME_H / 2 - 0.2 - 2.45 / 2),
    "centro": (13.0, 2.45, 0.0),
}


def panel(width: float, height: float) -> RoundedRectangle:
    """Panel de pizarrón con relleno propio (se lee sobre cualquier ilustración)."""
    return RoundedRectangle(corner_radius=0.18, width=width, height=height,
                            fill_color=BG, fill_opacity=PANEL_FILL_OPACITY,
                            stroke_color=CHALK, stroke_width=3)


def tag(text: str, anchor: RoundedRectangle) -> VGroup:
    """Pestaña dorada pegada a la esquina superior izquierda del panel."""
    label = T(text, 22, BG, "BOLD")
    box = RoundedRectangle(corner_radius=0.1, width=label.width + 0.4, height=label.height + 0.22,
                           fill_color=GOLD, fill_opacity=1, stroke_width=0)
    label.move_to(box)
    g = VGroup(box, label)
    g.move_to(anchor.get_corner(UP + LEFT) + RIGHT * (g.width / 2 + 0.35))
    return g


class Scene02Math(OverlayScene):
    """Overlay del GUION-02, Escena 2 (imágenes 4, 5 y 6): 3 tramos de 5 s."""

    SEGMENTS = (5.0, 5.0, 5.0)
    DEFAULT_DURATION = 15.0
    DEFAULT_PARAMS = {
        "a": "2/4",                              # fracción del Detective (img 5 y 6)
        "b": "4/8",                              # fracción de la Profesora Ana
        "orden": ["img04", "img05", "img06"],    # orden de los tramos (como la base)
        "posicion": "abajo",                     # abajo | arriba | centro
        "tramos": None,                          # p. ej. [5, 5, 5]; None = SEGMENTS escalados
    }

    # -- Ensamble ----------------------------------------------------------
    def timeline(self):
        pos = self.params["posicion"]
        if pos not in PANEL_LAYOUTS:
            raise ValueError(f"posicion={pos!r}; usa una de {sorted(PANEL_LAYOUTS)}")
        w, h, cy = PANEL_LAYOUTS[pos]
        self.box = panel(w, h).move_to(UP * cy)

        segments: Dict[str, Callable] = {
            "img04": self.seg_img04_grupo,
            "img05": self.seg_img05_objetivo,
            "img06": self.seg_img06_condiciones,
        }
        order: List[str] = list(self.params["orden"])
        unknown = [k for k in order if k not in segments]
        if unknown:
            raise ValueError(f"Tramos desconocidos {unknown}; disponibles: {sorted(segments)}")

        for i, key in enumerate(order):
            self.segment()
            if i == 0:
                self.beat(FadeIn(self.box, shift=UP * 0.15), t=0.4)
            content = segments[key]()
            # Salida del tramo: el panel solo se va al final del overlay.
            last = i == len(order) - 1
            exits = [FadeOut(content)] + ([FadeOut(self.box)] if last else [])
            self.beat(*exits, t=0.4)

    def _inner(self) -> np.ndarray:
        return self.box.get_center()

    # -- Imagen 4 · ¿Para quién se diseña el material? -----------------------
    def seg_img04_grupo(self) -> VGroup:
        c = self._inner()
        head = tag("Imagen 4 · ¿Para quién se diseña el material?", self.box)

        label = T("Borrador de prompt", 22, MUTED)
        l1 = T("Actúa como especialista en didáctica de las matemáticas.", 28, CHALK)
        l2 = T("El material está dirigido a un grupo con:", 28, CHALK)
        text = VGroup(label, l1, l2).arrange(DOWN, aligned_edge=LEFT, buff=0.14)

        chips = VGroup(*[self._chip(s) for s in ("[grado]", "[conocimientos previos]", "[dificultad]")])
        chips.arrange(RIGHT, buff=0.25)
        left = VGroup(text, chips).arrange(DOWN, aligned_edge=LEFT, buff=0.22)

        warn_txt = VGroup(T("Sin nombres", 24, BAD, "BOLD"), T("ni datos personales", 24, BAD, "BOLD"))
        warn_txt.arrange(DOWN, buff=0.08)
        warn = VGroup(RoundedRectangle(corner_radius=0.12, width=warn_txt.width + 0.45,
                                       height=warn_txt.height + 0.4, stroke_color=BAD,
                                       stroke_width=4), warn_txt)
        warn_txt.move_to(warn[0])

        row = VGroup(left, warn).arrange(RIGHT, buff=0.6)
        row.scale_to_fit_width(min(row.width, self.box.width - 0.7))
        row.move_to(c + DOWN * 0.05)

        self.beat(FadeIn(head, shift=RIGHT * 0.2), FadeIn(label), t=0.4)
        self.beat(Write(l1), t=0.9)
        self.beat(Write(l2), t=0.6)
        self.beat(LaggedStart(*[FadeIn(ch, scale=1.2) for ch in chips], lag_ratio=0.35), t=0.8)
        self.beat(Create(warn[0]), FadeIn(warn_txt), t=0.5)
        self.hold(1.0)
        return VGroup(head, row)

    def _chip(self, text: str) -> VGroup:
        t = T(text, 24, GOLD, "BOLD")
        box = RoundedRectangle(corner_radius=0.12, width=t.width + 0.35, height=t.height + 0.25,
                               stroke_color=GOLD, stroke_width=3)
        t.move_to(box)
        return VGroup(box, t)

    # -- Imagen 5 · Distintas representaciones, la misma fracción -------------
    def seg_img05_objetivo(self) -> VGroup:
        c = self._inner()
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        eq = are_equivalent(a, b)
        head = tag("Imagen 5 · Distintas representaciones", self.box)

        # Unidades del MISMO tamaño, una sobre otra: el área sombreada se alinea.
        ra = fraction_rect(*a, width=3.6, height=0.62)
        rb = fraction_rect(*b, width=3.6, height=0.62)
        bars = VGroup(ra, rb).arrange(DOWN, buff=0.28)
        la = frac(*a, size=34).next_to(ra, LEFT, buff=0.3)
        lb = frac(*b, size=34).next_to(rb, LEFT, buff=0.3)
        left = VGroup(la, lb, bars)

        edge_x = ra.shaded.get_right()[0]
        guide = DashedLine([edge_x, bars.get_top()[1] + 0.15, 0], [edge_x, bars.get_bottom()[1] - 0.15, 0],
                           color=GOLD, stroke_width=5, dash_length=0.1)
        left.add(guide)

        half = simplify(a)
        rel = "=" if eq else r"\neq"
        equation = tex(rf"\frac{{{a[0]}}}{{{a[1]}}} {rel} \frac{{{b[0]}}}{{{b[1]}}}"
                       + (rf" = \frac{{{half[0]}}}{{{half[1]}}}" if eq else ""),
                       font_size=60, color=GOLD)
        caption = T("Distintas representaciones. La misma fracción." if eq
                    else "Se parecen, pero no son la misma fracción.", 26, CHALK, "BOLD")
        right = VGroup(equation, caption).arrange(DOWN, buff=0.25)

        row = VGroup(left, right).arrange(RIGHT, buff=0.8)
        row.scale_to_fit_width(min(row.width, self.box.width - 0.7))
        if row.height > self.box.height - 0.45:
            row.scale_to_fit_height(self.box.height - 0.45)
        row.move_to(c + DOWN * 0.05)

        ra.shaded.set_fill(opacity=0)
        rb.shaded.set_fill(opacity=0)
        self.beat(FadeIn(head, shift=RIGHT * 0.2), t=0.3)
        self.beat(Create(ra.cells), Create(rb.cells), FadeIn(la), FadeIn(lb), t=0.8)
        self.beat(LaggedStart(*[x.animate.set_fill(SHADE, 0.9) for x in ra.shaded], lag_ratio=0.3),
                  LaggedStart(*[x.animate.set_fill(SHADE, 0.9) for x in rb.shaded], lag_ratio=0.3), t=0.9)
        self.beat(Create(guide), t=0.5)
        self.beat(Write(equation), t=0.9)
        self.beat(FadeIn(caption, shift=UP * 0.1), t=0.4)
        self.hold(0.9)
        return VGroup(head, row)

    # -- Imagen 6 · Las matemáticas también deben especificarse ---------------
    def seg_img06_condiciones(self) -> VGroup:
        c = self._inner()
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        left_p, right_p = cross_products(a, b)
        eq = left_p == right_p
        head = tag("Imagen 6 · Las matemáticas también deben especificarse", self.box)

        fa, fb = frac(*a, size=60), frac(*b, size=60)
        sign = tex("=" if eq else r"\neq", font_size=60, color=OK if eq else BAD)
        fracs = VGroup(fa, sign, fb).arrange(RIGHT, buff=1.0)

        ar1 = Arrow(fa.num.get_center(), fb.den.get_center(), buff=0.22, color=GOLD,
                    stroke_width=5, max_tip_length_to_length_ratio=0.15)
        ar2 = Arrow(fb.num.get_center(), fa.den.get_center(), buff=0.22, color=SHADE,
                    stroke_width=5, max_tip_length_to_length_ratio=0.15)
        sign.set_opacity(0)

        p1 = tex(rf"{a[0]} \times {b[1]} = {left_p}", font_size=46, color=GOLD)
        p2 = tex(rf"{b[0]} \times {a[1]} = {right_p}", font_size=46, color=SHADE)
        prods = VGroup(p1, p2).arrange(DOWN, buff=0.3, aligned_edge=LEFT)

        rel = "=" if eq else r"\neq"
        verdict = tex(rf"{left_p} {rel} {right_p}", font_size=56, color=OK if eq else BAD)
        mark = check_mark(eq, 44)
        vrow = VGroup(verdict, mark).arrange(RIGHT, buff=0.25)
        note = T("Enteros, sin decimales", 24, MUTED)
        right = VGroup(vrow, note).arrange(DOWN, buff=0.2)

        row = VGroup(VGroup(fracs, ar1, ar2), prods, right).arrange(RIGHT, buff=0.9)
        row.scale_to_fit_width(min(row.width, self.box.width - 0.7))
        if row.height > self.box.height - 0.45:
            row.scale_to_fit_height(self.box.height - 0.45)
        row.move_to(c + DOWN * 0.05)

        self.beat(FadeIn(head, shift=RIGHT * 0.2), Write(fa), Write(fb), t=0.6)
        self.beat(GrowArrow(ar1), t=0.4)
        self.beat(TransformFromCopy(VGroup(fa.num, fb.den), p1), t=0.7)
        self.beat(GrowArrow(ar2), t=0.4)
        self.beat(TransformFromCopy(VGroup(fb.num, fa.den), p2), t=0.7)
        # Las flechas ya hicieron su trabajo: se retiran y aparece el signo entre las fracciones.
        self.beat(Write(verdict), FadeIn(mark, scale=1.4), FadeOut(ar1), FadeOut(ar2),
                  sign.animate.set_opacity(1), t=0.6)
        self.beat(FadeIn(note), Indicate(vrow, color=OK if eq else BAD, scale_factor=1.08), t=0.5)
        self.hold(0.7)
        return VGroup(head, fracs, prods, right)


# ---------------------------------------------------------------------------
# Registro: --scene <nombre> en scripts/render_manim_clips.py
# ---------------------------------------------------------------------------
SCENE_REGISTRY: Dict[str, type] = {
    cls.__name__: cls
    for cls in (
        Scene02Math,
    )
}
