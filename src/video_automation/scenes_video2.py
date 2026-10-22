"""
Escenas de Manim del Video 2 — "Dominó de fracciones equivalentes" (GUION-02).

Aquí viven EXCLUSIVAMENTE las clases Manim de este entregable. La lógica
matemática está en fracciones.py y el control de tiempo/exportación en
manim_timing.py.

Cada clase corresponde a una imagen del guion que necesita matemáticas exactas
(las ilustraciones de GUION-02 traen particiones y fracciones que no siempre
coinciden con el guion; estas escenas son la versión correcta):

  Clase                                Guion (escena / imagen)        Mensaje en pantalla
  -----------------------------------  -----------------------------  -------------------------------------------
  V2E02_RepresentacionesEquivalentes   Escena 2 · Imagen 5            «Distintas representaciones. La misma fracción»
  V2E02_ProductosCruzados              Escena 2 · Imagen 6            «Las matemáticas también deben especificarse»
  V2E03_UnionDomino                    Escena 3 · Imagen 7            «Se unen los extremos equivalentes»
  V2E03_ColorUniforme                  Escena 3 · Imagen 9            «Comparar valores, no colores»
  V2E04_NivelesDificultad              Escena 4 · Imagen 10           «La dificultad debe tener características concretas»
  V2E04_FigurasRepresentacion          Escena 4 · Imagen 11           «Fracciones, imágenes o ambas»
  V2E06_MedidasFicha                   Escena 6 · Imágenes 16-17      «Recorta el contorno; conserva las dos mitades»
  V2E07_CadenaCompleta                 Escena 7 · Imagen 21           «Lo que se pide también debe poder revisarse»
  V2E09_ComprobacionManual             Escena 9 · Imagen 27           «No basta con que las fichas se vean bien»
  V2E12_CierreRecorrido                Escena 12 · Imagen 36          «Diseña. Pide. Comprueba. Enseña.»

Uso desde el YAML del guion:

    - id: "ESCENA-02-B"
      render_type: "manim"
      manim_scene: "V2E02_ProductosCruzados"
      manim_params: {a: "2/4", b: "4/8"}
      duration: 9.5          # ← el clip durará EXACTAMENTE esto

Previsualizar una escena suelta (fuera del pipeline):
    python scripts/render_video2_scenes.py examples/video2_manim.yaml --only V2E02_ProductosCruzados --preview
"""

from __future__ import annotations

import os
import random
from typing import Dict, List, Sequence, Tuple

import numpy as np
from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP, UL, UR, DL, DR, PI, TAU,
    Arrow, Circle, Create, Cross, DashedLine, DashedVMobject, DoubleArrow,
    FadeIn, FadeOut, GrowArrow, GrowFromCenter, Indicate, LaggedStart, Line,
    Rectangle, ReplacementTransform, RoundedRectangle, Sector,
    SurroundingRectangle, Text, TransformFromCopy, VGroup, Write, config,
)

from .fracciones import (
    NIVELES, HalfRepr, are_equivalent, cross_products, eulerian_chain,
    expected_tile_count, generate_tiles, parse_fraction, representation_for,
    simplify, validate_chain,
)
from .manim_timing import TimedScene, tex

# ---------------------------------------------------------------------------
# Estilo (pizarrón verde + gis + acento morado, como las ilustraciones)
# ---------------------------------------------------------------------------
BG = "#1E3A2F"          # pizarrón
CHALK = "#F5F1E6"       # gis
MUTED = "#A9B8AE"       # texto secundario
SHADE = "#B08AE0"       # sombreado ÚNICO para todas las familias (regla del guion)
GOLD = "#F4C95D"        # resaltado / uniones
OK = "#9BE58A"
BAD = "#FF8A80"
FONT = os.environ.get("VA_FONT", "DejaVu Sans")


def T(text: str, size: float = 36, color: str = CHALK, weight: str = "NORMAL") -> Text:
    return Text(text, font=FONT, font_size=size, color=color, weight=weight)


def titulo(text: str) -> Text:
    return T(text, 40, CHALK, "BOLD").to_edge(UP, buff=0.45)


def rotulo(text: str) -> VGroup:
    """Mensaje principal de la imagen del guion, en la franja inferior."""
    label = T(text, 34, GOLD, "BOLD")
    bar = Line(LEFT, RIGHT, color=SHADE, stroke_width=4).scale_to_fit_width(label.width + 0.6)
    bar.next_to(label, DOWN, buff=0.15)
    return VGroup(label, bar).to_edge(DOWN, buff=0.45)


def frac(num: int, den: int, size: float = 64, color: str = CHALK) -> VGroup:
    """Fracción construida a mano para poder señalar numerador y denominador."""
    n = tex(str(num), font_size=size, color=color)
    d = tex(str(den), font_size=size, color=color)
    width = max(n.width, d.width) + 0.25 * size / 64
    bar = Line(LEFT, RIGHT, color=color, stroke_width=4 * size / 64).scale_to_fit_width(width)
    n.next_to(bar, UP, buff=0.12 * size / 64)
    d.next_to(bar, DOWN, buff=0.12 * size / 64)
    g = VGroup(n, bar, d)
    g.num, g.bar, g.den = n, bar, d
    return g


def _grid_shape(den: int) -> Tuple[int, int]:
    """Filas x columnas de partes iguales: 1 fila hasta 8, 2 filas si es mayor."""
    if den <= 8:
        return 1, den
    rows = 2 if den % 2 == 0 else 1
    return rows, den // rows


def fraction_rect(num: int, den: int, width: float = 4.0, height: float = 1.6,
                  shade: str = SHADE, hatch: bool = False, stroke: str = CHALK) -> VGroup:
    """Unidad rectangular dividida en `den` partes de IGUAL área, `num` sombreadas."""
    rows, cols = _grid_shape(den)
    cw, ch = width / cols, height / rows
    cells = VGroup()
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            cell = Rectangle(width=cw, height=ch, stroke_color=stroke, stroke_width=3)
            cell.move_to(np.array([-width / 2 + cw * (c + 0.5), height / 2 - ch * (r + 0.5), 0]))
            if idx < num:
                cell.set_fill(shade, opacity=0.0 if hatch else 0.9)
            cells.add(cell)
    g = VGroup(cells)
    if hatch:
        g.add(_hatch(cells[:num], stroke))
    g.cells = cells
    g.shaded = VGroup(*cells[:num])
    return g


def _hatch(cells: Sequence[Rectangle], color: str, spacing: float = 0.16) -> VGroup:
    """Trama diagonal recortada a cada celda (versión blanco y negro)."""
    lines = VGroup()
    for cell in cells:
        x0, x1 = cell.get_left()[0], cell.get_right()[0]
        y0, y1 = cell.get_bottom()[1], cell.get_top()[1]
        c = x0 - y1
        while c < x1 - y0:
            # Recta y = x - c recortada al rectángulo.
            pts = []
            for x in (x0, x1):
                y = x - c
                if y0 - 1e-9 <= y <= y1 + 1e-9:
                    pts.append((x, y))
            for y in (y0, y1):
                x = y + c
                if x0 - 1e-9 <= x <= x1 + 1e-9:
                    pts.append((x, y))
            pts = sorted(set((round(px, 6), round(py, 6)) for px, py in pts))
            if len(pts) >= 2:
                (ax, ay), (bx, by) = pts[0], pts[-1]
                if abs(ax - bx) + abs(ay - by) > 1e-3:
                    lines.add(Line([ax, ay, 0], [bx, by, 0], color=color, stroke_width=2))
            c += spacing
    return lines


def fraction_circle(num: int, den: int, radius: float = 1.0, shade: str = SHADE,
                    stroke: str = CHALK) -> VGroup:
    """Círculo dividido en `den` sectores iguales, `num` sombreados."""
    sectors = VGroup()
    for k in range(den):
        s = Sector(radius=radius, angle=TAU / den, start_angle=PI / 2 - k * TAU / den - TAU / den,
                   fill_color=shade, fill_opacity=0.9 if k < num else 0.0,
                   stroke_color=stroke, stroke_width=3)
        sectors.add(s)
    g = VGroup(sectors)
    g.cells = sectors
    g.shaded = VGroup(*sectors[:num])
    return g


def half_mobject(rep: HalfRepr, w: float, h: float) -> VGroup:
    """Dibuja una mitad de ficha dentro de una caja w x h."""
    if rep.kind == "frac":
        m = frac(rep.num, rep.den, size=56)
    elif rep.kind == "circle":
        m = fraction_circle(rep.num, rep.den, radius=1.0)
    else:
        m = fraction_rect(rep.num, rep.den, width=2.4, height=1.2)
    m.scale_to_fit_height(h * 0.72)
    if m.width > w * 0.82:
        m.scale_to_fit_width(w * 0.82)
    return m


def domino_tile(left: HalfRepr, right: HalfRepr, width: float = 3.6,
                stroke: str = CHALK) -> VGroup:
    """Ficha con dos mitades y línea central (como en el material impreso)."""
    height = width * 4 / 9  # proporción real 90 x 40 mm
    body = RoundedRectangle(corner_radius=height * 0.12, width=width, height=height,
                            stroke_color=stroke, stroke_width=3, fill_color="#26463A", fill_opacity=1)
    mid = Line(body.get_top(), body.get_bottom(), color=stroke, stroke_width=2)
    hw = width / 2
    lm = half_mobject(left, hw, height).move_to(body.get_center() + LEFT * hw / 2)
    rm = half_mobject(right, hw, height).move_to(body.get_center() + RIGHT * hw / 2)
    tile = VGroup(body, mid, lm, rm)
    tile.body, tile.left_half, tile.right_half = body, lm, rm
    tile.left_rep, tile.right_rep = left, right
    return tile


def half_box(tile: VGroup, side: str, color: str = GOLD) -> Rectangle:
    """Rectángulo que marca la mitad izquierda/derecha de una ficha."""
    b = tile.body
    w, h = b.width / 2, b.height
    center = b.get_center() + (LEFT if side == "left" else RIGHT) * w / 2
    return Rectangle(width=w - 0.06, height=h - 0.06, stroke_color=color, stroke_width=6).move_to(center)


def check_mark(ok: bool, size: float = 40) -> Text:
    return T("✓" if ok else "✗", size, OK if ok else BAD, "BOLD")


class Video2Scene(TimedScene):
    """Base común: fondo de pizarrón."""

    def setup(self):
        super().setup()
        self.camera.background_color = BG
        if hasattr(self.camera, "init_background"):
            self.camera.init_background()


# ---------------------------------------------------------------------------
# Escena 2 · Imagen 5
# ---------------------------------------------------------------------------
class V2E02_RepresentacionesEquivalentes(Video2Scene):
    """Dos unidades del MISMO tamaño: 2/4 y 4/8 sombreados ocupan la misma área."""

    DEFAULT_DURATION = 10.0
    DEFAULT_PARAMS = {"a": "2/4", "b": "4/8", "figura": "rect"}

    def _shape(self, fr):
        if self.params["figura"] == "circle":
            return fraction_circle(*fr, radius=1.4)
        return fraction_rect(*fr, width=4.8, height=1.9)

    def timeline(self):
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        eq = are_equivalent(a, b)

        head = titulo("¿Cómo pueden ser iguales?")
        ua, ub = self._shape(a), self._shape(b)
        ua.move_to(LEFT * 3.4 + UP * 0.5)
        ub.move_to(RIGHT * 3.4 + UP * 0.5)
        la = frac(*a, size=60).next_to(ua, DOWN, buff=0.4)
        lb = frac(*b, size=60).next_to(ub, DOWN, buff=0.4)

        ua.shaded.set_fill(opacity=0)
        ub.shaded.set_fill(opacity=0)
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.8)
        self.beat(Create(ua.cells), Create(ub.cells), t=1.2)
        self.beat(LaggedStart(*[c.animate.set_fill(SHADE, 0.9) for c in ua.shaded], lag_ratio=0.3),
                  LaggedStart(*[c.animate.set_fill(SHADE, 0.9) for c in ub.shaded], lag_ratio=0.3),
                  t=1.4)
        self.beat(Write(la), Write(lb), t=0.9)
        self.hold(1.0)

        # Superponer una copia de B sobre A: mismas áreas sombreadas.
        ghost = ub.copy().set_opacity(0.55)
        self.beat(ghost.animate.move_to(ua.get_center()), t=1.2)
        area = SurroundingRectangle(ua.shaded, color=GOLD, buff=0.06, stroke_width=6)
        self.beat(Create(area), t=0.7)

        half = simplify(a)
        rel = "=" if eq else r"\neq"
        result = tex(rf"\frac{{{a[0]}}}{{{a[1]}}} {rel} \frac{{{b[0]}}}{{{b[1]}}}"
                     + (rf" = \frac{{{half[0]}}}{{{half[1]}}}" if eq else ""),
                     font_size=64, color=GOLD)
        result.move_to(DOWN * 0.5 + ORIGIN)
        cap = rotulo("Distintas representaciones. La misma fracción." if eq
                     else "Se ven parecidas, pero no son la misma fracción.")
        self.beat(FadeOut(ghost), FadeOut(area), FadeOut(la), FadeOut(lb),
                  ua.animate.shift(UP * 0.4), ub.animate.shift(UP * 0.4), t=0.8)
        result.next_to(VGroup(ua, ub), DOWN, buff=0.7)
        self.beat(Write(result), t=1.0)
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.7)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 2 · Imagen 6
# ---------------------------------------------------------------------------
class V2E02_ProductosCruzados(Video2Scene):
    """2/4 = 4/8 porque 2 × 8 = 4 × 4 (enteros, sin decimales)."""

    DEFAULT_DURATION = 9.0
    DEFAULT_PARAMS = {"a": "2/4", "b": "4/8"}

    def timeline(self):
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        left, right = cross_products(a, b)
        eq = left == right

        head = titulo("Comprobar la equivalencia con enteros")
        fa, fb = frac(*a, size=110), frac(*b, size=110)
        VGroup(fa, fb).arrange(RIGHT, buff=2.6).move_to(UP * 1.1)
        sign = tex("=" if eq else r"\neq", font_size=110, color=OK if eq else BAD)
        sign.move_to(VGroup(fa, fb).get_center())
        sign_q = T("¿Son equivalentes?", 30, GOLD).next_to(VGroup(fa, fb), UP, buff=0.3)

        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)
        self.beat(Write(fa), Write(fb), FadeIn(sign_q), t=1.2)
        self.hold(0.5)

        # Flechas cruzadas: numerador de una por denominador de la otra.
        ar1 = Arrow(fa.num.get_center(), fb.den.get_center(), buff=0.35, color=GOLD, stroke_width=6)
        ar2 = Arrow(fb.num.get_center(), fa.den.get_center(), buff=0.35, color=SHADE, stroke_width=6)
        p1 = tex(rf"{a[0]} \times {b[1]} = {left}", font_size=64, color=GOLD)
        p2 = tex(rf"{b[0]} \times {a[1]} = {right}", font_size=64, color=SHADE)
        prods = VGroup(p1, p2).arrange(RIGHT, buff=1.6).move_to(DOWN * 1.25)

        self.beat(GrowArrow(ar1), t=0.7)
        self.beat(TransformFromCopy(VGroup(fa.num, fb.den), p1), t=1.0)
        self.beat(GrowArrow(ar2), t=0.7)
        self.beat(TransformFromCopy(VGroup(fb.num, fa.den), p2), t=1.0)

        rel = "=" if eq else r"\neq"
        verdict = tex(rf"{left} {rel} {right}", font_size=72,
                      color=OK if eq else BAD)
        mark = check_mark(eq, 60)
        vrow = VGroup(verdict, mark).arrange(RIGHT, buff=0.4).next_to(prods, DOWN, buff=0.45)
        self.beat(Write(verdict), FadeIn(mark, scale=1.5), t=0.9)
        self.beat(FadeOut(sign_q), FadeOut(ar1), FadeOut(ar2), FadeIn(sign, scale=1.3), t=0.7)
        cap = rotulo("Las matemáticas también deben especificarse")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 3 · Imagen 7
# ---------------------------------------------------------------------------
class V2E03_UnionDomino(Video2Scene):
    """La equivalencia está en la UNIÓN entre fichas, no dentro de una ficha."""

    DEFAULT_DURATION = 10.0
    DEFAULT_PARAMS = {}

    def timeline(self):
        # Fichas válidas: (1/3 | 1/2) (1/2 | 3/4) (3/4 | 2/3)
        tiles = [
            domino_tile(HalfRepr("frac", 2, 6), HalfRepr("frac", 2, 4)),
            domino_tile(HalfRepr("rect", 4, 8), HalfRepr("circle", 3, 4)),
            domino_tile(HalfRepr("frac", 6, 8), HalfRepr("rect", 2, 3)),
        ]
        head = titulo("Cada ficha tiene dos mitades")
        spread = VGroup(*tiles).arrange(RIGHT, buff=0.9).move_to(UP * 0.4)
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)
        self.beat(LaggedStart(*[FadeIn(t, shift=UP * 0.3) for t in tiles], lag_ratio=0.3), t=1.4)
        self.hold(0.6)

        # Juntar las fichas.
        joined = VGroup(*[t.copy() for t in tiles]).arrange(RIGHT, buff=0.0).move_to(UP * 0.4)
        self.beat(*[t.animate.move_to(j.get_center()) for t, j in zip(tiles, joined)], t=1.1)

        # Iluminar SOLO las mitades que se tocan.
        joints = []
        for left_t, right_t in zip(tiles, tiles[1:]):
            joints.append(VGroup(half_box(left_t, "right"), half_box(right_t, "left")))
        others = VGroup(tiles[0].left_half, tiles[-1].right_half)
        self.beat(others.animate.set_opacity(0.35), t=0.6)
        for j, (lt, rt) in zip(joints, zip(tiles, tiles[1:])):
            a = (lt.right_rep.num, lt.right_rep.den)
            b = (rt.left_rep.num, rt.left_rep.den)
            eq_tex = tex(rf"\frac{{{a[0]}}}{{{a[1]}}} = \frac{{{b[0]}}}{{{b[1]}}}", font_size=46, color=GOLD)
            eq_tex.next_to(j, DOWN, buff=0.35)
            arrow = Arrow(eq_tex.get_top(), j.get_bottom(), buff=0.08, color=GOLD, stroke_width=5)
            self.beat(Create(j), GrowArrow(arrow), Write(eq_tex), t=1.0)
            self.hold(0.4)

        note = T("Las dos mitades de una misma ficha no tienen que ser equivalentes", 26, MUTED)
        note.next_to(spread, DOWN, buff=2.0)
        cap = rotulo("Se unen los extremos equivalentes")
        note.next_to(cap, UP, buff=0.3)
        self.beat(FadeIn(note), FadeIn(cap, shift=UP * 0.2), t=0.8)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 3 · Imagen 9
# ---------------------------------------------------------------------------
class V2E03_ColorUniforme(Video2Scene):
    """Un color por familia regala la respuesta; color uniforme o trama, no."""

    DEFAULT_DURATION = 9.0
    DEFAULT_PARAMS = {}

    def timeline(self):
        fams = [(1, 2), (2, 4), (1, 3), (2, 6)]
        palette = {(1, 2): "#5DADE2", (1, 3): "#F5A25D"}
        head = titulo("¿El color da la respuesta?")

        def row(colors: bool, hatch: bool = False):
            g = VGroup()
            for fr in fams:
                color = palette[simplify(fr)] if colors else SHADE
                g.add(VGroup(fraction_rect(*fr, width=2.2, height=0.9, shade=color, hatch=hatch),
                             frac(*fr, size=34)).arrange(DOWN, buff=0.18))
            return g.arrange(RIGHT, buff=0.45)

        bad = row(True)
        good = row(False)
        bw = row(False, hatch=True)
        lbl_bad = T("Un color por valor", 28, MUTED)
        lbl_good = T("Color uniforme", 28, MUTED)
        lbl_bw = T("Trama para blanco y negro", 28, MUTED)
        top = VGroup(lbl_bad, bad).arrange(DOWN, buff=0.3).move_to(UP * 0.4)
        row_good = VGroup(lbl_good, good).arrange(DOWN, buff=0.25)
        row_bw = VGroup(lbl_bw, bw).arrange(DOWN, buff=0.25)
        bottom = VGroup(row_good, row_bw).arrange(DOWN, buff=0.45).move_to(UP * 0.15)

        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)
        self.beat(FadeIn(top), t=1.0)
        # El color empareja sin pensar: se resaltan parejas del mismo color.
        pair1 = SurroundingRectangle(VGroup(bad[0], bad[1]), color=GOLD, buff=0.1)
        pair2 = SurroundingRectangle(VGroup(bad[2], bad[3]), color=GOLD, buff=0.1)
        self.beat(Create(pair1), Create(pair2), t=0.8)
        cross = Cross(VGroup(top, pair1, pair2), stroke_color=BAD, stroke_width=10)
        self.beat(Create(cross), t=0.6)
        self.hold(0.5)
        self.beat(FadeOut(pair1), FadeOut(pair2), FadeOut(top), FadeOut(cross), t=0.6)
        self.beat(FadeIn(bottom, shift=UP * 0.3), t=1.0)
        cap = rotulo("Comparar valores, no colores")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 4 · Imagen 10
# ---------------------------------------------------------------------------
class V2E04_NivelesDificultad(Video2Scene):
    """Por qué 15, 28 y 45 fichas: parejas no ordenadas con dobles = n(n+1)/2."""

    DEFAULT_DURATION = 13.0
    DEFAULT_PARAMS = {"nivel_detalle": "inicial"}

    def timeline(self):
        nivel = self.params["nivel_detalle"]
        fams = NIVELES[nivel]
        n = len(fams)
        head = titulo("Tres niveles con características concretas")
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)

        # Tabla de parejas (triángulo superior con diagonal) para el nivel elegido.
        cell = min(0.72, 3.6 / n)
        labels_top = VGroup(*[frac(*f, size=24) for f in fams])
        labels_left = VGroup(*[frac(*f, size=24) for f in fams])
        grid = VGroup()
        origin = LEFT * 3.2 + UP * 1.3
        for i in range(n):
            for j in range(n):
                sq = Rectangle(width=cell, height=cell, stroke_color=MUTED, stroke_width=1.5)
                sq.move_to(origin + RIGHT * j * cell + DOWN * i * cell)
                grid.add(sq)
        for j, lab in enumerate(labels_top):
            lab.scale_to_fit_height(cell * 0.85).next_to(grid[j], UP, buff=0.12)
        for i, lab in enumerate(labels_left):
            lab.scale_to_fit_height(cell * 0.85).next_to(grid[i * n], LEFT, buff=0.15)
        table = VGroup(grid, labels_top, labels_left)
        table.move_to(LEFT * 3.6 + UP * 0.55)

        tiles_idx = generate_tiles(fams)
        fills = VGroup(*[
            Rectangle(width=cell * 0.8, height=cell * 0.8, stroke_width=0,
                      fill_color=GOLD if i == j else SHADE, fill_opacity=0.9)
            .move_to(grid[i * n + j].get_center())
            for i, j in tiles_idx
        ])
        counter_lbl = T(f"Nivel {nivel}: {n} familias", 28, CHALK)
        counter_lbl.next_to(table, DOWN, buff=0.3)
        self.beat(Create(grid), FadeIn(labels_top), FadeIn(labels_left), FadeIn(counter_lbl), t=1.2)
        self.beat(LaggedStart(*[GrowFromCenter(f) for f in fills], lag_ratio=0.15), t=2.2)
        legend = VGroup(
            VGroup(Rectangle(width=0.3, height=0.3, fill_color=GOLD, fill_opacity=0.9, stroke_width=0),
                   T("dobles", 24, MUTED)).arrange(RIGHT, buff=0.15),
            VGroup(Rectangle(width=0.3, height=0.3, fill_color=SHADE, fill_opacity=0.9, stroke_width=0),
                   T("parejas distintas", 24, MUTED)).arrange(RIGHT, buff=0.15),
        ).arrange(RIGHT, buff=0.5).next_to(counter_lbl, DOWN, buff=0.18)
        total = tex(rf"= {len(tiles_idx)} \text{{ fichas}}", font_size=44, color=GOLD)
        total.next_to(table, RIGHT, buff=0.3)
        self.beat(FadeIn(legend), Write(total), t=0.9)
        self.hold(0.6)

        # Fórmula general y los tres niveles.
        formula = tex(r"\text{fichas} = \frac{n\,(n+1)}{2}", font_size=58, color=CHALK)
        formula.move_to(RIGHT * 3.3 + UP * 1.75)
        rows = VGroup()
        for name, fam in NIVELES.items():
            k = len(fam)
            rows.add(VGroup(
                T(name.capitalize(), 32, CHALK, "BOLD"),
                tex(rf"n={k} \;\Rightarrow\; \frac{{{k}\cdot{k + 1}}}{{2}} = {expected_tile_count(k)}",
                    font_size=38, color=GOLD if name == nivel else CHALK),
            ).arrange(RIGHT, buff=0.4))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        rows.scale_to_fit_width(min(rows.width, 6.2))
        rows.next_to(formula, DOWN, buff=0.45)
        rows.set_x(3.3)
        formula.set_x(3.3)
        self.beat(FadeOut(total), Write(formula), t=1.0)
        self.beat(LaggedStart(*[FadeIn(r, shift=LEFT * 0.3) for r in rows], lag_ratio=0.4), t=1.6)
        cap = rotulo("La dificultad debe tener características concretas")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(1.8)


# ---------------------------------------------------------------------------
# Escena 4 · Imagen 11
# ---------------------------------------------------------------------------
class V2E04_FigurasRepresentacion(Video2Scene):
    """Solo fracción, solo imagen o ambas; rectángulos y círculos bien divididos."""

    DEFAULT_DURATION = 9.0
    DEFAULT_PARAMS = {"fraccion": "3/4", "multiplicador": 2}

    def timeline(self):
        base = parse_fraction(self.params["fraccion"])
        m = int(self.params["multiplicador"])
        eqv = (base[0] * m, base[1] * m)
        if eqv[1] > 16:
            raise ValueError("El guion limita las imágenes a 16 partes")

        head = titulo("Elegir la representación")
        c1 = VGroup(T("Solo fracción", 30, MUTED), frac(*base, size=90))
        c2 = VGroup(T("Solo imagen", 30, MUTED), fraction_rect(*eqv, width=3.2, height=1.4))
        c3 = VGroup(T("Fracción + imagen", 30, MUTED),
                    VGroup(frac(*eqv, size=60), fraction_circle(*base, radius=0.85)).arrange(RIGHT, buff=0.4))
        cols = VGroup()
        for c in (c1, c2, c3):
            c[1].move_to(ORIGIN)
            cols.add(VGroup(c[0], c[1]).arrange(DOWN, buff=0.45))
        cols.arrange(RIGHT, buff=1.0, aligned_edge=UP).move_to(UP * 0.6)

        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)
        self.beat(LaggedStart(*[FadeIn(c, shift=UP * 0.3) for c in cols], lag_ratio=0.35), t=1.6)
        self.hold(0.8)
        # Mismo valor en todas: se comprueba con productos cruzados.
        low = min(c.get_bottom()[1] for c in cols) - 0.4
        checks = VGroup(*[check_mark(True, 44).move_to([c.get_x(), low, 0]) for c in cols])
        same = tex(rf"\frac{{{base[0]}}}{{{base[1]}}} = \frac{{{eqv[0]}}}{{{eqv[1]}}}"
                   rf"\quad ({base[0]}\times{eqv[1]} = {eqv[0]}\times{base[1]} = {base[0] * eqv[1]})",
                   font_size=42, color=GOLD)
        same.next_to(checks, DOWN, buff=0.35)
        self.beat(LaggedStart(*[FadeIn(k, scale=1.4) for k in checks], lag_ratio=0.3), t=0.9)
        self.beat(Write(same), t=1.0)
        cap = rotulo("Fracciones, imágenes o ambas")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 6 · Imágenes 16-17
# ---------------------------------------------------------------------------
class V2E06_MedidasFicha(Video2Scene):
    """Ficha de 90 × 40 mm, contorno de corte, línea central y hoja 2 × 5."""

    DEFAULT_DURATION = 11.0
    DEFAULT_PARAMS = {"papel": "A4"}

    PAPER_MM = {"A4": (210, 297), "Carta": (216, 279)}

    def timeline(self):
        head = titulo("Medidas que se conservan al imprimir")
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)

        # 1 unidad = 1 cm → ficha de 9 × 4 unidades.
        outline = DashedVMobject(Rectangle(width=9, height=4, stroke_color=CHALK, stroke_width=4),
                                 num_dashes=70)
        mid = Line(UP * 2, DOWN * 2, color=GOLD, stroke_width=6)
        tile = VGroup(outline, mid).move_to(UP * 0.1)
        dim_w = DoubleArrow(tile.get_corner(DL) + DOWN * 0.45, tile.get_corner(DR) + DOWN * 0.45,
                            buff=0, color=MUTED, stroke_width=3, tip_length=0.2)
        dim_h = DoubleArrow(tile.get_corner(UL) + LEFT * 0.45, tile.get_corner(DL) + LEFT * 0.45,
                            buff=0, color=MUTED, stroke_width=3, tip_length=0.2)
        lw = T("90 mm", 28, MUTED).next_to(dim_w, DOWN, buff=0.12)
        lh = T("40 mm", 28, MUTED).rotate(PI / 2).next_to(dim_h, LEFT, buff=0.12)
        scissors = T("✂  recortar el contorno", 26, CHALK).next_to(tile, UP, buff=0.2).align_to(tile, LEFT)
        nocut = T("línea central: NO cortar", 26, GOLD).next_to(tile, UP, buff=0.2).align_to(tile, RIGHT)

        self.beat(Create(outline), t=1.2)
        self.beat(GrowArrow(dim_w), GrowArrow(dim_h), FadeIn(lw), FadeIn(lh), t=0.8)
        self.beat(FadeIn(scissors), t=0.5)
        self.beat(Create(mid), FadeIn(nocut), t=0.7)
        cap1 = rotulo("Recorta el contorno; conserva las dos mitades")
        self.beat(FadeIn(cap1, shift=UP * 0.2), t=0.6)
        self.hold(1.4)

        # Hoja: 2 columnas × 5 filas + regla de 5 cm, a escala.
        pw, ph = self.PAPER_MM.get(self.params["papel"], self.PAPER_MM["A4"])
        s = 5.0 / ph  # unidades por mm
        page = Rectangle(width=pw * s, height=ph * s, stroke_color=CHALK, stroke_width=3,
                         fill_color="#F7F4EC", fill_opacity=0.08)
        cards = VGroup()
        for r in range(5):
            for c in range(2):
                card = DashedVMobject(Rectangle(width=90 * s, height=40 * s, stroke_color=CHALK,
                                                stroke_width=2), num_dashes=30)
                cm = Line(UP * 20 * s, DOWN * 20 * s, color=GOLD, stroke_width=2)
                cards.add(VGroup(card, cm))
        cards.arrange_in_grid(rows=5, cols=2, buff=(4 * s, 2 * s))
        cards.move_to(page.get_center() + UP * 12 * s)
        ruler = VGroup(Line(ORIGIN, RIGHT * 50 * s, color=GOLD, stroke_width=4))
        for k in range(6):
            ruler.add(Line(UP * 0.08, DOWN * 0.08, color=GOLD, stroke_width=3).move_to(RIGHT * k * 10 * s))
        ruler.next_to(cards, DOWN, buff=10 * s).align_to(cards, LEFT)
        ruler_lbl = T("5 cm", 18, GOLD).next_to(ruler, RIGHT, buff=0.12)
        sheet = VGroup(page, cards, ruler, ruler_lbl).move_to(LEFT * 3.0 + UP * 0.3)

        info = VGroup(
            T(f"Papel {self.params['papel']}", 32, CHALK, "BOLD"),
            T("10 fichas por hoja (2 × 5)", 30, CHALK),
            T("Regla de comprobación: 5 cm", 30, CHALK),
            T("Imprimir a escala 100 %", 30, GOLD, "BOLD"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.35).move_to(RIGHT * 3.4 + UP * 0.3)

        big = VGroup(tile, dim_w, dim_h, lw, lh, scissors, nocut)
        self.beat(FadeOut(cap1), ReplacementTransform(big, cards[0]), FadeIn(page), t=1.2)
        self.beat(LaggedStart(*[FadeIn(c) for c in cards[1:]], lag_ratio=0.12), t=1.2)
        self.beat(Create(ruler), FadeIn(ruler_lbl), t=0.6)
        self.beat(LaggedStart(*[FadeIn(i, shift=LEFT * 0.3) for i in info], lag_ratio=0.3), t=1.2)
        cap2 = rotulo("La impresión debe conservar las medidas")
        self.beat(FadeIn(cap2, shift=UP * 0.2), t=0.6)
        self.hold(1.6)


# ---------------------------------------------------------------------------
# Escena 7 · Imagen 21
# ---------------------------------------------------------------------------
class V2E07_CadenaCompleta(Video2Scene):
    """Solución de referencia: una cadena que usa TODAS las fichas una sola vez."""

    DEFAULT_DURATION = 15.0
    DEFAULT_PARAMS = {"nivel": "inicial", "semilla": "AULA-2026", "modo": "mixto", "figuras": "rect"}

    def timeline(self):
        nivel = self.params["nivel"]
        fams = NIVELES[nivel]
        tiles_idx = generate_tiles(fams)
        chain = eulerian_chain(len(fams), tiles_idx)
        rng = random.Random(f"{self.params['semilla']}|{nivel}")

        # Extremos en orden de lectura: (familia_izq, familia_der).
        ends = [tiles_idx[t] if o == 0 else tiles_idx[t][::-1] for t, o in chain]
        n = len(ends)
        cols = {15: 5, 28: 7, 45: 9}.get(n, 7)
        width = min(2.5, 12.8 / cols - 0.12)

        mobs = []
        for k, (fl, fr) in enumerate(ends):
            left = representation_for(fams[fl], nivel, rng, self.params["modo"], self.params["figuras"])
            right = representation_for(fams[fr], nivel, rng, self.params["modo"], self.params["figuras"])
            row = k // cols
            # Serpiente: filas impares se leen de derecha a izquierda → ficha girada.
            tile = domino_tile(left, right, width=width) if row % 2 == 0 else domino_tile(right, left, width=width)
            mobs.append(tile)

        h = width * 4 / 9
        rows = (n + cols - 1) // cols
        gap_x, gap_y = 0.06, 0.25
        total_w = cols * width + (cols - 1) * gap_x
        top_y = 1.9
        for k, tile in enumerate(mobs):
            row, col = divmod(k, cols)
            if row % 2 == 1:
                col = cols - 1 - col
            x = -total_w / 2 + width / 2 + col * (width + gap_x)
            y = top_y - row * (h + gap_y)
            tile.move_to([x, y, 0])
        board = VGroup(*mobs)
        if board.height > 4.6:
            board.scale_to_fit_height(4.6)
        board.move_to(UP * 0.55)

        head = titulo(f"Cadena completa · nivel {nivel} · {n} fichas")
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)
        self.beat(LaggedStart(*[FadeIn(t, shift=RIGHT * 0.15) for t in mobs], lag_ratio=0.35), t=4.0)

        # Resaltar las uniones (cada una debe ser equivalente).
        joints = VGroup()
        for k in range(n - 1):
            a, b = mobs[k].body, mobs[k + 1].body
            same_row = (k // cols) == ((k + 1) // cols)
            row = k // cols
            if same_row:
                p = (a.get_right() + b.get_left()) / 2 if row % 2 == 0 else (a.get_left() + b.get_right()) / 2
            else:
                edge = RIGHT if row % 2 == 0 else LEFT
                p = (a.get_edge_center(DOWN) + b.get_edge_center(UP)) / 2 + edge * a.width / 4
            joints.add(Circle(radius=0.11, color=GOLD, fill_color=GOLD, fill_opacity=1).move_to(p))
        self.beat(LaggedStart(*[GrowFromCenter(j) for j in joints], lag_ratio=0.25), t=1.8)
        self.hold(0.5)
        self.beat(FadeOut(joints), t=0.4)

        # Lista de comprobaciones REALES (no decorativas).
        ok_count = len(tiles_idx) == expected_tile_count(len(fams))
        ok_dupes = len(set(tiles_idx)) == len(tiles_idx)
        ok_chain = validate_chain(chain, tiles_idx, len(tiles_idx))
        ok_equiv = all(are_equivalent(fams[l1[1]], fams[l2[0]]) for l1, l2 in zip(ends, ends[1:]))
        items = [
            (f"{len(tiles_idx)} fichas", ok_count),
            ("Equivalencias en cada unión", ok_equiv),
            ("Sin parejas duplicadas", ok_dupes),
            ("Cada ficha una sola vez", ok_chain),
        ]
        checklist = VGroup(*[VGroup(check_mark(ok, 30), T(txt, 24, CHALK)).arrange(RIGHT, buff=0.15)
                             for txt, ok in items]).arrange(RIGHT, buff=0.55)
        checklist.next_to(board, DOWN, buff=0.35)
        if checklist.width > config.frame_width - 0.8:
            checklist.scale_to_fit_width(config.frame_width - 0.8)
        self.beat(LaggedStart(*[FadeIn(i, shift=UP * 0.2) for i in checklist], lag_ratio=0.35), t=1.6)
        cap = rotulo("Lo que se pide también debe poder revisarse")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(2.0)


# ---------------------------------------------------------------------------
# Escena 9 · Imagen 27
# ---------------------------------------------------------------------------
class V2E09_ComprobacionManual(Video2Scene):
    """2/4 = 4/8, pero 2/4 ≠ 2/8: mismas partes sombreadas ≠ misma fracción."""

    DEFAULT_DURATION = 11.0
    DEFAULT_PARAMS = {"a": "2/4", "b": "4/8", "c": "2/8"}

    def _compare(self, x, y, y_pos):
        ux = fraction_rect(*x, width=3.6, height=1.0)
        uy = fraction_rect(*y, width=3.6, height=1.0)
        fx, fy = frac(*x, size=48), frac(*y, size=48)
        eq = are_equivalent(x, y)
        l, r = cross_products(x, y)
        sign = tex("=" if eq else r"\neq", font_size=64, color=OK if eq else BAD)
        left = VGroup(fx, ux).arrange(RIGHT, buff=0.35)
        right = VGroup(fy, uy).arrange(RIGHT, buff=0.35)
        row = VGroup(left, sign, right).arrange(RIGHT, buff=0.55).move_to(UP * y_pos + LEFT * 1.3)
        proof = VGroup(
            tex(rf"{x[0]}\times{y[1]}={l}", font_size=38, color=CHALK),
            T("·", 30, MUTED),
            tex(rf"{y[0]}\times{x[1]}={r}", font_size=38, color=CHALK),
        ).arrange(RIGHT, buff=0.25)
        mark = check_mark(eq, 50)
        tail = VGroup(proof, mark).arrange(RIGHT, buff=0.3).next_to(row, RIGHT, buff=0.5)
        return row, ux, uy, tail

    def timeline(self):
        a, b, c = (parse_fraction(self.params[k]) for k in ("a", "b", "c"))
        head = titulo("Comprobación manual")
        self.beat(FadeIn(head, shift=DOWN * 0.2), t=0.7)

        row1, _, _, tail1 = self._compare(a, b, 1.35)
        row2, u2a, u2c, tail2 = self._compare(a, c, -0.75)
        for grp in (VGroup(row1, tail1), VGroup(row2, tail2)):
            if grp.width > config.frame_width - 1.0:
                grp.scale_to_fit_width(config.frame_width - 1.0)
            grp.set_x(0)

        self.beat(FadeIn(row1), t=1.0)
        self.beat(FadeIn(tail1, shift=LEFT * 0.2), t=0.8)
        self.hold(0.8)
        self.beat(FadeIn(row2), t=1.0)

        # Mismo número de partes sombreadas... pero de distinto tamaño.
        boxes = VGroup(SurroundingRectangle(u2a.shaded, color=GOLD, buff=0.05),
                       SurroundingRectangle(u2c.shaded, color=GOLD, buff=0.05))
        same = T(f"{a[0]} partes sombreadas en ambas", 26, GOLD).next_to(row2, DOWN, buff=0.35)
        self.beat(Create(boxes), FadeIn(same), t=0.9)
        self.beat(Indicate(u2a.shaded, color=GOLD), Indicate(u2c.shaded, color=GOLD), t=0.9)
        self.beat(FadeIn(tail2, shift=LEFT * 0.2), t=0.8)
        warn = T("…pero las partes no son del mismo tamaño", 26, BAD).next_to(same, DOWN, buff=0.15)
        self.beat(FadeIn(warn), t=0.6)
        cap = rotulo("No basta con que las fichas se vean bien")
        self.beat(FadeIn(cap, shift=UP * 0.2), t=0.6)
        self.hold(1.8)


# ---------------------------------------------------------------------------
# Escena 12 · Imagen 36
# ---------------------------------------------------------------------------
class V2E12_CierreRecorrido(Video2Scene):
    """Objetivo → Requisitos → Código → Pruebas → Aula."""

    DEFAULT_DURATION = 9.0
    DEFAULT_PARAMS = {"pasos": ["Objetivo", "Requisitos", "Código", "Pruebas", "Aula"],
                      "cierre": "Diseña. Pide. Comprueba. Enseña."}

    def timeline(self):
        pasos = list(self.params["pasos"])
        boxes = VGroup()
        for p in pasos:
            lbl = T(p, 32, CHALK, "BOLD")
            box = RoundedRectangle(corner_radius=0.15, width=lbl.width + 0.6, height=1.0,
                                   stroke_color=SHADE, stroke_width=4, fill_color="#26463A", fill_opacity=1)
            boxes.add(VGroup(box, lbl.move_to(box)))
        boxes.arrange(RIGHT, buff=0.75)
        if boxes.width > config.frame_width - 0.8:
            boxes.scale_to_fit_width(config.frame_width - 0.8)
        boxes.move_to(UP * 0.9)
        arrows = VGroup(*[Arrow(a.get_right(), b.get_left(), buff=0.08, color=GOLD, stroke_width=5)
                          for a, b in zip(boxes, boxes[1:])])

        self.beat(FadeIn(boxes[0], shift=RIGHT * 0.2), t=0.7)
        for arr, box in zip(arrows, boxes[1:]):
            self.beat(GrowArrow(arr), FadeIn(box, shift=RIGHT * 0.2), t=0.7)
        self.hold(0.8)
        cierre = T(self.params["cierre"], 54, GOLD, "BOLD")
        if cierre.width > config.frame_width - 1.0:
            cierre.scale_to_fit_width(config.frame_width - 1.0)
        cierre.move_to(DOWN * 1.2)
        self.beat(Write(cierre), t=1.4)
        sub = T("Lo transferible: convertir decisiones docentes en instrucciones claras y resultados revisables",
                24, MUTED)
        if sub.width > config.frame_width - 0.8:
            sub.scale_to_fit_width(config.frame_width - 0.8)
        sub.next_to(cierre, DOWN, buff=0.45)
        self.beat(FadeIn(sub), t=0.7)
        self.hold(2.0)


# ---------------------------------------------------------------------------
# Registro (manim_scene: "<nombre>" en el YAML)
# ---------------------------------------------------------------------------
SCENE_REGISTRY: Dict[str, type] = {
    cls.__name__: cls
    for cls in (
        V2E02_RepresentacionesEquivalentes,
        V2E02_ProductosCruzados,
        V2E03_UnionDomino,
        V2E03_ColorUniforme,
        V2E04_NivelesDificultad,
        V2E04_FigurasRepresentacion,
        V2E06_MedidasFicha,
        V2E07_CadenaCompleta,
        V2E09_ComprobacionManual,
        V2E12_CierreRecorrido,
    )
}
