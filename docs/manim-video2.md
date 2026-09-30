# Animaciones matemáticas del Video 2 (HG)

Entregable: clases Manim con las fórmulas, ecuaciones y gráficas exactas del
guion **GUION-02 — Dominó de fracciones equivalentes**
(`assets/source_scripts/GUION-02/Guion_visual_12_escenas_36_imagenes.docx`).

## Archivos

| Archivo | Qué contiene |
|---|---|
| `src/video_automation/scenes_video2.py` | **Solo** las clases Manim del Video 2 + `SCENE_REGISTRY`. |
| `src/video_automation/fracciones.py` | Matemáticas puras (sin Manim): equivalencia por productos cruzados, niveles 15/28/45, cadena completa (recorrido euleriano). |
| `src/video_automation/manim_timing.py` | `TimedScene` (duración exacta), `render_timed_scene`, `normalize_clip`, `probe_video`, `check_latex`. |
| `src/video_automation/heavy_render.py` | Usa `manim_scene` del YAML; la tarjeta genérica de fórmula también dura exacto. |
| `examples/video2_manim.yaml` | Las 10 escenas con sus duraciones. |
| `scripts/render_video2_scenes.py` | Renderiza + verifica con ffprobe (tabla OK/FALLA). |
| `tests/test_scenes_video2.py` | 31 pruebas (matemáticas, plan de cuadros, registro, render real). |

## Escenas

| Clase | Guion | Qué anima |
|---|---|---|
| `V2E02_RepresentacionesEquivalentes` | Esc. 2 · Img 5 | 2/4 y 4/8 en unidades del mismo tamaño; superposición de áreas. |
| `V2E02_ProductosCruzados` | Esc. 2 · Img 6 | Flechas cruzadas, 2×8 = 16 = 4×4 → equivalentes. |
| `V2E03_UnionDomino` | Esc. 3 · Img 7 | Las mitades que se tocan son equivalentes; las otras no tienen por qué. |
| `V2E03_ColorUniforme` | Esc. 3 · Img 9 | Un color por valor (✗) vs color uniforme y trama B/N. |
| `V2E04_NivelesDificultad` | Esc. 4 · Img 10 | Tabla de parejas y n(n+1)/2: 5→15, 7→28, 9→45. |
| `V2E04_FigurasRepresentacion` | Esc. 4 · Img 11 | Solo fracción / solo imagen / ambas; rectángulo y círculo. |
| `V2E06_MedidasFicha` | Esc. 6 · Img 16-17 | Ficha 90×40 mm, contorno de corte, línea central, hoja 2×5, regla de 5 cm. |
| `V2E07_CadenaCompleta` | Esc. 7 · Img 21 | Cadena real que usa todas las fichas una vez + lista de comprobaciones calculadas. |
| `V2E09_ComprobacionManual` | Esc. 9 · Img 27 | 2/4 = 4/8 ✓ pero 2/4 ≠ 2/8 ✗ (mismas partes sombreadas ≠ misma fracción). |
| `V2E12_CierreRecorrido` | Esc. 12 · Img 36 | Objetivo → Requisitos → Código → Pruebas → Aula. |

Las fracciones son parámetros (`manim_params`), así que Richi/Jaramilu pueden
cambiar valores desde el YAML sin tocar Python.

## Contrato de tiempos con el parser

```yaml
- id: "ESCENA-02-IMG06"
  render_type: "manim"
  manim_scene: "V2E02_ProductosCruzados"
  manim_params: {a: "2/4", b: "4/8"}
  duration: 9.5        # el clip sale con round(9.5 * fps) cuadros, ni uno más
```

- `TimedScene` hace una pasada en seco para medir los *beats* y reparte
  exactamente `round(duration * fps)` cuadros.
- Si `duration` es mayor que la duración nominal, **se alargan las pausas**
  (las animaciones conservan su velocidad). Si es menor, se comprime todo.
- `render_manim_scene(scene, duration=...)` acepta otra duración por si el
  pipeline quiere inyectar la que midió el TTS.

## Formato de salida

`normalize_clip()` deja cada clip igual que `simple_animator.py`:
`libx264`, `yuv420p`, `-r 30|60` CFR, sin audio, 1920×1080. Por eso los clips
de Manim se pueden unir con los Ken Burns usando `simple_concatenator`
(`ffmpeg -f concat -c copy`) sin re-encodar.

## Prueba de fuego (Docker)

```bash
docker compose build          # el build ejecuta --check-latex y truena si falta LaTeX
docker compose run --rm video-app python scripts/render_video2_scenes.py examples/video2_manim.yaml
docker compose run --rm video-app python -m pytest -q
```

Dentro del contenedor `VA_STRICT_LATEX=1`: cualquier `MathTex` que falle rompe
el render (fuera de Docker, `tex()` cae a `Text` para poder desarrollar sin
LaTeX). Solo se usan paquetes de la plantilla por defecto de Manim
(`amsmath`, `amssymb`, `standalone`), cubiertos por `texlive` +
`texlive-latex-extra` + `dvisvgm`.

Previsualización rápida: añade `--preview` (854×480) y `--only <Clase>`.
