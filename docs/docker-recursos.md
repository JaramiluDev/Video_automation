# Consumo de RAM/CPU en Docker y límites del contenedor (HG)

Mediciones de los renders más pesados del proyecto dentro del contenedor,
los cuellos de botella que aparecieron y cómo quedaron los límites de
`docker-compose.yml`.

## Cómo medir

`scripts/bench_render.py` lanza un comando (o `--jobs N` copias en paralelo) y
cada 0.25 s suma la memoria residente y el CPU de todo el árbol de procesos
(Python + Manim + FFmpeg + LaTeX). Dentro de Docker también reporta el pico
del cgroup, el límite y si hubo OOM.

```bash
docker compose run --rm video-app python scripts/bench_render.py --json data/renders/bench/results.jsonl -- \
    python -m src.video_automation.cli render --script examples/episodio3_overlays.yaml --no-audio --production --no-cache

# Dos renders a la vez ({job} = 0, 1 para no escribir el mismo archivo)
docker compose run --rm video-app python scripts/bench_render.py --jobs 2 -- \
    python scripts/render_video2_scenes.py examples/video2_manim.yaml --draft --no-cache -o "data/renders/bench/r_{job}"
```

## Equipo y cargas de prueba

Contenedor con 2 núcleos y 7.8 GB, imagen del `Dockerfile` (Manim 0.22, MoviePy 2.1,
TeX Live, FFmpeg). Caché de LaTeX ya caliente, clips con `--no-cache`.

| Carga | Qué es |
|---|---|
| W1 | Escena Manim más compleja del Video 2 (`V2E07_CadenaCompleta`, 15 s, 28 fichas) |
| W2 | Overlay con alfa `Scene02Math` (15 s) con `render_manim_clips.py` (`.mov`) |
| W3 | Pipeline completo del Episodio 3: `examples/episodio3_overlays.yaml` (4 escenas × 3 imágenes + overlays, 60 s) |

RAM = pico del cgroup (lo que compara `mem_limit`); CPU = núcleos promedio.

## Resultados

### Escenas Manim y overlays

| Carga | Perfil | Tiempo | RAM pico | CPU prom. |
|---|---|---|---|---|
| W1 | `--draft` | 6.8 s | 0.26 GB | 1.0 |
| W1 | `--low-res` | 13.0 s | 0.34 GB | 1.2 |
| W1 | `--production` | 23.8 s | 0.72 GB | 1.4 |
| W2 | `--draft` | 7.0 s | 0.17 GB | 1.0 |
| W2 | `--production` (ProRes 4444) | 72.5 s | 0.51 GB | 1.7 |
| W1 ×2 en paralelo | `--production` | 35.7 s | 1.56 GB | 1.8 |
| W1 ×3 en paralelo | `--draft` | 12.6 s | 0.72 GB | 1.6 |
| W2 ×2 en paralelo | `--production` | 129.6 s | 1.06 GB | 1.9 |

- Manim (renderer Cairo) usa **un núcleo** por proceso: dos escenas en paralelo
  rinden 1.3–1.6× más que en serie. ProRes ya usa los dos núcleos, así que
  paralelizar overlays ProRes casi no gana (1.1×).

### Pipeline del Episodio 3 (60 s de video)

| Versión | Perfil | Tiempo | RAM pico |
|---|---|---|---|
| Antes (MoviePy compone, overlay ProRes) | `--draft` | 70.7 s | 0.65 GB |
| Antes | `--low-res` | 267 s | 1.32 GB |
| Antes | `--production` | **914 s** | **3.76 GB** |
| Ahora (FFmpeg compone, overlay qtrle, lectores perezosos) | `--draft` | 55.4 s | 0.49 GB |
| Ahora | `--low-res` | 144 s | 0.76 GB |
| Ahora | `--production` | **267 s** | **1.18 GB** |
| Ahora · episodio de 12 escenas (180 s) | `--production` | 801 s | 1.44 GB |

Con límites (`--memory`, sin swap):

| Prueba | Límite | Resultado |
|---|---|---|
| Producción, código anterior | 1.5 GB | **OOM** (el kernel lo mata al empezar la exportación) |
| Producción, código actual | 1.5 GB | OK, pico 1.18 GB |
| Episodio de 12 escenas, producción | 2 GB | OK, pico 1.44 GB (la RAM ya no crece con el número de escenas) |
| Borrador | 1 GB / 1 CPU | OK, 83 s (vs 52 s con 2 CPU) |
| Borrador ×2 en paralelo | 1 GB | OK, pico 0.97 GB (al límite: usa 2 GB si vas a correr dos) |
| 2 producciones en paralelo vía `docker compose run` (límites del compose) | 3 GB / 2 CPU | OK, pico 2.36 GB, 449 s (vs 534 s en serie) |

## Problemas encontrados y corregidos

1. **La RAM crecía con cada escena.** Cada `VideoFileClip` de MoviePy arranca
   un proceso `ffmpeg` lector (~220 MB a 1080p) y lo deja vivo hasta el final;
   los overlays `.mov` con alfa abrían dos (color + máscara). Un episodio de 17
   escenas se habría ido a más de 4 GB.
   → `compositor.lazy_video_clip()`: el lector se abre al llegar al clip y se
   cierra en su último cuadro (`VA_LAZY_CLIPS=0` vuelve al comportamiento anterior).
2. **Componer overlays en Python era lo más lento.** `CompositeVideoClip`
   mezclaba cada cuadro en Python.
   → `compositor.overlay_scene_ffmpeg()`: cada escena imágenes + overlay se
   compone con los filtros `concat`/`overlay` de FFmpeg y queda en
   `<salida>/manim_clips/<id>_scene.mp4` con su propia caché
   (`VA_COMPOSITOR=moviepy` para la ruta anterior).
3. **ProRes 4444 para overlays que nadie más va a ver.** Dentro del pipeline el
   `.mov` con alfa se compone y se descarta: ahora va en QuickTime RLE (qtrle),
   sin pérdida, ~7× más rápido y ~10× más ligero (15 MB vs 141 MB por overlay
   de 15 s a 1080p). `render_manim_clips.py --production` sigue entregando
   ProRes para edición en Premiere/DaVinci.
4. **Renders en paralelo rompían la caché de Manim.** Dos procesos generando
   el mismo SVG de texto/LaTeX a la vez: uno leía el archivo a medio escribir
   (`no element found: line 1, column 0`) y el SVG vacío se quedaba en la caché,
   así que **todos** los renders siguientes fallaban. → cada proceso toma un
   slot de caché con candado (`<cache>/manim`, `.../slot1`, ...) y al tomarlo
   borra SVG vacíos o truncados (`manim_timing.manim_cache_root()`).
5. **FFmpeg veía todos los núcleos del host.** Dentro de un contenedor con
   `cpus: 2`, `os.cpu_count()` devuelve los núcleos del host y el perfil de
   producción ("hilos automáticos") lanzaba un hilo por cada uno. Ahora los
   perfiles respetan la cuota del cgroup y la afinidad de CPU.

## Límites en `docker-compose.yml`

```yaml
    cpus: ${VA_CPUS:-2}
    mem_limit: ${VA_MEM_LIMIT:-3g}
    memswap_limit: ${VA_MEM_LIMIT:-3g}   # sin swap: falla claro (137) en vez de congelar el equipo
    pids_limit: 512
    init: true
```

Se cambian en `.env` sin tocar el compose:

| Uso | `VA_CPUS` | `VA_MEM_LIMIT` |
|---|---|---|
| Solo borradores (`--draft`) | 2 | 1g (2g si corres dos a la vez) |
| Un render de producción (por defecto) | 2 | 3g |
| Dos renders de producción en paralelo | 2–4 | 4g |

`3g` deja ~2.5× de margen sobre el pico medido de producción (1.18 GB) para
escenas con más fórmulas o imágenes más grandes, y aguanta dos producciones a
la vez (2.36 GB), aunque justo; para eso es mejor `4g`. Con 2 núcleos,
paralelizar el pipeline completo solo gana ~1.2×: conviene más cuando hay
4 núcleos o más (`VA_CPUS=4`). Si el contenedor se pasa,
el proceso termina con código **137** (`OOM` en `bench_render.py`): sube
`VA_MEM_LIMIT` o usa `--draft` mientras iteras.

> [!note] Docker Desktop (Windows)
> Los límites del contenedor no pueden pasar de la memoria que Docker Desktop
> tiene asignada (con el backend WSL2 se fija en `%UserProfile%\.wslconfig`,
> clave `memory=`). Con 4 GB asignados, deja `VA_MEM_LIMIT=3g`.

## Pendiente

- La exportación final (`compose_clips`) sigue pasando todos los cuadros por
  MoviePy. Es el siguiente candidato: si no hay audio ni subtítulos que mezclar,
  se podría concatenar con `ffmpeg -f concat` sin re-codificar.
