# Video base sincronizado con el audio multi-voz (HG)

## El problema

`narrator.py` genera el audio del episodio escena por escena:

```
data/output/GUION-02_audio.mp3                          ← episodio completo (~21:11)
data/output/GUION-02_audio_dialogues/escena_01/
    turn_01_AgenteCero.mp3, turn_02_Detective.mp3, …    ← un archivo por turno
    escena_01_consolidated.mp3                          ← la escena completa
```

El video base, en cambio, tenía duraciones fijas: `build_zoomed_video.py` usaba
36 imágenes × 5 s = **3:00**, y `pipeline.py` unía video y audio con
`ffmpeg -shortest`. Resultado: el episodio de ~21 min quedaba cortado en 3 min.

## La solución (`heavy_render.py`)

1. **Duración por escena = su audio.** `plan_audio_sync()` busca
   `<id>/<id>_consolidated.mp3` (también `<id>_consolidated.*` en cualquier
   subcarpeta) y lo mide con `ffprobe`. Si falta el audio de alguna escena
   se detiene con `AudioSyncError` (o usa la `duration` del YAML con
   `strict=False` / `--allow-missing`).
2. **El total empata con el episodio.** Al concatenar las escenas, el MP3 se
   reencoda y se mueven unas decenas de ms por escena. El plan ajusta las
   escenas en proporción para que la suma sea exactamente
   `round(duración de GUION-02_audio.mp3 × fps)` cuadros.
3. **Todo en cuadros enteros.** Los cortes se redondean sobre el tiempo
   acumulado (`frames_for_durations`), así que no se acumula error: ningún
   cambio de escena se aleja más de medio cuadro de su audio.
4. **Reparto entre imágenes.** Las imágenes de cada escena vienen de
   `image_paths` del YAML o, si el guion no las trae (caso `GUION-02.yaml`),
   de la carpeta numerada: `escena_07` → `assets/source_scripts/GUION-02/ESCENA-07/`.
   Los cuadros se reparten en partes iguales y, con `--cut-mode turns` (por
   defecto), cada corte se mueve al cambio de turno más cercano (si queda a
   menos del 25 % de un tramo), para que la imagen cambie cuando cambia quien
   habla. Ninguna imagen dura menos de 1 s.
5. **Render.** Escenas solo-imágenes: un clip FFmpeg por imagen con el número
   exacto de cuadros (Ken Burns alternando zoom in/out, o fija con `--static`)
   y concatenación sin recodificar. Los clips se guardan en
   `data/output/base_clips[_fast]/` con caché (no se rehacen si no cambió la
   imagen ni sus cuadros). Si una escena trae overlay o es `render_type: manim`,
   se usa `render_video()` con las duraciones del audio.
6. **Verificación.** Al terminar se cuentan los cuadros reales del archivo y
   se guarda la línea de tiempo en `<base>.sync.json`.

## Uso

Pipeline completo (TTS → base sincronizado → video final):

```bash
python scripts/run_pipeline.py -s GUION-02 --fast                 # borrador 480p (~1 min)
python scripts/run_pipeline.py -s GUION-02 --production --reuse-audio
make episode EP=GUION-02 Q=--production                            # en Docker
```

- `-s GUION-02` busca primero `assets/source_scripts/GUION-02.yaml` (el guion
  multi-voz con `dialogue`) y después `assets/source_scripts/GUION-02/GUION-02.yaml`.
- `--reuse-audio` no vuelve a llamar a Edge-TTS si ya existen el audio del
  episodio y todos los `*_consolidated.mp3`.
- `--no-sync-base` regresa al comportamiento anterior (base fijo + `-shortest`).
- `--static`, `--cut-mode equal`, `--images-root RUTA` ajustan el base.

Solo el video base (o solo revisar la línea de tiempo):

```bash
python -m src.video_automation.cli sync-base \
    --script assets/source_scripts/GUION-02.yaml \
    --audio data/output/GUION-02_audio.mp3 --plan-only

python -m src.video_automation.cli sync-base \
    --script assets/source_scripts/GUION-02.yaml \
    --audio data/output/GUION-02_audio.mp3 --production [--mux]
```

`--plan-only` imprime algo así (audio sintético de 21:11):

```
escena             audio     video  imágenes (s)
escena_01        105.74s   105.70s  [34.60, 39.43, 31.67]
…
escena_12         90.77s    90.73s  [26.23, 32.57, 31.93]
TOTAL                     1271.07s  = 21:11.067 (38132 cuadros @ 30 fps)
Audio del episodio: 21:11.064 (1271.064s) → diferencia +0.003s
```

## Mediciones (audio sintético de 21:11, 12 escenas, 36 imágenes)

| Perfil | Video base | Tiempo |
|---|---|---|
| `--fast` (854x480 @ 15 fps) | 19 066 cuadros = 21:11.067 | ~45 s |
| final (`pipeline.py`) | video 21:11.067 / audio 21:11.0 | +30 s del mux |

La diferencia con el audio siempre es menor a 1 cuadro.

## API

```python
from video_automation.heavy_render import plan_audio_sync, render_audio_synced_base

plan = plan_audio_sync(script, fps=30, episode_audio="data/output/GUION-02_audio.mp3",
                       images_root="assets/source_scripts/GUION-02")
print(plan.table())
render_audio_synced_base(script, "data/output/GUION-02_base.mp4",
                         episode_audio="data/output/GUION-02_audio.mp3", plan=plan)
```

`apply_audio_sync(script, plan)` devuelve una copia del guion con
`duration` = cuadros/fps del audio, para cualquier otro render (subtítulos,
overlays) que necesite los mismos tiempos.
