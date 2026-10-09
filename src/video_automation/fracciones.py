"""
Lógica matemática pura del Video 2 (Dominó de fracciones equivalentes).

No importa Manim a propósito: así se puede probar con pytest en milisegundos
y las escenas de scenes_video2.py solo se encargan de dibujar.

Todo lo que aquí se calcula sigue las reglas del guion (GUION-02, anexo
"Prompt completo de referencia"):
  - Fracciones positivas propias (0 < numerador < denominador).
  - Equivalencia por productos cruzados de ENTEROS, nunca con decimales.
  - Niveles: Inicial (5 familias / 15 fichas), Intermedio (7 / 28),
    Avanzado (9 / 45).
  - Fichas = todas las parejas NO ordenadas de familias, incluidas las dobles.
  - Una cadena completa usa cada ficha exactamente una vez.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import gcd
from typing import Dict, List, Sequence, Tuple

Fraction = Tuple[int, int]

# Familias por nivel, tomadas literalmente del guion.
NIVELES: Dict[str, List[Fraction]] = {
    "inicial": [(1, 4), (1, 3), (1, 2), (2, 3), (3, 4)],
    "intermedio": [(1, 6), (1, 4), (1, 3), (1, 2), (2, 3), (3, 4), (5, 6)],
    "avanzado": [(1, 8), (1, 6), (1, 4), (1, 3), (1, 2), (2, 3), (3, 4), (5, 6), (7, 8)],
}

# Multiplicadores para las fracciones ESCRITAS según el nivel (guion).
MULTIPLICADORES_ESCRITOS: Dict[str, Tuple[int, ...]] = {
    "inicial": (2, 3),
    "intermedio": (2, 3, 4),
    "avanzado": (2, 3, 4),
}
# Para las imágenes: multiplicadores de 1 a 4 respetando el límite de 16 partes.
MULTIPLICADORES_IMAGEN = (1, 2, 3, 4)
MAX_PARTES_IMAGEN = 16


def parse_fraction(value) -> Fraction:
    """Acepta "2/4", (2, 4) o [2, 4] y devuelve una tupla validada."""
    if isinstance(value, str):
        try:
            num_s, den_s = value.replace(" ", "").split("/")
            num, den = int(num_s), int(den_s)
        except ValueError as exc:
            raise ValueError(f"Fracción inválida: {value!r} (usa el formato 'a/b')") from exc
    else:
        num, den = int(value[0]), int(value[1])
    if den <= 0 or num <= 0:
        raise ValueError(f"Solo se admiten fracciones positivas: {num}/{den}")
    if num >= den:
        raise ValueError(f"El guion solo usa fracciones propias (num < den): {num}/{den}")
    return num, den


def simplify(fr: Fraction) -> Fraction:
    g = gcd(fr[0], fr[1])
    return fr[0] // g, fr[1] // g


def cross_products(a: Fraction, b: Fraction) -> Tuple[int, int]:
    """(a_num * b_den, b_num * a_den). Si son iguales, las fracciones son equivalentes."""
    return a[0] * b[1], b[0] * a[1]


def are_equivalent(a: Fraction, b: Fraction) -> bool:
    left, right = cross_products(a, b)
    return left == right


def expected_tile_count(n_families: int) -> int:
    """Parejas no ordenadas con repetición: n(n+1)/2 → 5→15, 7→28, 9→45."""
    return n_families * (n_families + 1) // 2


def generate_tiles(families: Sequence[Fraction]) -> List[Tuple[int, int]]:
    """Índices (i, j) con i <= j: todas las parejas no ordenadas, dobles incluidas."""
    n = len(families)
    return [(i, j) for i in range(n) for j in range(i, n)]


def eulerian_chain(n_families: int, tiles: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Devuelve una cadena completa que usa TODAS las fichas una sola vez.

    Se modela como un multigrafo (familias = vértices, fichas = aristas, dobles =
    lazos) y se busca un recorrido euleriano con Hierholzer. Cada elemento del
    resultado es (idx_ficha, orientacion) con orientacion 0 = normal, 1 = invertida,
    de modo que el extremo derecho de una ficha coincide con el izquierdo de la
    siguiente.

    Con familias completas cada vértice tiene grado n+1; para n impar (5, 7, 9,
    los tres niveles) todos los grados son pares y el circuito siempre existe.
    """
    adj: Dict[int, List[int]] = {v: [] for v in range(n_families)}
    for t_idx, (a, b) in enumerate(tiles):
        adj[a].append(t_idx)
        if a != b:
            adj[b].append(t_idx)

    odd = [v for v in adj if _degree(v, tiles, adj) % 2 == 1]
    if len(odd) not in (0, 2):
        raise ValueError("No existe una cadena que use todas las fichas una vez.")
    start = odd[0] if odd else 0

    used = [False] * len(tiles)
    ptr = {v: 0 for v in adj}
    stack: List[Tuple[int, int | None]] = [(start, None)]
    path: List[Tuple[int, int | None]] = []
    while stack:
        v, via = stack[-1]
        while ptr[v] < len(adj[v]) and used[adj[v][ptr[v]]]:
            ptr[v] += 1
        if ptr[v] == len(adj[v]):
            path.append(stack.pop())
        else:
            t_idx = adj[v][ptr[v]]
            used[t_idx] = True
            a, b = tiles[t_idx]
            stack.append((b if v == a else a, t_idx))
    path.reverse()

    chain: List[Tuple[int, int]] = []
    for (prev_v, _), (v, t_idx) in zip(path, path[1:]):
        a, b = tiles[t_idx]
        # Normal si la ficha se lee (a | b) de izquierda a derecha.
        orient = 0 if (prev_v == a and v == b) else 1
        chain.append((t_idx, orient))
    if len(chain) != len(tiles):
        raise ValueError("El grafo de fichas no es conexo.")
    return chain


def _degree(v: int, tiles, adj) -> int:
    return sum(2 if tiles[t][0] == tiles[t][1] else 1 for t in adj[v])


def validate_chain(chain, tiles, n_tiles: int) -> bool:
    """Comprueba: cada ficha una vez y extremos que se tocan de la misma familia."""
    if sorted(t for t, _ in chain) != list(range(n_tiles)):
        return False
    ends = [tiles[t] if o == 0 else tiles[t][::-1] for t, o in chain]
    return all(left[1] == right[0] for left, right in zip(ends, ends[1:]))


@dataclass(frozen=True)
class HalfRepr:
    """Cómo se dibuja una mitad de ficha: 'frac' (escrita), 'rect' o 'circle'."""
    kind: str
    num: int
    den: int


def representation_for(family: Fraction, level: str, rng: random.Random,
                       mode: str = "mixto", figuras: str = "rect") -> HalfRepr:
    """
    Elige una representación equivalente de la familia, igual que el programa:
    escritas con multiplicadores del nivel, imágenes con 1..4 sin pasar de 16 partes.
    mode: 'fracciones' | 'imagenes' | 'mixto'. figuras: 'rect' | 'circle' | 'variadas'.
    """
    if mode not in ("fracciones", "imagenes", "mixto"):
        raise ValueError(f"mode inválido: {mode}")
    use_image = mode == "imagenes" or (mode == "mixto" and rng.random() < 0.5)
    if use_image:
        mults = [m for m in MULTIPLICADORES_IMAGEN if family[1] * m <= MAX_PARTES_IMAGEN]
        m = rng.choice(mults)
        if figuras == "variadas":
            kind = rng.choice(("rect", "circle"))
        else:
            kind = figuras
        return HalfRepr(kind, family[0] * m, family[1] * m)
    m = rng.choice(MULTIPLICADORES_ESCRITOS[level])
    return HalfRepr("frac", family[0] * m, family[1] * m)
