"""
Escenas Manim de overlay (HG) — se incrustan SOBRE la base visual del guion.

Aquí viven EXCLUSIVAMENTE las clases de escena. Las piezas de dibujo están en
animations/components.py (catálogo reutilizable), la infraestructura de tramos
y transparencia en animations/base.py, la exportación en animations/export.py
y las matemáticas puras en fracciones.py / ecuaciones.py.

  Clase                  Uso                                   Qué superpone
  ---------------------  ------------------------------------  ---------------------------------------
  Scene02Math            GUION-02 · Escena 2 · Imágenes 4-5-6  Prompt / 2/4 = 4/8 / productos cruzados
  FormulaOverlay         Cualquier guion (solo YAML)           Una fórmula LaTeX (+ leyenda) por tramo
  FractionOverlay        Cualquier guion (solo YAML)           Barras de fracciones y/o productos cruzados
  LinearEquationOverlay  Cualquier guion (solo YAML)           Despeje paso a paso de ax + b = c (+ comprobación)
  GraphOverlay           Cualquier guion (solo YAML)           Plano cartesiano con la gráfica y sus raíces

Diseño de overlay:
  - Todo el contenido vive en un PANEL de pizarrón semitransparente. Las
    franjas abajo/arriba/centro sirven para fórmulas y despejes; las columnas
    izquierda/derecha para gráficas (ver components.PANEL_LAYOUTS).
  - Cada imagen de la base es un tramo: heavy_render manda `tramos` = la
    duración de cada imagen y el contenido cambia en el mismo cuadro del corte.
  - Los overlays genéricos aceptan `icono` (ruta .svg o .png) que se coloca en
    la esquina superior derecha del panel.

Todas se registran en SCENE_REGISTRY: `manim_overlay: <Clase>` en el YAML o
`--scene <Clase>` en scripts/render_manim_clips.py. También sirven como escena
completa (`render_type: manim`, fondo opaco de pizarrón).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from manim import (
    DOWN, LEFT, RIGHT, UP,
    Create, FadeIn, FadeOut, GrowArrow, Indicate, LaggedStart, RoundedRectangle,
    TransformFromCopy, VGroup, Write,
)

from ..ecuaciones import frac_latex, parse_linear, solve_steps
from ..fracciones import are_equivalent, parse_fraction
from ..manim_timing import tex
from .base import OverlayScene
from .components import (
    BAD, CHALK, GOLD, MUTED, OK, PANEL_LAYOUTS, SHADE, T, asset_mobject,
    cross_products_row, fit_in, fraction_bars_row, function_plot, panel, panel_box,
    solution_box, steps_flow, substitution_block, tag,
)

# Compatibilidad: estos nombres vivían aquí antes del catálogo.
__all__ = ["Scene02Math", "FormulaOverlay", "FractionOverlay", "LinearEquationOverlay",
           "GraphOverlay", "SCENE_REGISTRY", "panel", "tag", "PANEL_LAYOUTS"]


def distribute(n_items: int, n_segments: int) -> List[List[int]]:
    """
    Reparte n_items contenidos en n_segments tramos, en orden:
      - sobran tramos  → los últimos quedan vacíos (se mantiene lo último);
      - faltan tramos  → el último tramo muestra todos los restantes.
    distribute(2, 1) = [[0, 1]]; distribute(2, 3) = [[0], [1], []].
    """
    if n_segments < 1:
        raise ValueError("se necesita al menos un tramo")
    out: List[List[int]] = [[i] if i < n_items else [] for i in range(n_segments)]
    if n_items > n_segments:
        out[-1] = list(range(n_segments - 1, n_items))
    return out


class PanelOverlay(OverlayScene):
    """Base de los overlays de panel: crea el panel, la pestaña y el ícono opcional."""

    def make_panel(self, default_title: Optional[str] = None) -> Tuple[RoundedRectangle, List]:
        """Devuelve (panel, decoraciones) — decoraciones = pestaña e ícono, si hay."""
        self.box = panel_box(str(self.params.get("posicion", "abajo")))
        deco: List = []
        title = self.params.get("titulo", default_title)
        if title:
            self.head = tag(str(title), self.box)
            deco.append(self.head)
        else:
            self.head = None
        icon_path = self.params.get("icono")
        if icon_path:
            icon = asset_mobject(icon_path, height=float(self.params.get("icono_alto", 0.9)))
            icon.move_to(self.box.get_corner(UP + RIGHT) + LEFT * (icon.width / 2 + 0.25)
                         + DOWN * (icon.height / 2 + 0.2))
            deco.append(icon)
        return self.box, deco

    @property
    def is_column(self) -> bool:
        """True en los paneles altos (izquierda/derecha): el contenido va en vertical."""
        return self.params.get("posicion", "abajo") in ("izquierda", "derecha")

    def content_shift(self):
        return DOWN * 0.15 if self.head is not None else np.zeros(3)


# ---------------------------------------------------------------------------
# GUION-02 · Escena 2
# ---------------------------------------------------------------------------
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
        if pos not in ("abajo", "arriba", "centro"):
            raise ValueError(f"posicion={pos!r}; Scene02Math usa abajo, arriba o centro")
        self.box = panel_box(pos)

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

    # -- Imagen 4 · ¿Para quién se diseña el material? -----------------------
    def seg_img04_grupo(self) -> VGroup:
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
        fit_in(row, self.box, pad_y=0.0, shift=DOWN * 0.05)

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
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        head = tag("Imagen 5 · Distintas representaciones", self.box)
        row = fraction_bars_row(a, b, are_equivalent(a, b))
        fit_in(row, self.box, shift=DOWN * 0.05)
        _animate_bars(self, row, head)
        return VGroup(head, row)

    # -- Imagen 6 · Las matemáticas también deben especificarse ---------------
    def seg_img06_condiciones(self) -> VGroup:
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        head = tag("Imagen 6 · Las matemáticas también deben especificarse", self.box)
        row = cross_products_row(a, b)
        fit_in(row, self.box, shift=DOWN * 0.05)
        _animate_cross_products(self, row, head)
        return VGroup(head, row.fracs, row.prods, row.right)


def _animate_bars(scene: OverlayScene, row: VGroup, head=None) -> None:
    """Barras de fracción: celdas → sombreado → línea guía → igualdad → leyenda."""
    row.ra.shaded.set_fill(opacity=0)
    row.rb.shaded.set_fill(opacity=0)
    if head is not None:
        scene.beat(FadeIn(head, shift=RIGHT * 0.2), t=0.3)
    scene.beat(Create(row.ra.cells), Create(row.rb.cells), FadeIn(row.la), FadeIn(row.lb), t=0.8)
    scene.beat(LaggedStart(*[x.animate.set_fill(SHADE, 0.9) for x in row.ra.shaded], lag_ratio=0.3),
               LaggedStart(*[x.animate.set_fill(SHADE, 0.9) for x in row.rb.shaded], lag_ratio=0.3),
               t=0.9)
    scene.beat(Create(row.guide), t=0.5)
    scene.beat(Write(row.equation), t=0.9)
    scene.beat(FadeIn(row.caption, shift=UP * 0.1), t=0.4)
    scene.hold(0.9)


def _animate_cross_products(scene: OverlayScene, row: VGroup, head=None) -> None:
    """Productos cruzados: fracciones → flecha + producto (×2) → veredicto ✓/✗."""
    intro = [Write(row.fa), Write(row.fb)] + ([FadeIn(head, shift=RIGHT * 0.2)] if head is not None else [])
    scene.beat(*intro, t=0.6)
    scene.beat(GrowArrow(row.ar1), t=0.4)
    scene.beat(TransformFromCopy(VGroup(row.fa.num, row.fb.den), row.p1), t=0.7)
    scene.beat(GrowArrow(row.ar2), t=0.4)
    scene.beat(TransformFromCopy(VGroup(row.fb.num, row.fa.den), row.p2), t=0.7)
    # Las flechas ya hicieron su trabajo: se retiran y aparece el signo entre las fracciones.
    scene.beat(Write(row.verdict), FadeIn(row.mark, scale=1.4), FadeOut(row.ar1), FadeOut(row.ar2),
               row.sign.animate.set_opacity(1), t=0.6)
    scene.beat(FadeIn(row.note), Indicate(row.vrow, color=OK if row.equivalent else BAD,
                                          scale_factor=1.08), t=0.5)
    scene.hold(0.7)


# ---------------------------------------------------------------------------
# Overlay genérico de fórmulas (sin escribir Python)
# ---------------------------------------------------------------------------
class FormulaOverlay(OverlayScene):
    """Overlay genérico: una fórmula LaTeX (y leyenda opcional) por tramo/imagen.

    Pensado para que cualquier guion pida fórmulas sobre sus imágenes solo
    desde el YAML:

        - id: "ESCENA-05"
          image_paths: [a.png, b.png]
          duration: 10
          manim_overlay: "FormulaOverlay"
          manim_overlay_params:
            titulo: "Productos cruzados"
            formulas: ["\\frac{2}{4} = \\frac{4}{8}", "2 \\times 8 = 4 \\times 4 = 16"]
            textos: ["Misma parte de la unidad", "Si coinciden, son equivalentes"]

    heavy_render.py manda `tramos` = duración de cada imagen, así que la
    fórmula cambia en el mismo cuadro que la imagen. Si hay más tramos que
    fórmulas, se repite la última (sin volver a escribirla).
    """

    SEGMENTS = ()
    DEFAULT_DURATION = 5.0
    DEFAULT_PARAMS = {
        "formulas": [],          # LaTeX sin $ (uno por tramo)
        "formula": None,         # atajo: una sola fórmula para todo el overlay
        "textos": [],            # leyenda opcional por tramo
        "titulo": None,          # pestaña dorada del panel
        "posicion": "abajo",     # abajo | arriba | centro | izquierda | derecha
        "tramos": None,
    }

    def _formulas(self) -> List[str]:
        formulas = self.params.get("formulas") or []
        if isinstance(formulas, str):
            formulas = [formulas]
        if not formulas and self.params.get("formula"):
            formulas = [self.params["formula"]]
        if not formulas:
            raise ValueError("FormulaOverlay necesita `formula` o `formulas` en manim_overlay_params")
        return [str(f) for f in formulas]

    def default_segments(self) -> List[float]:
        n = len(self._formulas())
        return [self.target_duration / n] * n

    def _content_for(self, i: int):
        formulas = self._formulas()
        textos = self.params.get("textos") or []
        if isinstance(textos, str):
            textos = [textos]
        j = min(i, len(formulas) - 1)
        texto = textos[min(i, len(textos) - 1)] if textos else None
        return formulas[j], texto

    def _build(self, formula: str, texto) -> VGroup:
        parts = [tex(formula, font_size=60, color=CHALK)]
        if texto:
            parts.append(T(str(texto), 26, MUTED))
        group = VGroup(*parts).arrange(DOWN, buff=0.22)
        titled = bool(self.params.get("titulo"))
        return fit_in(group, self.box, pad_x=0.8, pad_y=0.75 if titled else 0.45,
                      shift=DOWN * 0.12 if titled else np.zeros(3))

    def timeline(self):
        self.box = panel_box(self.params["posicion"])
        head = tag(str(self.params["titulo"]), self.box) if self.params.get("titulo") else None

        n_seg = len(self.segment_durations())
        keys = [self._content_for(i) for i in range(n_seg)]
        content = None
        for i, key in enumerate(keys):
            self.segment()
            if i == 0:
                intro = [FadeIn(self.box, shift=UP * 0.15)] + ([FadeIn(head)] if head else [])
                self.beat(*intro, t=0.4)
            if i == 0 or key != keys[i - 1]:
                content = self._build(*key)
                self.beat(Write(content), t=1.0)
            self.hold(2.0)
            last = i == n_seg - 1
            if last:
                outs = [FadeOut(content), FadeOut(self.box)] + ([FadeOut(head)] if head else [])
                self.beat(*outs, t=0.4)
            elif keys[i + 1] != key:
                self.beat(FadeOut(content), t=0.3)


# ---------------------------------------------------------------------------
# Fracciones (barras y/o productos cruzados) desde el YAML
# ---------------------------------------------------------------------------
class FractionOverlay(PanelOverlay):
    """Compara dos fracciones: barras de la misma unidad y/o productos cruzados.

        manim_overlay: "FractionOverlay"
        manim_overlay_params:
          a: "2/4"
          b: "4/8"
          modo: "ambos"        # barras | productos | ambos (un tramo para cada uno)
          titulo: "¿Son equivalentes?"

    Con modo "ambos" hay dos tramos (barras, luego productos): si la escena
    tiene dos imágenes, cada una recibe el suyo.
    """

    SEGMENTS = ()
    DEFAULT_DURATION = 6.0
    DEFAULT_PARAMS = {
        "a": "2/4", "b": "4/8",
        "modo": "ambos",          # barras | productos | ambos
        "titulo": None,
        "leyenda": None,          # texto bajo la igualdad en modo barras
        "nota": "Enteros, sin decimales",
        "posicion": "abajo",      # abajo | arriba | centro
        "icono": None,
        "tramos": None,
    }
    MODES = {"barras": ["barras"], "productos": ["productos"], "ambos": ["barras", "productos"]}

    def _parts(self) -> List[str]:
        modo = str(self.params["modo"]).lower()
        if modo not in self.MODES:
            raise ValueError(f"modo={modo!r}; usa {sorted(self.MODES)}")
        return self.MODES[modo]

    def default_segments(self) -> List[float]:
        n = len(self._parts())
        return [self.target_duration / n] * n

    def timeline(self):
        if self.is_column:
            raise ValueError("FractionOverlay usa posicion abajo, arriba o centro")
        a, b = parse_fraction(self.params["a"]), parse_fraction(self.params["b"])
        box, deco = self.make_panel()
        parts = self._parts()
        plan = distribute(len(parts), len(self.segment_durations()))
        pad_y = 0.75 if self.head else 0.45
        content = None
        for i, items in enumerate(plan):
            self.segment()
            if i == 0:
                self.beat(FadeIn(box, shift=UP * 0.15), *[FadeIn(d) for d in deco], t=0.4)
            if not items:                 # más imágenes que partes: se queda la última
                self.hold(1.0)
                continue
            for k in items:
                if content is not None:
                    self.beat(FadeOut(content), t=0.3)
                if parts[k] == "barras":
                    row = fraction_bars_row(a, b, are_equivalent(a, b), caption=self.params.get("leyenda"))
                    fit_in(row, box, pad_y=pad_y, shift=self.content_shift())
                    _animate_bars(self, row)
                    content = row
                else:
                    row = cross_products_row(a, b, note=str(self.params.get("nota") or ""))
                    fit_in(row, box, pad_y=pad_y, shift=self.content_shift())
                    _animate_cross_products(self, row)
                    content = VGroup(row.fracs, row.prods, row.right)
        self.beat(FadeOut(content), FadeOut(box), *[FadeOut(d) for d in deco], t=0.4)


# ---------------------------------------------------------------------------
# Ecuaciones de primer grado desde el YAML
# ---------------------------------------------------------------------------
class LinearEquationOverlay(PanelOverlay):
    """Despeje paso a paso de una ecuación de primer grado (y su comprobación).

        manim_overlay: "LinearEquationOverlay"
        manim_overlay_params:
          ecuacion: "x + 4 = 0"          # o `ecuaciones: [...]`, una por tramo/imagen
          titulo: "Primer caso"
          comprobar: true                 # agrega la sustitución con ✓ al final
          posicion: "abajo"               # abajo | arriba | centro | izquierda | derecha

    Los pasos salen de ecuaciones.solve_steps(): la operación que se aplica
    a ambos lados va en rojo (x + 4 - 4 = 0 - 4) y la solución en dorado
    dentro del recuadro «Una solución: x = -4». En las franjas los pasos van
    en horizontal; en las columnas izquierda/derecha, en vertical.
    """

    SEGMENTS = ()
    DEFAULT_DURATION = 8.0
    DEFAULT_PARAMS = {
        "ecuacion": None,
        "ecuaciones": [],
        "variable": "x",
        "titulo": None,
        "comprobar": False,
        "mostrar_operaciones": True,   # línea intermedia x + 4 - 4 = 0 - 4
        "explicar": True,              # texto de cada paso bajo los pasos
        "posicion": "abajo",
        "icono": None,
        "tramos": None,
    }

    def _equations(self) -> List[str]:
        eqs = self.params.get("ecuaciones") or []
        if isinstance(eqs, str):
            eqs = [eqs]
        if not eqs and self.params.get("ecuacion"):
            eqs = [self.params["ecuacion"]]
        if not eqs:
            raise ValueError("LinearEquationOverlay necesita `ecuacion` o `ecuaciones`")
        return [str(e) for e in eqs]

    def default_segments(self) -> List[float]:
        n = len(self._equations())
        return [self.target_duration / n] * n

    def _build(self, text: str, box) -> VGroup:
        eq = parse_linear(text, var=str(self.params["variable"]))
        steps = solve_steps(eq, show_operations=bool(self.params["mostrar_operaciones"]))
        vertical = self.is_column
        flow = steps_flow(steps[:-1] if len(steps) > 1 else steps, direction=DOWN if vertical else RIGHT,
                          font_size=50)
        sol = solution_box(eq.var, frac_latex(eq.solution))
        main = VGroup(flow, sol).arrange(DOWN if vertical else RIGHT, buff=0.5)
        parts = [main]
        expl = None
        if self.params["explicar"]:
            texts = [s.explanation for s in steps if s.kind == "operate"]
            if texts:
                expl = T(" · ".join(texts), 24, MUTED)
                parts.append(expl)
        check = None
        if self.params["comprobar"]:
            check = substitution_block(eq, font_size=40)
            check_lbl = T("Comprobación", 22, MUTED)
            check = VGroup(check_lbl, check).arrange(DOWN if vertical else RIGHT, buff=0.25)
            parts.append(check)
        group = VGroup(*parts).arrange(DOWN, buff=0.22)
        fit_in(group, box, pad_x=0.6, pad_y=0.8 if self.head else 0.4, shift=self.content_shift())
        group.flow, group.sol, group.expl, group.check, group.steps = flow, sol, expl, check, steps
        return group

    def timeline(self):
        box, deco = self.make_panel()
        eqs = self._equations()
        plan = distribute(len(eqs), len(self.segment_durations()))
        content = None
        for i, items in enumerate(plan):
            self.segment()
            if i == 0:
                self.beat(FadeIn(box, shift=UP * 0.15), *[FadeIn(d) for d in deco], t=0.4)
            if not items:
                self.hold(1.0)
                continue
            for k in items:
                content = self._show_equation(eqs[k], box, content)
        self.beat(FadeOut(content), FadeOut(box), *[FadeOut(d) for d in deco], t=0.4)

    def _show_equation(self, text: str, box, previous) -> VGroup:
        if previous is not None:
            self.beat(FadeOut(previous), t=0.3)
        content = self._build(text, box)
        lines, arrows = content.flow.lines, content.flow.arrows
        self.beat(Write(lines[0]), t=0.8)
        for k, (arr, ln) in enumerate(zip(arrows, lines[1:])):
            extra = [FadeIn(content.expl)] if (k == 0 and content.expl is not None) else []
            self.beat(GrowArrow(arr), Write(ln), *extra, t=0.9)
        if content.expl is not None and not len(arrows):
            self.beat(FadeIn(content.expl), t=0.3)
        self.beat(Create(content.sol.frame), Write(content.sol[1]), t=0.8)
        self.hold(1.2)
        if content.check is not None:
            chk = content.check
            self.beat(FadeIn(chk[0]), Write(chk[1].lines), t=0.9)
            self.beat(FadeIn(chk[1].mark, scale=1.4), t=0.4)
            self.hold(0.8)
        return content


# ---------------------------------------------------------------------------
# Gráficas desde el YAML
# ---------------------------------------------------------------------------
class GraphOverlay(PanelOverlay):
    """Plano cartesiano con la gráfica de un polinomio y sus raíces.

        manim_overlay: "GraphOverlay"
        manim_overlay_params:
          funcion: [1, 9, 20]          # coeficientes, mayor grado primero: x² + 9x + 20
          x_range: [-8, -1, 1]         # [min, max, paso]
          y_range: [-2, 6, 2]
          raices: true                 # marca las raíces reales (azul / naranja)
          puntos: [[-4.5, -0.25]]      # puntos extra (opcional)
          etiqueta: "y = x^2 + 9x + 20" # por defecto se arma con la función
          posicion: "derecha"          # derecha | izquierda (columna) | centro
          titulo: "Las soluciones son los cortes con el eje x"

    Tramos: si hay dos o más, el primero dibuja ejes y curva y cada tramo
    siguiente revela una raíz; con un solo tramo, todo ocurre en ese tramo.
    """

    SEGMENTS = ()
    DEFAULT_DURATION = 8.0
    DEFAULT_PARAMS = {
        "funcion": [1, 0, 0],
        "x_range": [-4, 4, 1],
        "y_range": [-2, 8, 2],
        "raices": True,
        "puntos": [],
        "etiqueta": None,
        "titulo": None,
        "posicion": "derecha",
        "icono": None,
        "tramos": None,
    }

    def timeline(self):
        box, deco = self.make_panel()
        w, h = box.width - 0.7, box.height - (1.5 if self.head else 1.1)
        if not self.is_column:          # franja: gráfica más baja y ancha
            w, h = min(6.5, box.width * 0.55), box.height - 0.6
        plot = function_plot(self.params["funcion"], self.params["x_range"], self.params["y_range"],
                             width=w, height=h, mark_roots=bool(self.params["raices"]),
                             points=[tuple(p) for p in (self.params.get("puntos") or [])],
                             label=self.params.get("etiqueta"))
        fit_in(plot, box, pad_x=0.5, pad_y=0.85 if self.head else 0.35, shift=self.content_shift())

        n_seg = len(self.segment_durations())
        reveals = list(zip(plot.roots, plot.root_labels))
        self.segment()
        self.beat(FadeIn(box, shift=UP * 0.15), *[FadeIn(d) for d in deco], t=0.4)
        self.beat(Create(plot.axes), t=0.9)
        intro = [Create(plot.graph)] + ([Write(plot.label)] if plot.label is not None else [])
        self.beat(*intro, t=1.3)
        if n_seg == 1:
            if reveals:
                self.beat(*[FadeIn(d, scale=1.6) for d, _ in reveals],
                          *[Write(l) for _, l in reveals], t=0.8)
            if len(plot.marks):
                self.beat(*[FadeIn(p, scale=1.6) for p in plot.marks], t=0.4)
            self.hold(1.5)
        else:
            self.hold(1.0)
            groups = [[r] for r in reveals]
            for i in range(1, n_seg):
                self.segment()
                if i - 1 < len(groups):
                    d, l = groups[i - 1][0]
                    self.beat(FadeIn(d, scale=1.6), Write(l), t=0.7)
                    self.beat(Indicate(d, scale_factor=1.6), t=0.5)
                elif len(plot.marks) and i - 1 == len(groups):
                    self.beat(*[FadeIn(p, scale=1.6) for p in plot.marks], t=0.4)
                self.hold(1.0)
        self.beat(FadeOut(plot), FadeOut(box), *[FadeOut(d) for d in deco], t=0.4)


# ---------------------------------------------------------------------------
# Registro: --scene <nombre> en scripts/render_manim_clips.py
#           manim_overlay: <nombre> en el YAML (heavy_render.py)
# ---------------------------------------------------------------------------
SCENE_REGISTRY: Dict[str, type] = {
    cls.__name__: cls
    for cls in (
        Scene02Math,
        FormulaOverlay,
        FractionOverlay,
        LinearEquationOverlay,
        GraphOverlay,
    )
}
