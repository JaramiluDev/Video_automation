# Animaciones matemáticas dinámicas (`math_animator.py`)

Motor de escenas Manim **sin código duro**: la escena `DynamicMathScene` se construye
leyendo un archivo JSON/YAML (o un `dict` con la misma estructura).

## Uso

```powershell
# Borrador (480p @ 15 fps) → data/renders/manim/sample_math_low.mp4
python -m src.video_automation.math_animator --config data/scenes/sample_math.json --quality low

# Producción (1080p @ 60 fps) → data/renders/manim/sample_math.mp4
python -m src.video_automation.math_animator --config data/scenes/sample_math.json --quality high
```

`-ql` / `-qh` son equivalentes a `--quality low` / `--quality high`. También se aceptan
alias: `borrador`, `draft`, `fast` (low) y `produccion`, `final`, `1080p` (high).
`--output-dir` cambia la carpeta de salida (por defecto `data/renders/manim/`).

Desde Python:

```python
from pathlib import Path
from video_automation.math_animator import render_scene_from_config

video = render_scene_from_config(Path("data/scenes/sample_math.json"), quality="low")
```

## Esquema

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `name` | str | nombre del archivo | Nombre del `.mp4` de salida |
| `latex_expressions` | lista (≥1) | — | Expresiones LaTeX (sin `$`), en orden |
| `latex_expressions[].tex` | str | — | La expresión |
| `latex_expressions[].animation` | `write` \| `transform` \| `fadein` | 1.ª `write`, resto `transform` | Cómo entra a escena |
| `latex_expressions[].duration` | float > 0 | `duration` global | Segundos de este elemento |
| `latex_expressions[].color` | `#RRGGBB` | `text_color` | Color de la expresión |
| `text_labels` | lista | `[]` | Textos explicativos |
| `text_labels[].text` | str | — | Texto |
| `text_labels[].position` | `UP` `DOWN` `LEFT` `RIGHT` `UL` `UR` `DL` `DR` `CENTER` | `DOWN` | Posición en pantalla (acepta `arriba`, `abajo`, `izquierda`, `derecha`, `centro`) |
| `text_labels[].step` | int ≥ 0 | `0` | Índice de la expresión con la que aparece |
| `duration` | float > 0 | `2.0` | Segundos por elemento (animación + pausa) |
| `animation_time` | float > 0 | `1.0` | Parte de `duration` que dura la animación |
| `background_color` | `#RRGGBB` | `#1E3A2F` | Fondo oscuro del canal (pizarrón) |
| `text_color` | `#RRGGBB` | `#F5F1E6` | Color de gis |
| `tex_font_size` / `label_font_size` | float | `64` / `34` | Tamaños |
| `fade_out` | bool | `false` | Desvanecer todo al final (`animation_time / 2` s) |

La forma corta también es válida: `"latex_expressions": ["a^2+b^2=c^2", "c=\\sqrt{a^2+b^2}"]`
y `"text_labels": ["Nota"]`.

## Reglas de animación

- Las expresiones se muestran una a la vez, al centro.
- `transform` convierte la expresión anterior en la nueva; `write` y `fadein` primero
  desvanecen la anterior. La primera expresión no puede ser `transform`.
- Una etiqueta nueva en la misma posición reemplaza a la anterior (útil para la
  explicación de cada paso en `DOWN`).
- **Duración exacta:** el clip dura `round(suma_de_duraciones × fps)` cuadros
  (mismo control de cuadros que `manim_timing.TimedScene`), así encaja con el compositor.
- Si LaTeX no está instalado se usa texto plano como respaldo (`tex()` de
  `manim_timing`), salvo con `VA_STRICT_LATEX=1`.

## Pruebas

```powershell
python -m pytest tests/test_math_animator.py -q
```
