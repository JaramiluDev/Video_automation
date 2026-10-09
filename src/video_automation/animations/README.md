# Overlays y animaciones Manim (HG)

Clips de animación matemática que se **incrustan sobre** la base visual del
guion (los Ken Burns de `simple_animator.py` / `build_zoomed_video.py`).

| Archivo | Contenido |
|---|---|
| `math_scenes.py` | Solo las escenas Manim + `SCENE_REGISTRY` (`Scene02Math`, `FormulaOverlay`). |
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

## Agregar otra escena

1. Subclase de `OverlayScene` en `math_scenes.py` con `SEGMENTS` (un valor por imagen de la base).
2. En `timeline()`: `self.segment()` al inicio de cada tramo; animar solo con `self.beat(...)` / `self.hold(...)`.
3. Registrarla en `SCENE_REGISTRY`.
