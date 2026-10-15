"""
Catálogo de componentes Manim reutilizables (HG).

Piezas de dibujo SIN tiempo ni escena: cada función devuelve un Mobject listo
para animar dentro de una TimedScene / OverlayScene. Las escenas de
scenes_video2.py y los overlays de math_scenes.py se arman con estas piezas,
así todos los episodios comparten el mismo estilo de pizarrón y las mismas
matemáticas correctas (la lógica pura vive en fracciones.py y ecuaciones.py).

  Grupo         Componentes
  ------------  ---------------------------------------------------------------
  Estilo        Paleta (BG, CHALK, MUTED, SHADE, GOLD, OK, BAD, BLUE, ORANGE),
                resolve_font(), T(), titulo(), rotulo(), check_mark()
  Paneles       PANEL_LAYOUTS, panel(), panel_box(), tag(), fit_in()
  Fracciones    frac(), fraction_rect(), fraction_circle(), fraction_equation(),
                fraction_bars_row(), cross_products_row()
  Ecuaciones    steps_flow(), solution_box(), substitution_block()
  Gráficas      number_line_points(), function_plot()
  SVG / PNG     asset_mobject()

Convenciones:
  - Colores en hex; tamaños de fuente en puntos de Manim (64 = MathTex normal).
  - Nada aquí llama play()/wait(): las escenas deciden el tiempo con beat()/hold().
  - Los componentes compuestos exponen sus partes como atributos (p. ej.
    frac().num / .den, fraction_rect().cells / .shaded, function_plot().axes)
    para que la escena pueda animarlas por separado.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP, PI, TAU,
    Arrow, Axes, DashedLine, Dot, ImageMobject, Line, NumberLine, Rectangle, RoundedRectangle,
    SVGMobject, Sector, Text, VGroup,
)

from ..ecuaciones import (
    LinearEquation, Step, check_steps, frac_latex, poly_eval, poly_latex, real_roots,
)
from ..fracciones import cross_products, simplify
from .. import manim_timing as _mt
from ..manim_timing import strict_latex, tex

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estilo (pizarrón verde + gis, como las ilustraciones de los guiones)
# ---------------------------------------------------------------------------
BG = "#1E3A2F"          # pizarrón
CHALK = "#F5F1E6"       # gis
MUTED = "#A9B8AE"       # texto secundario
SHADE = "#B08AE0"       # sombreado ÚNICO para fracciones (regla del GUION-02)
GOLD = "#F4C95D"        # resaltado / resultado
OK = "#9BE58A"
BAD = "#FF8A80"
BLUE = "#7FB7FF"        # «¡Se busca a la x!»: el 4 y su factor
ORANGE = "#FFB06B"      # «¡Se busca a la x!»: el 5 y su factor
PANEL_FILL_OPACITY = 0.9

#: Fuentes en orden de preferencia; se usa la primera instalada (DejaVu en
#: Linux/Docker, Segoe UI o Arial en Windows). $VA_FONT tiene prioridad.
FONT_CANDIDATES: Tuple[str, ...] = ("DejaVu Sans", "Segoe UI", "Arial", "Helvetica",
                                    "Liberation Sans", "Noto Sans", "Sans")


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


def T(text: str, size: float = 36, color: str = CHALK, weight: str = "NORMAL") -> Text:
    """Texto con la fuente del canal."""
    return Text(text, font=resolve_font(), font_size=size, color=color, weight=weight)


def titulo(text: str) -> Text:
    return T(text, 40, CHALK, "BOLD").to_edge(UP, buff=0.45)


def rotulo(text: str) -> VGroup:
    """Mensaje principal de la imagen del guion, en la franja inferior."""
    label = T(text, 34, GOLD, "BOLD")
    bar = Line(LEFT, RIGHT, color=SHADE, stroke_width=4).scale_to_fit_width(label.width + 0.6)
    bar.next_to(label, DOWN, buff=0.15)
    return VGroup(label, bar).to_edge(DOWN, buff=0.45)


def check_mark(ok: bool, size: float = 40) -> Text:
    return T("✓" if ok else "✗", size, OK if ok else BAD, "BOLD")


# ---------------------------------------------------------------------------
# Paneles para overlays
# ---------------------------------------------------------------------------
# Cuadro de Manim a 16:9: 14.22 x 8 unidades.
FRAME_W, FRAME_H = 14.222, 8.0
_M = 0.2   # margen al borde del cuadro

#: Panel por posición: (ancho, alto, centro_x, centro_y).
#: abajo/arriba/centro: franja horizontal (fórmulas, despejes).
#: izquierda/derecha: columna alta (gráficas, procedimientos largos).
PANEL_LAYOUTS: Dict[str, Tuple[float, float, float, float]] = {
    "abajo": (13.0, 2.45, 0.0, -FRAME_H / 2 + _M + 2.45 / 2),
    "arriba": (13.0, 2.45, 0.0, FRAME_H / 2 - _M - 2.45 / 2),
    "centro": (13.0, 2.45, 0.0, 0.0),
    "derecha": (6.2, 7.2, FRAME_W / 2 - _M - 6.2 / 2, 0.0),
    "izquierda": (6.2, 7.2, -FRAME_W / 2 + _M + 6.2 / 2, 0.0),
}


def panel(width: float, height: float) -> RoundedRectangle:
    """Panel de pizarrón con relleno propio (se lee sobre cualquier ilustración)."""
    return RoundedRectangle(corner_radius=0.18, width=width, height=height,
                            fill_color=BG, fill_opacity=PANEL_FILL_OPACITY,
                            stroke_color=CHALK, stroke_width=3)


def panel_box(posicion: str) -> RoundedRectangle:
    """Panel ya colocado según PANEL_LAYOUTS ("abajo", "derecha"...)."""
    if posicion not in PANEL_LAYOUTS:
        raise ValueError(f"posicion={posicion!r}; usa una de {sorted(PANEL_LAYOUTS)}")
    w, h, cx, cy = PANEL_LAYOUTS[posicion]
    return panel(w, h).move_to(RIGHT * cx + UP * cy)


def tag(text: str, anchor: RoundedRectangle) -> VGroup:
    """Pestaña dorada pegada a la esquina superior izquierda del panel."""
    label = T(text, 22, BG, "BOLD")
    box = RoundedRectangle(corner_radius=0.1, width=label.width + 0.4, height=label.height + 0.22,
                           fill_color=GOLD, fill_opacity=1, stroke_width=0)
    label.move_to(box)
    g = VGroup(box, label)
    if g.width > anchor.width - 0.7:
        g.scale_to_fit_width(anchor.width - 0.7)
    g.move_to(anchor.get_corner(UP + LEFT) + RIGHT * (g.width / 2 + 0.35))
    return g


def fit_in(mob, box: RoundedRectangle, pad_x: float = 0.7, pad_y: float = 0.45,
           shift=ORIGIN):
    """Escala `mob` (solo hacia abajo) para que quepa en `box` y lo centra."""
    if mob.width > box.width - pad_x:
        mob.scale_to_fit_width(box.width - pad_x)
    if mob.height > box.height - pad_y:
        mob.scale_to_fit_height(box.height - pad_y)
    return mob.move_to(box.get_center() + shift)


# ---------------------------------------------------------------------------
# Fracciones
# ---------------------------------------------------------------------------

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
        g.add(hatch_cells(cells[:num], stroke))
    g.cells = cells
    g.shaded = VGroup(*cells[:num])
    return g


def hatch_cells(cells: Sequence[Rectangle], color: str, spacing: float = 0.16) -> VGroup:
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


def fraction_equation(a: Tuple[int, int], b: Tuple[int, int], equivalent: bool,
                      font_size: float = 60, color: str = GOLD):
    """a/b = c/d = simplificada (o a/b ≠ c/d) como un solo MathTex."""
    rel = "=" if equivalent else r"\neq"
    half = simplify(a)
    latex = rf"\frac{{{a[0]}}}{{{a[1]}}} {rel} \frac{{{b[0]}}}{{{b[1]}}}"
    if equivalent and half != tuple(a):
        latex += rf" = \frac{{{half[0]}}}{{{half[1]}}}"
    return tex(latex, font_size=font_size, color=color)


def fraction_bars_row(a: Tuple[int, int], b: Tuple[int, int], equivalent: bool,
                      caption: Optional[str] = None, bar_width: float = 3.6,
                      bar_height: float = 0.62) -> VGroup:
    """
    Dos unidades del MISMO tamaño, una sobre otra, con línea guía y la
    igualdad a la derecha. Expone: .ra .rb .la .lb .guide .equation .caption
    (los sombreados empiezan VISIBLES; la escena puede apagarlos y animarlos).
    """
    ra = fraction_rect(*a, width=bar_width, height=bar_height)
    rb = fraction_rect(*b, width=bar_width, height=bar_height)
    bars = VGroup(ra, rb).arrange(DOWN, buff=0.28)
    la = frac(*a, size=34).next_to(ra, LEFT, buff=0.3)
    lb = frac(*b, size=34).next_to(rb, LEFT, buff=0.3)
    edge_x = ra.shaded.get_right()[0] if len(ra.shaded) else ra.get_left()[0]
    guide = DashedLine([edge_x, bars.get_top()[1] + 0.15, 0], [edge_x, bars.get_bottom()[1] - 0.15, 0],
                       color=GOLD, stroke_width=5, dash_length=0.1)
    left = VGroup(la, lb, bars, guide)

    equation = fraction_equation(a, b, equivalent)
    if caption is None:
        caption = ("Distintas representaciones. La misma fracción." if equivalent
                   else "Se parecen, pero no son la misma fracción.")
    cap = T(caption, 26, CHALK, "BOLD")
    right = VGroup(equation, cap).arrange(DOWN, buff=0.25)
    row = VGroup(left, right).arrange(RIGHT, buff=0.8)
    row.ra, row.rb, row.la, row.lb, row.guide = ra, rb, la, lb, guide
    row.equation, row.caption = equation, cap
    return row


def cross_products_row(a: Tuple[int, int], b: Tuple[int, int], note: str = "Enteros, sin decimales",
                       size: float = 60) -> VGroup:
    """
    a/b ? c/d con flechas cruzadas, los dos productos y el veredicto.
    Expone: .fa .fb .sign .ar1 .ar2 .p1 .p2 .verdict .mark .vrow .note .equivalent
    (.sign empieza transparente: aparece cuando se confirma la relación).
    """
    left_p, right_p = cross_products(a, b)
    eq = left_p == right_p
    fa, fb = frac(*a, size=size), frac(*b, size=size)
    sign = tex("=" if eq else r"\neq", font_size=size, color=OK if eq else BAD)
    fracs = VGroup(fa, sign, fb).arrange(RIGHT, buff=1.0)
    ar1 = Arrow(fa.num.get_center(), fb.den.get_center(), buff=0.22, color=GOLD,
                stroke_width=5, max_tip_length_to_length_ratio=0.15)
    ar2 = Arrow(fb.num.get_center(), fa.den.get_center(), buff=0.22, color=SHADE,
                stroke_width=5, max_tip_length_to_length_ratio=0.15)
    sign.set_opacity(0)

    p1 = tex(rf"{a[0]} \times {b[1]} = {left_p}", font_size=size * 0.77, color=GOLD)
    p2 = tex(rf"{b[0]} \times {a[1]} = {right_p}", font_size=size * 0.77, color=SHADE)
    prods = VGroup(p1, p2).arrange(DOWN, buff=0.3, aligned_edge=LEFT)

    rel = "=" if eq else r"\neq"
    verdict = tex(rf"{left_p} {rel} {right_p}", font_size=size * 0.93, color=OK if eq else BAD)
    mark = check_mark(eq, size * 0.73)
    vrow = VGroup(verdict, mark).arrange(RIGHT, buff=0.25)
    nt = T(note, 24, MUTED)
    right = VGroup(vrow, nt).arrange(DOWN, buff=0.2)

    row = VGroup(VGroup(fracs, ar1, ar2), prods, right).arrange(RIGHT, buff=0.9)
    row.fa, row.fb, row.sign, row.ar1, row.ar2 = fa, fb, sign, ar1, ar2
    row.fracs, row.prods, row.right = fracs, prods, right
    row.p1, row.p2, row.verdict, row.mark, row.vrow, row.note = p1, p2, verdict, mark, vrow, nt
    row.equivalent = eq
    return row


# ---------------------------------------------------------------------------
# Ecuaciones de primer grado
# ---------------------------------------------------------------------------

def _step_tex(step: Step, font_size: float, color: str):
    """MathTex con la operación aislada en su propio submobject para poder pintarla."""
    if step.op and step.kind == "operate" and step.op in step.latex:
        pieces: List[str] = []
        rest = step.latex
        while step.op in rest:
            before, rest = rest.split(step.op, 1)
            pieces += [before, step.op]
        pieces.append(rest)
        pieces = [p for p in pieces if p.strip()]
        try:
            from manim import MathTex

            mob = MathTex(*pieces, font_size=font_size, color=color)
            for i, p in enumerate(pieces):
                if p == step.op:
                    mob[i].set_color(BAD)
            return mob
        except Exception:  # noqa: BLE001 - sin LaTeX: una sola pieza con fallback
            pass
    return tex(step.latex, font_size=font_size, color=color)


def steps_flow(steps: Sequence[Step], direction=RIGHT, font_size: float = 52,
               color: str = CHALK, arrow_color: str = GOLD, buff: float = 0.45) -> VGroup:
    """
    Pasos de despeje encadenados con flechas (horizontal para los paneles
    abajo/arriba, vertical con direction=DOWN para izquierda/derecha).
    Expone .lines (un MathTex por paso, la operación pintada) y .arrows.
    El último paso (kind="solution") va en GOLD.
    """
    lines = VGroup()
    for s in steps:
        lines.add(_step_tex(s, font_size, GOLD if s.kind == "solution" else color))
    arrows = VGroup()
    flow = VGroup()
    for i, ln in enumerate(lines):
        if i:
            arr = Arrow(ORIGIN, direction * 0.7, buff=0, color=arrow_color, stroke_width=5,
                        max_tip_length_to_length_ratio=0.35)
            arrows.add(arr)
            flow.add(arr)
        flow.add(ln)
    flow.arrange(direction, buff=buff * 0.6)
    flow.lines, flow.arrows = lines, arrows
    return flow


def solution_box(var: str, value_latex: str, label: str = "Una solución:",
                 color: str = GOLD, frame_color: str = BAD) -> VGroup:
    """Recuadro «Una solución: x = -4» (como en el pizarrón). Expone .frame .label .value."""
    lab = T(label, 28, CHALK, "BOLD")
    val = tex(f"{var} = {value_latex}", font_size=56, color=color)
    body = VGroup(lab, val).arrange(DOWN, buff=0.12)
    frame = RoundedRectangle(corner_radius=0.12, width=body.width + 0.5, height=body.height + 0.35,
                             stroke_color=frame_color, stroke_width=5)
    body.move_to(frame)
    g = VGroup(frame, body)
    g.frame, g.label, g.value = frame, lab, val
    return g


def substitution_block(eq: LinearEquation, value=None, font_size: float = 46) -> VGroup:
    """Comprobación por sustitución: dos líneas y ✓/✗. Expone .lines .mark .ok."""
    lines, ok = check_steps(eq, value)
    mobs = VGroup(*[tex(l, font_size=font_size, color=CHALK if i == 0 else (OK if ok else BAD))
                    for i, l in enumerate(lines)]).arrange(DOWN, buff=0.18)
    mark = check_mark(ok, font_size * 0.9).next_to(mobs[-1], RIGHT, buff=0.25)
    g = VGroup(mobs, mark)
    g.lines, g.mark, g.ok = mobs, mark, ok
    return g


# ---------------------------------------------------------------------------
# Gráficas
# ---------------------------------------------------------------------------

def _with_latex_fallback(build):
    """
    Los números de los ejes de Manim (NumberLine/Axes) se escriben con MathTex
    SIN pasar por tex(): sin LaTeX funcional el render tronaba aquí aunque
    todo lo demás ya hubiera caído a texto plano. build(extra) recibe
    {"label_constructor": Text} cuando hay que usar texto plano.
    """
    if not _mt.latex_available() and not strict_latex():
        return build({"label_constructor": Text})
    try:
        return build({})
    except Exception:  # noqa: BLE001 - LaTeX/dvisvgm rotos: mismo respaldo que tex()
        if strict_latex():
            raise
        _mt._latex_broken = True
        log.warning("LaTeX no funciona: los números de los ejes se escriben como texto plano.")
        return build({"label_constructor": Text})


def number_line_points(x_range: Sequence[float], points: Iterable = (), length: float = 10.0,
                       colors: Sequence[str] = (BLUE, ORANGE, GOLD, OK),
                       label_size: float = 34) -> VGroup:
    """
    Recta numérica con puntos marcados (soluciones, valores a comparar).
    points: números (int/Fraction/float). Expone .line .dots .labels.
    """
    line = _with_latex_fallback(lambda extra: NumberLine(
        x_range=list(x_range), length=length, color=CHALK, include_numbers=True,
        font_size=28, stroke_width=3, **extra))
    dots, labels = VGroup(), VGroup()
    for i, p in enumerate(points):
        c = colors[i % len(colors)]
        d = Dot(line.n2p(float(p)), radius=0.11, color=c)
        lab = tex(frac_latex(p) if not isinstance(p, float) else f"{p:g}", font_size=label_size,
                  color=c).next_to(d, UP, buff=0.18)
        dots.add(d)
        labels.add(lab)
    g = VGroup(line, dots, labels)
    g.line, g.dots, g.labels = line, dots, labels
    return g


def function_plot(coeffs: Sequence, x_range: Sequence[float], y_range: Sequence[float],
                  width: float = 5.4, height: float = 5.4, color: str = GOLD,
                  mark_roots: bool = True, points: Iterable = (), label: Optional[str] = None,
                  root_colors: Sequence[str] = (BLUE, ORANGE)) -> VGroup:
    """
    Plano cartesiano con la gráfica de un polinomio (coeficientes, mayor grado
    primero: [1, 9, 20] = x² + 9x + 20) y, opcionalmente, sus raíces reales
    y puntos extra [(x, y), ...]. La curva se recorta a y_range.

    Expone: .axes .graph .roots (Dots) .root_labels .marks (puntos extra) .label
    """
    xr = [float(v) for v in x_range]
    yr = [float(v) for v in y_range]
    if len(xr) == 2:
        xr.append(1.0)
    if len(yr) == 2:
        yr.append(max(1.0, round((yr[1] - yr[0]) / 6)))
    def decimals(step: float) -> int:
        return 0 if float(step).is_integer() else 1

    axis_config = {"color": MUTED, "stroke_width": 2.5, "include_numbers": True,
                   "font_size": 22, "include_ticks": True}
    axes = _with_latex_fallback(lambda extra: Axes(
        x_range=xr, y_range=yr, x_length=width, y_length=height, tips=False,
        axis_config={**axis_config, **extra},
        x_axis_config={"decimal_number_config": {"num_decimal_places": decimals(xr[2])}},
        y_axis_config={"decimal_number_config": {"num_decimal_places": decimals(yr[2])}},
    ))
    f = lambda x: float(poly_eval(coeffs, x))  # noqa: E731

    # Recorta el dominio a donde la curva cabe en y_range (una sola rama continua).
    xs = np.linspace(xr[0], xr[1], 400)
    inside = [x for x in xs if yr[0] - 1e-9 <= f(x) <= yr[1] + 1e-9]
    lo, hi = (min(inside), max(inside)) if inside else (xr[0], xr[1])
    graph = axes.plot(lambda x: min(max(f(x), yr[0]), yr[1]), x_range=[lo, hi], color=color,
                      stroke_width=5, use_smoothing=True)

    roots, root_labels = VGroup(), VGroup()
    if mark_roots:
        for i, r in enumerate(real_roots(coeffs)):
            rv = float(r)
            if not (xr[0] <= rv <= xr[1]):
                continue
            c = root_colors[i % len(root_colors)]
            d = Dot(axes.c2p(rv, 0), radius=0.1, color=c)
            lab = tex(f"x = {frac_latex(r) if not isinstance(r, float) else f'{r:.2f}'}",
                      font_size=30, color=c)
            # Encima de la curva (los números del eje x quedan debajo): la primera
            # raíz a la izquierda y la segunda a la derecha para que no se encimen.
            lab.next_to(d, UP + (LEFT if i == 0 else RIGHT) * 0.9, buff=0.15)
            lab.add_background_rectangle(color=BG, opacity=0.85, buff=0.06)
            roots.add(d)
            root_labels.add(lab)
    extra = VGroup()
    for px, py in points:
        extra.add(Dot(axes.c2p(float(px), float(py)), radius=0.09, color=OK))

    lab = None
    if label is not False:
        lab = tex(label or f"y = {poly_latex(coeffs)}", font_size=34, color=color)
        lab.next_to(axes, UP, buff=0.2)

    g = VGroup(axes, graph, roots, root_labels, extra, *([lab] if lab is not None else []))
    g.axes, g.graph, g.roots, g.root_labels, g.marks, g.label = axes, graph, roots, root_labels, extra, lab
    return g


# ---------------------------------------------------------------------------
# Recursos SVG / PNG
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_asset(path: Union[str, Path]) -> Path:
    """Ruta absoluta del recurso; las relativas se buscan desde la raíz del repo."""
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = PROJECT_ROOT / p
    if not p.is_file():
        raise FileNotFoundError(f"No existe el recurso gráfico: {path}")
    return p


def asset_mobject(path: Union[str, Path], height: float = 1.2, color: Optional[str] = None):
    """
    Ícono o ilustración para un overlay: .svg → SVGMobject (vectorial, se
    puede recolorear y animar con Create/Write), .png/.jpg → ImageMobject
    (respeta la transparencia del PNG; se anima con FadeIn).
    """
    p = resolve_asset(path)
    ext = p.suffix.lower()
    if ext == ".svg":
        mob = SVGMobject(str(p))
        if color:
            mob.set_color(color)
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        mob = ImageMobject(str(p))
    else:
        raise ValueError(f"Formato de recurso no soportado {ext!r}; usa .svg, .png o .jpg")
    mob.height = height
    return mob


__all__ = [
    "BG", "CHALK", "MUTED", "SHADE", "GOLD", "OK", "BAD", "BLUE", "ORANGE", "PANEL_FILL_OPACITY",
    "FONT_CANDIDATES", "resolve_font", "T", "titulo", "rotulo", "check_mark",
    "FRAME_W", "FRAME_H", "PANEL_LAYOUTS", "panel", "panel_box", "tag", "fit_in",
    "frac", "fraction_rect", "hatch_cells", "fraction_circle", "fraction_equation",
    "fraction_bars_row", "cross_products_row",
    "steps_flow", "solution_box", "substitution_block",
    "number_line_points", "function_plot", "resolve_asset", "asset_mobject",
]
