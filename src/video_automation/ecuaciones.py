"""
Lógica matemática pura de ecuaciones (HG) — sin Manim, igual que fracciones.py.

Sirve a los componentes de animations/components.py y a los overlays
LinearEquationOverlay / GraphOverlay. Todo se calcula con fractions.Fraction
(enteros y fracciones exactas, nunca decimales), así lo que se ve en pantalla
siempre es correcto y se prueba con pytest en milisegundos.

Ecuaciones de primer grado
--------------------------
    eq = parse_linear("x + 4 = 0")
    for step in solve_steps(eq):           # pasos de despeje, como en el pizarrón
        print(step.latex, "·", step.explanation)
    #  x + 4 = 0
    #  x + 4 - 4 = 0 - 4      · Restamos 4 en ambos lados
    #  x = -4                 · Una solución: x = -4

Formato admitido en cada lado: sumas/restas de términos `a`, `ax`, `a/bx`,
`-x`... con UNA variable (por defecto x). Ejemplos: "3x - 5 = 10",
"2x + 3 = x - 1", "x/2 + 1 = 4", "-x = 7". No admite paréntesis ni productos
de variables: para eso el guion escribe los pasos a mano con FormulaOverlay.

Polinomios (gráficas)
---------------------
    coeffs = [1, 9, 20]                    # x^2 + 9x + 20 (mayor grado primero)
    poly_eval(coeffs, -4)  → 0
    real_roots(coeffs)     → [-5, -4]      # exactas si el discriminante es cuadrado
    poly_latex(coeffs)     → "x^{2} + 9x + 20"
    find_pair(20, 9)       → (4, 5)        # dos números: producto 20, suma 9
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, List, Optional, Sequence, Tuple, Union

Number = Union[int, Fraction]
Coeff = Union[int, float, str, Fraction]

# ---------------------------------------------------------------------------
# Formato LaTeX de números exactos
# ---------------------------------------------------------------------------


def frac_latex(value: Number, signed: bool = False) -> str:
    """Fraction(-3, 4) → '-\\frac{3}{4}'; Fraction(5) → '5'. signed=True antepone '+'."""
    q = Fraction(value)
    sign = "-" if q < 0 else ("+" if signed else "")
    q = abs(q)
    body = str(q.numerator) if q.denominator == 1 else rf"\frac{{{q.numerator}}}{{{q.denominator}}}"
    return sign + body


def paren_latex(value: Number) -> str:
    """Número listo para sustituir: los negativos van entre paréntesis, (-4)."""
    q = Fraction(value)
    return rf"\left({frac_latex(q)}\right)" if q < 0 else frac_latex(q)


def _term_latex(coef: Fraction, var: str, first: bool) -> str:
    """Un término con su signo: 3x, -x, + 4, - \\frac{1}{2}x."""
    mag = abs(coef)
    if var:
        body = var if mag == 1 else f"{frac_latex(mag)}{var}"
    else:
        body = frac_latex(mag)
    if first:
        return ("-" if coef < 0 else "") + body
    return (" - " if coef < 0 else " + ") + body


# ---------------------------------------------------------------------------
# Expresiones lineales  a·x + b
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Linear:
    """Expresión lineal a·var + b con coeficientes exactos."""

    a: Fraction = Fraction(0)
    b: Fraction = Fraction(0)

    def __add__(self, other: "Linear") -> "Linear":
        return Linear(self.a + other.a, self.b + other.b)

    def __sub__(self, other: "Linear") -> "Linear":
        return Linear(self.a - other.a, self.b - other.b)

    def evaluate(self, x: Number) -> Fraction:
        return self.a * Fraction(x) + self.b

    def latex(self, var: str = "x") -> str:
        parts: List[str] = []
        if self.a != 0:
            parts.append(_term_latex(self.a, var, first=True))
        if self.b != 0 or not parts:
            parts.append(_term_latex(self.b, "", first=not parts))
        return "".join(parts)


_TERM = re.compile(
    r"""\s*(?P<sign>[+-])?\s*
        (?P<num>\d+)?\s*(?:/\s*(?P<den>\d+))?\s*
        (?P<var>[a-zA-Z])?\s*(?:/\s*(?P<den2>\d+))?\s*""",
    re.VERBOSE,
)


def parse_side(text: str, var: str = "x") -> Linear:
    """'2x + 3 - x/2' → Linear(3/2, 3). Lanza ValueError si no es lineal en `var`."""
    src = text.replace("−", "-").replace("·", "").replace("*", "").strip()
    if not src:
        raise ValueError("un lado de la ecuación está vacío")
    pos, total, seen = 0, Linear(), False
    while pos < len(src):
        m = _TERM.match(src, pos)
        if not m or m.end() == pos or not (m.group("num") or m.group("var")):
            raise ValueError(f"no se entiende {src[pos:]!r} en {text!r}")
        if seen and not m.group("sign"):
            raise ValueError(f"falta un signo + o - antes de {src[pos:m.end()].strip()!r} en {text!r}")
        name = m.group("var")
        if name and name != var:
            raise ValueError(f"variable {name!r} inesperada en {text!r} (se esperaba {var!r})")
        coef = Fraction(int(m.group("num"))) if m.group("num") else Fraction(1)
        for den in (m.group("den"), m.group("den2")):
            if den:
                if int(den) == 0:
                    raise ValueError(f"división entre cero en {text!r}")
                coef /= int(den)
        if m.group("sign") == "-":
            coef = -coef
        total = total + (Linear(coef, Fraction(0)) if name else Linear(Fraction(0), coef))
        pos, seen = m.end(), True
    return total


@dataclass(frozen=True)
class LinearEquation:
    left: Linear
    right: Linear
    var: str = "x"

    def latex(self) -> str:
        return f"{self.left.latex(self.var)} = {self.right.latex(self.var)}"

    @property
    def solution(self) -> Fraction:
        a = self.left.a - self.right.a
        b = self.right.b - self.left.b
        if a == 0:
            raise ValueError("la ecuación no es de primer grado (la variable se cancela)")
        return b / a


def parse_linear(text: str, var: str = "x") -> LinearEquation:
    """'3x - 5 = 10' → LinearEquation. Exige un solo '=' y que la variable no se cancele."""
    if text.count("=") != 1:
        raise ValueError(f"una ecuación necesita exactamente un '=': {text!r}")
    left, right = text.split("=")
    eq = LinearEquation(parse_side(left, var), parse_side(right, var), var)
    _ = eq.solution  # valida que sea de primer grado
    return eq


# ---------------------------------------------------------------------------
# Pasos de despeje
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """Una línea del procedimiento.

    latex:       la ecuación de esa línea.
    explanation: texto corto para el panel ("Restamos 4 en ambos lados").
    op:          la operación aplicada a AMBOS lados en LaTeX ("- 4", "\\div 3"),
                 vacía en la primera línea y en las simplificaciones.
    kind:        "start" | "operate" | "simplify" | "solution".
    """

    latex: str
    explanation: str
    op: str = ""
    kind: str = "simplify"


def plain(value: Number) -> str:
    """Número para texto normal (no LaTeX): Fraction(-1, 2) → '-1/2'."""
    q = Fraction(value)
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def _verb(value: Fraction, adding: bool) -> str:
    return f"{'Sumamos' if adding else 'Restamos'} {plain(abs(value))} en ambos lados"


def solve_steps(eq: LinearEquation, show_operations: bool = True) -> List[Step]:
    """
    Procedimiento de despeje en el orden del guion:
      1. variable de la derecha → a la izquierda,
      2. constante de la izquierda → a la derecha,
      3. dividir entre el coeficiente.
    Con show_operations=True cada operación muestra la línea intermedia
    (x + 4 - 4 = 0 - 4) antes de simplificar, como en el pizarrón.
    """
    v = eq.var
    left, right = eq.left, eq.right
    steps = [Step(eq.latex(), "Ecuación original", kind="start")]

    def operate(term: Linear, explanation: str) -> None:
        nonlocal left, right
        sign = "-" if (term.a or term.b) > 0 else "+"
        mag = Linear(abs(term.a), abs(term.b)).latex(v)
        op = f"{sign} {mag}"
        if show_operations:
            steps.append(Step(f"{left.latex(v)} {op} = {right.latex(v)} {op}", explanation, op, "operate"))
        left, right = left - term, right - term
        steps.append(Step(f"{left.latex(v)} = {right.latex(v)}",
                          "Simplificamos" if show_operations else explanation,
                          "" if show_operations else op, "simplify"))

    if left.a == 0 and right.a != 0:
        # 4 = 2x → 2x = 4: la variable queda a la izquierda sin operar.
        left, right = right, left
        steps.append(Step(f"{left.latex(v)} = {right.latex(v)}", "Intercambiamos los lados", kind="simplify"))
    if right.a != 0:
        term = Linear(right.a, Fraction(0))
        operate(term, f"{'Restamos' if right.a > 0 else 'Sumamos'} "
                      f"{Linear(abs(right.a), Fraction(0)).latex(v)} en ambos lados")
    if left.b != 0:
        operate(Linear(Fraction(0), left.b), _verb(left.b, adding=left.b < 0))

    a = left.a
    if a != 1:
        if show_operations:
            num_l = Linear(a, Fraction(0)).latex(v)
            rhs = frac_latex(right.b)
            if a.denominator == 1 and a != -1:
                steps.append(Step(rf"\frac{{{num_l}}}{{{frac_latex(a)}}} = \frac{{{rhs}}}{{{frac_latex(a)}}}",
                                  f"Dividimos ambos lados entre {plain(a)}",
                                  rf"\div {paren_latex(a)}", "operate"))
            else:
                # Coeficiente fraccionario o -1: multiplicar por el inverso se lee mejor
                # que una fracción de fracciones.
                inv = 1 / a
                steps.append(Step(rf"{paren_latex(inv)} \cdot \left({num_l}\right) = "
                                  rf"{paren_latex(inv)} \cdot {paren_latex(right.b)}",
                                  f"Multiplicamos ambos lados por {plain(inv)}",
                                  rf"\cdot {paren_latex(inv)}", "operate"))
        right, left = Linear(Fraction(0), right.b / a), Linear(Fraction(1), Fraction(0))
    sol = eq.solution
    steps.append(Step(f"{v} = {frac_latex(sol)}", f"Una solución: {v} = {frac_latex(sol)}",
                      kind="solution"))
    # Si la última simplificación ya era x = sol, no se repite la línea.
    if len(steps) >= 2 and steps[-2].latex == steps[-1].latex:
        steps.pop(-2)
    return steps


def check_steps(eq: LinearEquation, value: Optional[Number] = None) -> Tuple[List[str], bool]:
    """
    Comprobación por sustitución: ['(-4) + 4 = 0', '0 = 0'] y si se cumple.
    value=None usa la solución de la ecuación.
    """
    x = Fraction(eq.solution if value is None else value)
    v = eq.var

    def substituted(expr: Linear) -> str:
        parts: List[str] = []
        if expr.a != 0:
            coef = "" if expr.a == 1 else ("-" if expr.a == -1 else frac_latex(expr.a))
            mult = r" \cdot " if coef not in ("", "-") else ""
            parts.append(f"{coef}{mult}{paren_latex(x)}")
        if expr.b != 0 or not parts:
            parts.append(_term_latex(expr.b, "", first=not parts))
        return "".join(parts).replace(v, "")

    lhs, rhs = eq.left.evaluate(x), eq.right.evaluate(x)
    ok = lhs == rhs
    rel = "=" if ok else r"\neq"
    lines = [f"{substituted(eq.left)} = {substituted(eq.right)}",
             f"{frac_latex(lhs)} {rel} {frac_latex(rhs)}"]
    return lines, ok


# ---------------------------------------------------------------------------
# Polinomios (para las gráficas)
# ---------------------------------------------------------------------------


def _coeffs(coeffs: Sequence[Coeff]) -> List[Fraction]:
    out = [Fraction(str(c)) if isinstance(c, (str, float)) else Fraction(c) for c in coeffs]
    while len(out) > 1 and out[0] == 0:
        out.pop(0)
    if not out:
        raise ValueError("el polinomio no tiene coeficientes")
    return out


def poly_eval(coeffs: Sequence[Coeff], x: Number) -> Fraction:
    """Horner exacto. coeffs: mayor grado primero ([1, 9, 20] = x² + 9x + 20)."""
    acc = Fraction(0)
    for c in _coeffs(coeffs):
        acc = acc * Fraction(x) + c
    return acc


def poly_latex(coeffs: Sequence[Coeff], var: str = "x") -> str:
    cs = _coeffs(coeffs)
    deg = len(cs) - 1
    parts: List[str] = []
    for i, c in enumerate(cs):
        p = deg - i
        if c == 0:
            continue
        v = "" if p == 0 else (var if p == 1 else f"{var}^{{{p}}}")
        mag = abs(c)
        body = frac_latex(mag) if (not v or mag != 1) else ""
        body += v
        if not parts:
            parts.append(("-" if c < 0 else "") + body)
        else:
            parts.append((" - " if c < 0 else " + ") + body)
    return "".join(parts) or "0"


def real_roots(coeffs: Sequence[Coeff]) -> List[Union[Fraction, float]]:
    """Raíces reales de grado 1 o 2, ordenadas. Exactas (Fraction) cuando se puede."""
    cs = _coeffs(coeffs)
    if len(cs) == 2:
        return [-cs[1] / cs[0]]
    if len(cs) == 3:
        a, b, c = cs
        disc = b * b - 4 * a * c
        if disc < 0:
            return []
        num, den = disc.numerator, disc.denominator
        rn, rd = math.isqrt(num), math.isqrt(den)
        roots: set[Union[Fraction, float]]
        if rn * rn == num and rd * rd == den:
            sq = Fraction(rn, rd)
            roots = {(-b - sq) / (2 * a), (-b + sq) / (2 * a)}
        else:
            s = math.sqrt(float(disc))
            roots = {(-float(b) - s) / (2 * float(a)), (-float(b) + s) / (2 * float(a))}
        return sorted(roots)
    if len(cs) == 1:
        return []
    raise ValueError("real_roots solo resuelve grado 1 o 2")


def vertex(coeffs: Sequence[Coeff]) -> Tuple[Fraction, Fraction]:
    """Vértice de una parábola a x² + b x + c."""
    cs = _coeffs(coeffs)
    if len(cs) != 3:
        raise ValueError("vertex() necesita un polinomio de grado 2")
    a, b, _ = cs
    h = -b / (2 * a)
    return h, poly_eval(cs, h)


def find_pair(product: int, total: int, candidates: Optional[Iterable[Tuple[int, int]]] = None
              ) -> Optional[Tuple[int, int]]:
    """Dos enteros con producto `product` y suma `total` (el 'casting de números')."""
    for p, q in (candidates or pairs_with_product(product)):
        if p * q == product and p + q == total:
            return p, q
    return None


def pairs_with_product(product: int) -> List[Tuple[int, int]]:
    """Parejas de enteros (p <= q en valor absoluto) con p·q = product: 20 → (1,20), (2,10), (4,5)..."""
    if product == 0:
        return [(0, 0)]
    n = abs(product)
    out: List[Tuple[int, int]] = []
    for p in range(1, math.isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if product > 0:
                out += [(p, q), (-p, -q)]
            else:
                out += [(p, -q), (-p, q)]
    return out
