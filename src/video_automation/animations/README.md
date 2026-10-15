# Overlays y animaciones Manim (HG)

Clips de animación matemática que se **incrustan sobre** la base visual del
guion (los Ken Burns de `simple_animator.py` / `build_zoomed_video.py`).

| Archivo | Contenido |
|---|---|
| `components.py` | **Catálogo de componentes reutilizables**: estilo, paneles, fracciones, ecuaciones de primer grado, gráficas y recursos SVG/PNG. Sin tiempo ni escenas. |
| `math_scenes.py` | Solo las escenas Manim + `SCENE_REGISTRY` (`Scene02Math`, `FormulaOverlay`, `FractionOverlay`, `LinearEquationOverlay`, `GraphOverlay`). |
| `base.py` | `OverlayScene`: tramos alineados a los cortes de la base (5 s por imagen) y fondo transparente opcional. |
| `export.py` | `render_overlay()`: 1080p, fps constante, cuadros exactos; `.mp4` opaco o `.mov`/`.webm` con alfa. Verificación con ffprobe. |
| `../../../scripts/render_manim_clips.py` | CLI. |

## Uso

```bash
# Opaco (H.264/yuv420p, igual que simple_animator.py)
python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mp4

# Con transparencia (recomendado para overlay)
python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mov
python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.webm
python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mp4 --alpha   # → escribe .mov

# Borrador sin saturar el equipo (480p, 15 fps, 2 hilos) — ver docs/render-profiles.md
python scripts/render_manim_clips.py --scene Scene02Math --output prueba.mov --fast
python scripts/render_manim_clips.py --scene Scene02Math --output prueba.mov --low-res
python scripts/render_manim_clips.py --list
```

En PowerShell, los parámetros con corchetes van entre comillas:
`--param "orden=[img06,img04,img05]" --param "tramos=[5,5,5]" --param posicion=arriba`

## Formatos de salida

| Extensión | Códec | Alfa | Notas |
|---|---|---|---|
| `.mp4` | libx264, yuv420p | No | Concatenable con los Ken Burns (`-c copy`). Fondo de pizarrón. |
| `.mov` | ProRes 4444 (`yuva444p`) | Sí | Estándar para edición. ~150 MB por 15 s: **no subir a Git** (límite de GitHub: 100 MB). |
| `.webm` | VP9 (`yuva420p`) | Sí | ~1 MB. Para leer el alfa: `ffmpeg -c:v libvpx-vp9 -i overlay.webm ...` |

Todas salen a 1920x1080, 30 fps CFR, `round(duración × 30)` cuadros exactos.

## Scene02Math (GUION-02 · Escena 2 · imágenes 4-5-6)

Panel de pizarrón semitransparente en el tercio inferior (la mesa en las
ilustraciones: no tapa caras ni el pizarrón). 3 tramos de 5 s = 15 s; el
contenido cambia en el mismo cuadro que el corte de imagen de la base.

| Tramo | Imagen | Qué muestra |
|---|---|---|
| `img04` | 4 | Borrador de prompt + campos `[grado]` `[conocimientos previos]` `[dificultad]` + «Sin nombres ni datos personales». |
| `img05` | 5 | 2/4 y 4/8 en unidades del mismo tamaño, línea guía en la mitad, `2/4 = 4/8 = 1/2`. |
| `img06` | 6 | Productos cruzados `2×8 = 16`, `4×4 = 16` → `16 = 16 ✓` (enteros, sin decimales). |

Parámetros (`--param`): `a`, `b` (fracciones), `orden`, `tramos`, `posicion` (`abajo`/`arriba`/`centro`).

## Desde el YAML (pipeline completo)

`heavy_render.py` ya incrusta overlays sin pasos manuales. En una escena de
imágenes basta con `manim_overlay`:

```yaml
- id: "ESCENA-02"
  image_paths: [img6.png, img4.png, img5.png]
  duration: 15.0
  manim_overlay: "Scene02Math"
  manim_overlay_params: {orden: [img06, img04, img05]}
```

Cada imagen es un tramo del overlay (`tramos` = duración de cada imagen), así
que el contenido cambia en el mismo cuadro que la imagen. El overlay se
renderiza a `.mov` con alfa en `<salida>/manim_clips[_fast]/<id>_overlay.mov`
(con caché) y se compone encima. Ejemplo completo:
`examples/video2_overlays.yaml`.

```bash
python -m src.video_automation.cli render --script examples/video2_overlays.yaml --no-audio --fast
```

### FormulaOverlay: fórmulas sin escribir Python

Overlay genérico para cualquier guion. Parámetros: `formulas` (LaTeX, una
por tramo; si hay más tramos que fórmulas se repite la última), `formula`
(atajo para una sola), `textos` (leyenda opcional por tramo), `titulo`
(pestaña dorada), `posicion` (`abajo`/`arriba`/`centro`) y `tramos`.

```yaml
manim_overlay: "FormulaOverlay"
manim_overlay_params:
  titulo: "Comprobación manual"
  tramos: [4, 4]                 # dos momentos sobre una sola imagen
  formulas:
    - '\frac{2}{4} = \frac{4}{8}'
    - '\frac{2}{4} \neq \frac{2}{8}'
  textos: ["Sí son equivalentes", "No son equivalentes"]
```

En YAML usa comillas simples para el LaTeX: así `\frac` no necesita escaparse.

## Incrustar sobre la base (manual, con FFmpeg)

La Escena 2 empieza en el segundo 15 de `video2_base_render.mp4` (Escena 1 = 3 imágenes × 5 s):

```bash
ffmpeg -i video2_base_render.mp4 -itsoffset 15 -i manim_overlay.mov \
  -filter_complex "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto,format=yuv420p" \
  -c:v libx264 -r 30 -c:a copy video2_con_overlay.mp4
```

## Catálogo de componentes (`components.py`)

Piezas que devuelven un Mobject listo para animar; la lógica matemática está en
`fracciones.py` y `ecuaciones.py` (sin Manim, probada con pytest). Las escenas
del Video 2 (`scenes_video2.py`) y todos los overlays usan este catálogo, así
cada episodio comparte el mismo estilo y las mismas matemáticas verificadas.

| Grupo | Componentes | Qué hace |
|---|---|---|
| Estilo | `BG CHALK MUTED SHADE GOLD OK BAD BLUE ORANGE`, `T()`, `titulo()`, `rotulo()`, `check_mark()`, `resolve_font()` | Paleta del pizarrón; texto con la primera fuente instalada (DejaVu en Docker, Segoe UI/Arial en Windows). `BLUE`/`ORANGE` = colores del 4 y el 5 en «¡Se busca a la x!». |
| Paneles | `PANEL_LAYOUTS`, `panel_box(pos)`, `tag()`, `fit_in()` | Franjas `abajo`/`arriba`/`centro` y columnas `izquierda`/`derecha` para gráficas. |
| Fracciones | `frac()`, `fraction_rect()`, `fraction_circle()`, `fraction_equation()`, `fraction_bars_row()`, `cross_products_row()` | Fracción con numerador/denominador señalables, unidades de igual área, igualdad simplificada, productos cruzados con ✓/✗. |
| Ecuaciones | `steps_flow()`, `solution_box()`, `substitution_block()` (+ `ecuaciones.parse_linear/solve_steps/check_steps`) | Despeje de `ax + b = c` con la operación de ambos lados en rojo, recuadro «Una solución», comprobación por sustitución. |
| Gráficas | `function_plot()`, `number_line_points()` (+ `ecuaciones.real_roots/poly_latex/vertex`) | Plano cartesiano de un polinomio con raíces marcadas; recta numérica con puntos. |
| SVG / PNG | `asset_mobject(ruta, height)` | `.svg` → `SVGMobject` (recoloreable), `.png/.jpg` → `ImageMobject` (respeta transparencia). Rutas relativas a la raíz del repo. |

## Overlays genéricos (solo YAML)

| Overlay | Parámetros principales | Tramos |
|---|---|---|
| `FormulaOverlay` | `formula`/`formulas`, `textos`, `titulo`, `posicion` | Una fórmula por imagen. |
| `FractionOverlay` | `a`, `b`, `modo` (`barras`/`productos`/`ambos`), `leyenda`, `nota`, `titulo`, `icono` | `ambos` = barras en la 1.ª imagen, productos en la 2.ª. |
| `LinearEquationOverlay` | `ecuacion`/`ecuaciones`, `comprobar`, `mostrar_operaciones`, `explicar`, `variable`, `titulo`, `posicion`, `icono` | Una ecuación por imagen; en `izquierda`/`derecha` los pasos van en vertical. |
| `GraphOverlay` | `funcion` (coeficientes, mayor grado primero), `x_range`, `y_range`, `raices`, `puntos`, `etiqueta`, `posicion`, `titulo`, `icono` | 1.ª imagen: ejes y curva; cada imagen siguiente revela una raíz. |

Si hay **más imágenes que contenidos**, las imágenes extra conservan el último;
si hay **menos**, la última imagen muestra todos los restantes. `icono` acepta
un `.svg` o `.png` que se coloca en la esquina superior derecha del panel.

Ejemplo completo (Episodio 3 · «¡Se busca a la x!»): `examples/episodio3_overlays.yaml`.

```bash
python -m src.video_automation.cli render --script examples/episodio3_overlays.yaml --no-audio --draft
python scripts/render_manim_clips.py --scene LinearEquationOverlay --output e.mov --draft --param "ecuacion=x + 4 = 0" --param comprobar=true
python scripts/render_manim_clips.py --scene GraphOverlay --output g.mov --draft --param "funcion=[1,9,20]" --param "x_range=[-7,-2,1]" --param "y_range=[-1,6,1]"
```

## Agregar otra escena

1. Subclase de `OverlayScene` (o `PanelOverlay`, que ya arma panel, pestaña e ícono) en `math_scenes.py` con `SEGMENTS` (un valor por imagen de la base). Dibuja con las piezas de `components.py`; si falta una, agrégala ahí y no en la escena.
2. En `timeline()`: `self.segment()` al inicio de cada tramo; animar solo con `self.beat(...)` / `self.hold(...)`.
3. Registrarla en `SCENE_REGISTRY`.
