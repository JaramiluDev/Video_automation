# Perfiles de calidad de render (HG)

Para probar el pipeline sin saturar el equipo, todos los scripts de render
aceptan el mismo grupo de flags. La calidad final solo se usa para la entrega.

| Flag | Resolución (desde 1080p) | fps | libx264 | Hilos FFmpeg | Prioridad | Alfa `.mov` |
|---|---|---|---|---|---|---|
| `--fast` | 854×480 (lado corto 480) | ≤ 15 | `ultrafast`, crf 30 | 2 | baja | qtrle |
| `--low-res` | 1280×720 (lado corto 720) | ≤ 30 | `veryfast`, crf 26 | mitad de los núcleos | baja | qtrle |
| `--production` | la del guion | la del guion | `medium`, crf 18 | todos | normal | ProRes 4444 |

- Alias: `--quality fast|low-res|production` (también `draft`, `preview`, `720p`, `final`).
  En los scripts de Manim, `--preview` sigue funcionando y equivale a `--fast`.
- `--threads N` limita los hilos de FFmpeg (0 = automático) y gana sobre el perfil.
- Sin flag se usa la variable `VA_QUALITY` y, si no existe, `production`.
  En tu máquina de desarrollo puedes dejarla fija:
  - PowerShell (sesión actual): `$env:VA_QUALITY = "fast"`
  - PowerShell (permanente): `setx VA_QUALITY fast`
  - Linux / Docker: `export VA_QUALITY=fast`
- `VA_THREADS` fija los hilos por defecto; `VA_NO_NICE=1` desactiva la prioridad baja.
- Los perfiles nunca suben la resolución: un guion a 640×360 se queda así en `--fast`.
- Los perfiles conservan la proporción (un video vertical 1080×1920 en `--fast` sale 480×854).

## Dónde aplica

| Comando | Qué cambia con el perfil |
|---|---|
| `python -m src.video_automation.cli render --script X.yaml --fast` | Resolución/fps del video, codificación de MoviePy y de los clips Manim, quemado de subtítulos. Salida `X_fast.mp4` y clips en `manim_clips_fast/`. |
| `python scripts/build_zoomed_video.py <carpeta> --fast` | Ken Burns a 480p/15 fps con `ultrafast`. Clips en `animated_clips_fast/`, video `video2_base_render_fast.mp4`. |
| `python scripts/render_video2_scenes.py examples/video2_manim.yaml --fast` | Escenas Manim del Video 2. Salida en `data/renders/video2_manim_fast/`. |
| `python scripts/render_manim_clips.py --scene Scene02Math --output o.mov --fast` | Overlays con alfa (qtrle en vez de ProRes en borrador). |
| `python -m src.video_automation.cli profiles` | Lista los perfiles y cuál está activo. |

Los borradores usan sufijos (`_fast`, `_lowres`) para **no sobrescribir** los
renders de producción y para no mezclar clips de distinta resolución en la
misma carpeta: `simple_concatenator` une con `-c copy`, así que todos los clips
de una carpeta deben venir del mismo perfil.

## Caché de clips Manim

Los clips Manim (`render`, `render_video2_scenes.py`, `render_manim_clips.py`)
guardan junto a cada salida un archivo `<clip>.key`. Si al volver a correr no
cambió la escena, sus parámetros, la duración, la resolución/fps, el perfil ni
el código de las escenas, **no se vuelve a renderizar**. Para forzarlo:
`--no-cache`.

Además, las fórmulas LaTeX y los textos que Manim compila se guardan en
`~/.cache/video_automation/manim` (o en `VA_CACHE_DIR`), así que la segunda
vez que aparece una misma fórmula ya no se recompila.

### En Docker

`docker compose run --rm` crea un contenedor nuevo cada vez, así que la caché
en `~/.cache` se perdería. Pon en tu `.env` (ya viene en `.env.example`):

```
VA_CACHE_DIR=/app/data/.cache
VA_QUALITY=fast        # opcional: borrador por defecto en tu máquina
```

`data/.cache/` está en `.gitignore`. Ejemplo:

```bash
docker compose run --rm video-app python -m src.video_automation.cli render --script examples/video2_overlays.yaml --no-audio --fast
```

## Medición (2 núcleos, misma máquina)

| Tarea | `--fast` | `--low-res` | `--production` |
|---|---|---|---|
| 2 escenas Manim del Video 2 (`render_video2_scenes.py`) | 9.3 s · 0.6 GB | 14.8 s · 1.3 GB | 27.4 s · 2.7 GB |
| Overlay `Scene02Math` 15 s con alfa (`.mov`) | 5.1 s · 2.8 MB | — | 57.5 s · 148 MB |
| Ken Burns de 3 imágenes (`build_zoomed_video.py`) | 0.9 s | 5.3 s | 26.6 s |

(Memoria = RSS máxima del proceso; tamaño = archivo de salida.)
