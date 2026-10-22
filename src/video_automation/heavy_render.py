"""
Motor de Renderizado de Video Pesado (heavy_render.py)
Módulo asignado a HG.

Orquesta el ensamblado visual final: conecta secuencias de imágenes y
animaciones matemáticas de Manim en una sola línea de tiempo, y delega en
compositor.py (audio real + subtítulos quemados + export) para el resultado.

Tipos de escena (models.Scene):
  - render_type "images"                 → imágenes del guion.
  - render_type "images" + manim_overlay → imágenes con un overlay Manim
                                           transparente encima (fórmulas,
                                           paneles), un tramo por imagen.
  - render_type "manim"                  → animación Manim a pantalla completa
                                           (manim_scene registrado o FormulaCard).

Composición (HG, optimización): cada escena imágenes + overlay se compone
con FFmpeg en <salida>/manim_clips/<id>_scene.mp4 (overlay intermedio en qtrle,
sin pérdida) y los clips ya renderizados se leen de forma perezosa (un lector
ffmpeg a la vez). Mediciones: docs/docker-recursos.md.

Audio multi-voz: plan_audio_sync() / render_audio_synced_base() hacen que cada
escena dure lo que su <id>_consolidated.mp3 y que el video base empate con el
audio del episodio cuadro a cuadro (ver docs/audio-sync.md).

Calidad: render_video(..., profile=...) usa render_profiles.py
(--fast / --low-res / --production). Los clips Manim se guardan en
<salida>/manim_clips[_fast|_lowres]/ con una clave de caché: si no cambió la
escena, sus parámetros, la duración, el formato ni el código, no se vuelven a
renderizar.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from moviepy import VideoFileClip

from .models import ScriptDefinition, Scene, OutputSettings
from .compositor import build_image_clip, compose_clips
from .render_profiles import RenderProfile, default_profile

log = logging.getLogger(__name__)


def _formula_card_class(scene: Scene):
    """
    Escena genérica (título + fórmula LaTeX o narración) para guiones que solo
    traen `formula`. Ahora hereda de TimedScene, así que también dura
    EXACTAMENTE scene.duration (antes duraba duration + 0.5 s).
    """
    from manim import Text, Write, FadeOut, VGroup, UP
    from .manim_timing import TimedScene, tex

    class FormulaCard(TimedScene):
        def timeline(self):
            mobjects = []
            if scene.text_on_screen:
                mobjects.append(Text(scene.text_on_screen, font_size=36).to_edge(UP))
            if scene.formula:
                mobjects.append(tex(scene.formula, font_size=64))
            elif scene.narration:
                mobjects.append(Text(scene.narration, font_size=40))
            if not mobjects:
                self.hold(1.0)  # clip vacío pero con la duración correcta
                return
            group = VGroup(*mobjects) if len(mobjects) > 1 else mobjects[0]
            # Evita que texto/fórmulas largas se salgan del cuadro.
            max_width = self.camera.frame_width * 0.9
            max_height = self.camera.frame_height * 0.8
            if group.width > max_width:
                group.scale_to_fit_width(max_width)
            if group.height > max_height:
                group.scale_to_fit_height(max_height)
            self.beat(Write(group), t=1.0)
            self.hold(max(scene.duration - 1.5, 0.5))
            self.beat(FadeOut(group), t=0.5)

    FormulaCard.__name__ = f"FormulaCard_{scene.id}".replace("-", "_")
    return FormulaCard


def render_manim_scene(scene: Scene, resolution: tuple = (1920, 1080), fps: int = 30,
                       clips_dir: Optional[str] = None, duration: Optional[float] = None,
                       profile: Optional[RenderProfile] = None, use_cache: bool = False):
    """
    Renderiza una escena con Manim y devuelve un clip de MoviePy (lector
    perezoso del .mp4) listo para concatenarse con el resto de la línea de tiempo.

    - scene.manim_scene → clase registrada en scenes_video2.py (Video 2).
    - si no, scene.formula / scene.narration → tarjeta genérica (FormulaCard).

    En ambos casos el clip sale con resolución, fps y número de cuadros
    exactos (round(duration * fps)), codificado igual que simple_animator
    (libx264 / yuv420p / CFR), para que compositor.py y simple_concatenator
    no tengan que re-sincronizar nada.

    duration: permite que el pipeline inyecte otro tiempo (ej. el que midió
    el TTS). Por defecto se usa scene.duration, que es lo que da el parser.

    resolution/fps son los finales (ya escalados por el perfil). use_cache
    reutiliza el clip de clips_dir si su clave coincide.
    """
    from .manim_timing import render_timed_scene

    target = float(duration if duration is not None else scene.duration)
    out_dir = Path(clips_dir) if clips_dir else Path(tempfile.mkdtemp(prefix="manim_clips_"))
    out_path = out_dir / f"{scene.id}.mp4"

    what = scene.manim_scene or _formula_card_class(scene)
    extra = None if scene.manim_scene else {
        "formula": scene.formula, "text_on_screen": scene.text_on_screen, "narration": scene.narration,
    }
    render_timed_scene(what, str(out_path), duration=target, params=scene.manim_params,
                       resolution=tuple(resolution), fps=fps, profile=profile,
                       use_cache=use_cache, cache_extra=extra)

    print(f"🎬 Escena Manim '{scene.id}' renderizada en: {out_path} ({target:.3f}s @ {fps}fps)")
    return _file_clip(out_path, target, fps)


def _file_clip(path, duration: float, fps: int):
    """Clip de un .mp4 ya renderizado: perezoso (un lector ffmpeg a la vez) salvo VA_LAZY_CLIPS=0."""
    if os.environ.get("VA_LAZY_CLIPS", "1").strip() not in ("0", "false", "no"):
        from .compositor import lazy_video_clip

        return lazy_video_clip(str(path), duration, fps)
    return _exact_clip(VideoFileClip(str(path)), duration, fps)


def _exact_clip(clip, duration: float, fps: int):
    """
    Fija la duración del clip a sus cuadros reales: round(duration * fps) / fps.

    En borrador (--draft/--fast, 15 fps) una duración como 9.5 s no cae en la
    rejilla de cuadros (142.5) y el clip sale con 142. El contenedor reporta
    9.47 s y MoviePy intentaba leer el cuadro 142, que no existe ("bytes
    wanted but 0 bytes read"). Con la duración exacta no lee de más.
    """
    frames = max(1, int(round(float(duration) * fps)))
    exact = frames / float(fps)
    if clip.duration is None or abs(clip.duration - exact) > 1e-9:
        clip = clip.with_duration(min(exact, clip.duration or exact))
    return clip


def validate_manim_scenes(script: ScriptDefinition) -> None:
    """Falla ANTES de renderizar si el YAML pide una escena/overlay que no existe."""
    from .manim_timing import get_scene_class

    for scene in script.scenes:
        if scene.render_type == "manim" and scene.manim_scene:
            get_scene_class(scene.manim_scene)  # lanza KeyError con la lista disponible
        if scene.manim_overlay:
            if scene.render_type == "manim":
                raise ValueError(f"La escena {scene.id}: manim_overlay solo aplica a render_type 'images'")
            from .animations.export import get_overlay_scene

            get_overlay_scene(scene.manim_overlay)  # KeyError con la lista disponible
        if scene.duration <= 0:
            raise ValueError(f"La escena {scene.id} tiene duration <= 0")


def image_seconds(scene: Scene, fps: int) -> List[float]:
    """
    Segundos de cada imagen de la escena en cuadros enteros: la suma es
    exactamente round(scene.duration × fps) / fps (ver split_scene_frames).
    """
    n = len(scene.image_paths or [])
    if not n:
        return []
    total = max(n, int(round(float(scene.duration) * fps)))
    return [f / float(fps) for f in split_scene_frames(total, n, fps)]


def overlay_params(scene: Scene, image_durations: Sequence[float]) -> dict:
    """
    Parámetros del overlay con los tramos alineados a las imágenes de la
    escena. Si la clase tiene SEGMENTS fijos de otro tamaño, se respetan
    (se escalan a la duración) y se avisa que los cortes pueden no coincidir.
    """
    from .animations.export import get_overlay_scene

    cls = get_overlay_scene(scene.manim_overlay)
    params = dict(scene.manim_overlay_params or {})
    if params.get("tramos") is None and image_durations:
        segments = tuple(getattr(cls, "SEGMENTS", ()) or ())
        if not segments or len(segments) == len(image_durations):
            params["tramos"] = [float(d) for d in image_durations]
        else:
            log.warning("%s: %s tiene %d tramos y la escena %d imágenes; los cambios del overlay "
                        "no caerán en los cortes de imagen.", scene.id, cls.__name__,
                        len(segments), len(image_durations))
    return params


#: Códecs con alfa para overlays INTERNOS del pipeline (se componen y se descartan).
INTERNAL_ALPHA_CODECS = ("qtrle", "png", "prores_ks")


def internal_overlay_profile(profile: RenderProfile) -> RenderProfile:
    """
    Mismo perfil, pero el .mov con alfa intermedio va en QuickTime RLE (qtrle):
    sin pérdida, y en un overlay de 15 s a 1080p tarda ~10 s y pesa ~15 MB
    contra ~72 s y ~140 MB de ProRes 4444. ProRes sigue siendo el formato de
    entrega de scripts/render_manim_clips.py para quien edita en Premiere/DaVinci.
    """
    from dataclasses import replace

    return replace(profile, alpha_codecs=INTERNAL_ALPHA_CODECS)


def render_scene_overlay(scene: Scene, base_clips: List, resolution: Tuple[int, int], fps: int,
                         clips_dir: Path, profile: Optional[RenderProfile] = None,
                         use_cache: bool = False):
    """
    Renderiza el overlay Manim de una escena de imágenes (.mov con alfa) y lo
    compone encima de sus imágenes. Devuelve UN clip con la duración exacta
    de la escena.

    Por defecto la composición la hace FFmpeg (compositor.overlay_scene_ffmpeg)
    y el resultado se guarda como <id>_scene.mp4 junto al overlay, con su
    propia clave de caché. Con VA_COMPOSITOR=moviepy (o si FFmpeg falla) se
    usa la composición anterior con MoviePy.
    """
    from .animations import render_overlay

    resolution = (int(resolution[0]), int(resolution[1]))
    profile = profile or default_profile()
    n_img = len(scene.image_paths)
    image_durations = image_seconds(scene, fps) if n_img else []

    params = overlay_params(scene, image_durations)
    out = Path(clips_dir) / f"{scene.id}_overlay.mov"
    render_overlay(scene.manim_overlay, str(out), duration=scene.duration, params=params,
                   resolution=resolution, fps=fps, profile=internal_overlay_profile(profile),
                   use_cache=use_cache)
    print(f"🧮 Overlay '{scene.manim_overlay}' sobre '{scene.id}': {out}")

    if n_img and os.environ.get("VA_COMPOSITOR", "ffmpeg").strip().lower() != "moviepy":
        try:
            return _scene_clip_ffmpeg(scene, image_durations, out, resolution, fps, profile, use_cache)
        except (RuntimeError, OSError) as exc:
            log.warning("%s: composición con FFmpeg falló (%s); se usa MoviePy.", scene.id, exc)
    return _scene_clip_moviepy(scene, base_clips, out, resolution, fps)


def _scene_clip_ffmpeg(scene: Scene, image_durations: List[float], overlay: Path,
                       resolution: Tuple[int, int], fps: int, profile: RenderProfile,
                       use_cache: bool):
    import hashlib
    import json

    from .compositor import overlay_scene_ffmpeg
    from .manim_timing import cached_clip_is_valid, store_cache_key

    target = overlay.with_name(f"{scene.id}_scene.mp4")
    key = None
    if use_cache:
        def stamp(p: str):
            try:
                st = os.stat(p)
                return [p, st.st_size, int(st.st_mtime)]
            except OSError:
                return [p, None, None]
        try:
            overlay_key = overlay.with_name(overlay.name + ".key").read_text(encoding="utf-8").strip()
        except OSError:
            overlay_key = None
        payload = {"overlay": overlay_key, "images": [stamp(p) for p in scene.image_paths],
                   "durations": image_durations, "res": list(resolution), "fps": fps,
                   "profile": [profile.name, profile.x264_preset, profile.crf], "v": 1}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if overlay_key and cached_clip_is_valid(str(target), key):
            log.info("%s: escena compuesta en caché (%s)", scene.id, target)
            return _file_clip(target, scene.duration, fps)
    overlay_scene_ffmpeg(list(scene.image_paths), image_durations, str(overlay), str(target),
                         fps=fps, resolution=resolution, profile=profile)
    if key:
        store_cache_key(str(target), key)
    return _file_clip(target, scene.duration, fps)


def _scene_clip_moviepy(scene: Scene, base_clips: List, overlay: Path,
                        resolution: Tuple[int, int], fps: int):
    """Composición anterior (MoviePy): más lenta y con más RAM; queda como respaldo."""
    from moviepy import ColorClip, CompositeVideoClip, concatenate_videoclips

    base_clips = [c for c in base_clips if c is not None]
    if not base_clips and scene.image_paths:      # venían sin construir (ruta FFmpeg)
        base_clips = [c for c in (build_image_clip(p, d, resolution)
                                  for p, d in zip(scene.image_paths, image_seconds(scene, fps)))
                      if c is not None]
    if base_clips:
        base = base_clips[0] if len(base_clips) == 1 else concatenate_videoclips(base_clips, method="compose")
    else:
        log.warning("%s: sin imágenes válidas; el overlay va sobre fondo negro.", scene.id)
        base = ColorClip(size=resolution, color=(0, 0, 0), duration=scene.duration)
    clip = _exact_clip(VideoFileClip(str(overlay), has_mask=True), scene.duration, fps)
    return CompositeVideoClip([base, clip.with_position((0, 0))], size=resolution) \
        .with_duration(max(1, int(round(scene.duration * fps))) / float(fps))


def resolve_output_format(script: ScriptDefinition, profile: RenderProfile,
                          resolution: Optional[Sequence[int]] = None,
                          fps: Optional[int] = None) -> Tuple[Tuple[int, int], int]:
    """
    Formato final: lo que pida la CLI (--resolution/--fps) o, si no, el
    output_settings del guion; después el perfil lo escala (fast → 480p...).
    """
    settings = script.output_settings or OutputSettings()
    base_res = tuple(resolution) if resolution else tuple(settings.resolution)
    base_fps = int(fps) if fps else int(settings.fps)
    return profile.resolve(base_res, base_fps)


def render_video(script: ScriptDefinition, output_dir: str,
                 profile: Optional[RenderProfile] = None,
                 resolution: Optional[Sequence[int]] = None,
                 fps: Optional[int] = None,
                 use_cache: bool = True) -> str:
    """
    Punto de entrada principal del módulo. Recorre las escenas del guión en
    orden, arma un clip por cada una (imagen, imagen + overlay o Manim) y
    llama a compose_clips() con audio y subtítulos si el guión los trae.

    profile: perfil de calidad (None → $VA_QUALITY o production).
    resolution/fps: sobrescriben output_settings del guion (antes de escalar).
    use_cache: reutiliza clips Manim ya renderizados con la misma clave.
    """
    print(f"Iniciando renderizado pesado para: {script.title}")

    profile = profile or default_profile()
    res, out_fps = resolve_output_format(script, profile, resolution, fps)
    print(f"⚙️  {profile.summary(res, out_fps)}")
    validate_manim_scenes(script)
    clips: List = []
    # Los clips de Manim se conservan junto al render final por si se
    # quieren revisar o unir con simple_concatenator (-c copy). Cada perfil
    # usa su carpeta para no mezclar resoluciones.
    clips_dir = profile.tag_dir(Path(output_dir) / "manim_clips")

    for scene in script.scenes:
        if scene.render_type == "manim":
            clips.append(render_manim_scene(scene, resolution=res, fps=out_fps,
                                            clips_dir=str(clips_dir), profile=profile,
                                            use_cache=use_cache))
            continue
        scene_clips = []
        lazy = scene.manim_overlay and os.environ.get("VA_COMPOSITOR", "ffmpeg").lower() != "moviepy"
        # Cuadros exactos por imagen: la suma de la escena es round(duration × fps)
        # (antes duration / n en flotante, que podía correr un cuadro por escena).
        for img, duration in zip(scene.image_paths, image_seconds(scene, out_fps)):
            # Con FFmpeg las imágenes del overlay no pasan por MoviePy (ni su RAM).
            scene_clips.append(None if lazy else build_image_clip(img, duration, res))
        if scene.manim_overlay:
            clips.append(render_scene_overlay(scene, scene_clips, res, out_fps, clips_dir,
                                              profile=profile, use_cache=use_cache))
        else:
            clips.extend(scene_clips)

    # Los borradores no pisan el render de producción: video.mp4 → video_fast.mp4
    output_file = profile.tag_path(Path(output_dir) / script.output_filename)

    result = compose_clips(
        clips,
        str(output_file),
        audio_path=script.audio_path,
        subtitle_path=script.subtitle_path,
        fps=out_fps,
        resolution=res,
        profile=profile,
    )

    print(f"Renderizado pesado completado. Video guardado en: {result}")
    return result


# ===========================================================================
# Sincronización con el audio multi-voz (HG)
# ===========================================================================
#
# Antes cada escena duraba lo que dijera el YAML (o 5 s por imagen en
# build_zoomed_video.py): 36 imágenes × 5 s = 3:00, mientras el audio
# multi-voz de narrator.py dura ~21 min. pipeline.py une ambos con
# `ffmpeg -shortest`, así que el episodio final quedaba cortado en 3 min.
#
# Ahora la duración de cada escena se LEE de su audio consolidado
# (<salida>/<guion>_audio_dialogues/<id>/<id>_consolidated.mp3), el total se
# ajusta al audio del episodio (<guion>_audio.mp3) y los cuadros se reparten
# entre las imágenes de la escena (cortes en los cambios de turno cuando se
# puede). Todo se cuenta en CUADROS enteros, así que la suma del video base es
# exactamente round(duración del audio × fps).

AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
CONSOLIDATED_SUFFIX = "_consolidated"
#: Si el audio del episodio y la suma de escenas difieren más que esto, se avisa.
DRIFT_WARN_SECONDS = 1.0
#: Un corte de imagen se "pega" al cambio de turno más cercano si queda a menos
#: de esta fracción del tramo ideal (0.25 → ~7 s en tramos de 30 s).
TURN_SNAP_FRACTION = 0.25
#: Ninguna imagen dura menos que esto (si la escena alcanza).
MIN_IMAGE_SECONDS = 1.0


class AudioSyncError(RuntimeError):
    """Faltan audios de escena o no se pueden medir."""


# -- Medición ---------------------------------------------------------------

def probe_duration(path) -> float:
    """
    Duración real (s) de un audio/video con ffprobe. Si el contenedor no trae
    la duración (o ffprobe no está), decodifica con MoviePy como respaldo.
    """
    path = str(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            value = float(out)
            if value > 0:
                return value
        except (subprocess.CalledProcessError, ValueError):
            pass
    from moviepy import AudioFileClip

    with AudioFileClip(path) as clip:
        return float(clip.duration)


def probe_frame_count(path) -> int:
    """Cuadros de video reales (cuenta paquetes: rápido y exacto en CFR)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out.split(",")[0])


def default_dialogues_dir(episode_audio) -> Path:
    """Convención de narrator.generate_script_audio: <audio>.mp3 → <audio>_dialogues/."""
    p = Path(episode_audio)
    return p.parent / f"{p.stem}_dialogues"


def scene_key(scene: Scene, index: int) -> str:
    """Id de la escena (models.Scene.id ahora es opcional): escena_NN si falta."""
    return str(scene.id) if scene.id not in (None, "") else f"escena_{index + 1:02d}"


def scene_number(scene: Scene, index: int) -> int:
    """'escena_07' → 7, '7' → 7, 'ESCENA-07-A' → 7; sin número → posición + 1."""
    nums = re.findall(r"\d+", str(scene.id or ""))
    return int(nums[0]) if nums else index + 1


def find_scene_audio(scene_id: str, dialogues_dir) -> Optional[Path]:
    """
    Busca el audio consolidado de una escena:
      <dir>/<id>/<id>_consolidated.mp3   (narrator.py multi-voz)
      <dir>/<id>_consolidated.mp3
      <dir>/**/<id>_consolidated.*       (cualquier extensión de audio)
    """
    if not dialogues_dir:
        return None
    root = Path(dialogues_dir)
    stem = f"{scene_id}{CONSOLIDATED_SUFFIX}"
    for ext in AUDIO_EXTENSIONS:
        for cand in (root / scene_id / f"{stem}{ext}", root / f"{stem}{ext}"):
            if cand.is_file() and cand.stat().st_size > 0:
                return cand
    if root.is_dir():
        for cand in sorted(root.rglob(f"{stem}.*")):
            if cand.suffix.lower() in AUDIO_EXTENSIONS and cand.stat().st_size > 0:
                return cand
    return None


def find_turn_audios(scene_audio: Path) -> List[Path]:
    """Turnos individuales (turn_01_Detective.mp3, ...) junto al consolidado."""
    folder = scene_audio.parent
    turns = [p for p in folder.glob("turn_*") if p.suffix.lower() in AUDIO_EXTENSIONS]
    return sorted(turns, key=lambda p: p.name)


# -- Reparto de cuadros -----------------------------------------------------

def frames_for_durations(durations: Sequence[float], fps: int,
                         total_frames: Optional[int] = None) -> List[int]:
    """
    Convierte duraciones (s) a cuadros enteros sin acumular error: los cortes
    se redondean sobre el tiempo ACUMULADO, así la suma es exactamente
    round(sum(durations) × fps). Con total_frames, las duraciones se escalan
    para que sumen justo ese número de cuadros (empatar con el audio total).
    Cada elemento recibe al menos 1 cuadro.
    """
    durs = [max(0.0, float(d)) for d in durations]
    if not durs:
        return []
    total_s = sum(durs)
    target = int(total_frames) if total_frames is not None else int(round(total_s * fps))
    target = max(target, len(durs))
    if total_s <= 0:
        durs = [1.0] * len(durs)
        total_s = float(len(durs))
    # Sin total explícito: cuadros = tiempo × fps. Con total: se escala al total.
    scale = (target / total_s) if total_frames is not None else float(fps)
    frames: List[int] = []
    acc, prev = 0.0, 0
    for i, d in enumerate(durs):
        acc += d
        cut = target if i == len(durs) - 1 else int(round(acc * scale))
        # al menos 1 cuadro y dejando 1 para cada elemento que falta
        cut = max(cut, prev + 1)
        cut = min(cut, target - (len(durs) - 1 - i))
        frames.append(cut - prev)
        prev = cut
    return frames


def split_scene_frames(total_frames: int, n_images: int, fps: int,
                       turn_durations: Optional[Sequence[float]] = None,
                       snap_fraction: float = TURN_SNAP_FRACTION) -> List[int]:
    """
    Reparte los cuadros de una escena entre sus imágenes.

    - Reparto base: partes iguales (los cuadros sobrantes van a las primeras).
    - Si se conocen los turnos de diálogo, cada corte ideal se mueve al cambio
      de turno más cercano cuando está a menos de `snap_fraction` de un tramo,
      para que la imagen cambie cuando cambia quien habla. Ninguna imagen
      queda por debajo de MIN_IMAGE_SECONDS (si la escena alcanza).
    La suma SIEMPRE es total_frames.
    """
    n = int(n_images)
    total = int(total_frames)
    if n <= 0:
        return []
    if n == 1 or total <= n:
        base = [total // n] * n
        for i in range(total - sum(base)):
            base[i] += 1
        return base

    ideal = [round(total * k / n) for k in range(1, n)]
    cuts = list(ideal)
    if turn_durations and len(turn_durations) > 1:
        tsum = float(sum(turn_durations))
        if tsum > 0:
            bounds, acc = [], 0.0
            for d in turn_durations[:-1]:
                acc += float(d)
                bounds.append(int(round(acc / tsum * total)))
            seg = total / float(n)
            min_frames = min(int(round(MIN_IMAGE_SECONDS * fps)), int(seg // 2))
            prev = 0
            for k, c in enumerate(ideal):
                nxt_limit = total - (n - 1 - k) * max(min_frames, 1)
                best = None
                for b in bounds:
                    if abs(b - c) <= snap_fraction * seg and b - prev >= max(min_frames, 1) \
                            and b <= nxt_limit and (best is None or abs(b - c) < abs(best - c)):
                        best = b
                cuts[k] = best if best is not None else max(c, prev + 1)
                prev = cuts[k]
    out, prev = [], 0
    for c in cuts + [total]:
        out.append(c - prev)
        prev = c
    return out


# -- Plan de sincronización -------------------------------------------------

def resolve_scene_images(scene: Scene, index: int, images_root=None) -> List[str]:
    """
    Imágenes de la escena: las de image_paths del YAML (si existen) o, si el
    guion no las trae (GUION-02.yaml multi-voz), la carpeta de images_root
    cuyo número coincide con el de la escena: escena_07 → ESCENA-07/.
    """
    listed = [p for p in (scene.image_paths or []) if p]
    if listed:
        return listed
    if not images_root or not Path(images_root).is_dir():
        return []
    num = scene_number(scene, index)
    root = Path(images_root)
    for folder in sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name.lower()):
        nums = re.findall(r"\d+", folder.name)
        if nums and int(nums[0]) == num and not folder.name.lower().startswith(("animated", "manim")):
            imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
            return [str(p) for p in sorted(imgs, key=lambda p: _natural_key(p.name))]
    return []


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def default_images_root(script_path) -> Optional[Path]:
    """assets/source_scripts/GUION-02.yaml → assets/source_scripts/GUION-02/ (si existe)."""
    if not script_path:
        return None
    p = Path(script_path)
    for cand in (p.parent / p.stem, p.parent):
        if cand.is_dir() and any(d.is_dir() and re.search(r"\d", d.name) for d in cand.iterdir()):
            return cand
    return None


@dataclass
class SceneTiming:
    scene_id: str
    title: str
    audio_path: Optional[str]
    audio_seconds: float          # lo que mide su _consolidated.mp3
    frames: int                   # cuadros asignados en el video base
    image_paths: List[str]
    image_frames: List[int]
    source: str                   # "audio" | "yaml" (sin audio, se usó duration)
    turns: int = 0

    def seconds(self, fps: int) -> float:
        return self.frames / float(fps)


@dataclass
class AudioSyncPlan:
    fps: int
    scenes: List[SceneTiming]
    episode_audio: Optional[str] = None
    episode_seconds: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.scenes)

    @property
    def total_seconds(self) -> float:
        return self.total_frames / float(self.fps)

    def table(self) -> str:
        lines = [f"{'escena':<14}{'audio':>10}{'video':>10}  imágenes (s)"]
        for s in self.scenes:
            imgs = ", ".join(f"{f / self.fps:.2f}" for f in s.image_frames) or "—"
            audio = f"{s.audio_seconds:9.2f}s" if s.source == "audio" else "   (yaml)"
            lines.append(f"{s.scene_id:<14}{audio}{s.seconds(self.fps):9.2f}s  [{imgs}]")
        lines.append(f"{'TOTAL':<14}{'':>10}{self.total_seconds:9.2f}s  = {fmt_hms(self.total_seconds)}"
                     f" ({self.total_frames} cuadros @ {self.fps} fps)")
        if self.episode_seconds is not None:
            lines.append(f"Audio del episodio: {fmt_hms(self.episode_seconds)} "
                         f"({self.episode_seconds:.3f}s) → diferencia "
                         f"{self.total_seconds - self.episode_seconds:+.3f}s")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_frames"] = self.total_frames
        d["total_seconds"] = self.total_seconds
        return d


def fmt_hms(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(seconds, 60.0)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:06.3f}" if h else f"{m}:{s:06.3f}"


def plan_audio_sync(script: ScriptDefinition, fps: int, *,
                    dialogues_dir=None, episode_audio=None, images_root=None,
                    strict: bool = True, cut_mode: str = "turns") -> AudioSyncPlan:
    """
    Calcula la línea de tiempo del video base a partir del audio real.

    1. Duración de cada escena = su <id>_consolidated.mp3 (dialogues_dir; si
       no se da, el que sale de episode_audio por la convención de narrator).
       Sin audio: strict → AudioSyncError; si no, se usa scene.duration.
    2. Si hay audio del episodio, el total se ajusta a él: el reencodado MP3
       de la concatenación mueve unas decenas de ms por escena y así el video
       base dura exactamente lo mismo que la pista final.
    3. Cuadros por imagen con split_scene_frames (cut_mode "turns" usa los
       turn_*.mp3 para cortar en los cambios de voz; "equal" = partes iguales).
    """
    fps = int(fps)
    if fps <= 0:
        raise ValueError("fps debe ser > 0")
    if dialogues_dir is None and episode_audio:
        dialogues_dir = default_dialogues_dir(episode_audio)

    warnings: List[str] = []
    rows = []
    missing = []
    for i, scene in enumerate(script.scenes):
        sid = scene_key(scene, i)
        audio = find_scene_audio(sid, dialogues_dir)
        turns: List[float] = []
        if audio is not None:
            secs = probe_duration(audio)
            source = "audio"
            if cut_mode == "turns":
                for t in find_turn_audios(audio):
                    try:
                        turns.append(probe_duration(t))
                    except (OSError, subprocess.SubprocessError, ValueError):
                        turns = []
                        break
        else:
            missing.append(sid)
            secs = float(scene.duration or 0.0)
            source = "yaml"
        rows.append((scene, sid, audio, secs, source, turns))

    if missing:
        msg = (f"{len(missing)} escena(s) sin audio consolidado en {dialogues_dir}: "
               f"{', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")
        if strict:
            raise AudioSyncError(msg + ". Genera el audio con narrator.py o usa strict=False.")
        warnings.append(msg + " → se usa la duración del YAML.")
        log.warning(warnings[-1])

    scene_secs = [r[3] for r in rows]
    episode_secs = None
    total_frames = None
    if episode_audio and Path(episode_audio).is_file():
        episode_secs = probe_duration(episode_audio)
        total_frames = int(round(episode_secs * fps))
        drift = episode_secs - sum(scene_secs)
        if abs(drift) > DRIFT_WARN_SECONDS:
            warnings.append(f"El audio del episodio ({episode_secs:.2f}s) y la suma de escenas "
                            f"({sum(scene_secs):.2f}s) difieren {drift:+.2f}s; se reparte "
                            f"proporcionalmente para empatar con el episodio.")
            log.warning(warnings[-1])
    elif episode_audio:
        warnings.append(f"No existe el audio del episodio {episode_audio}; se usa la suma de escenas.")
        log.warning(warnings[-1])

    scene_frames = frames_for_durations(scene_secs, fps, total_frames)
    timings: List[SceneTiming] = []
    for (scene, sid, audio, secs, source, turns), frames in zip(rows, scene_frames):
        images = resolve_scene_images(scene, len(timings), images_root)
        if not images:
            warnings.append(f"{sid}: sin imágenes; el video base usará un fondo negro.")
            log.warning(warnings[-1])
        img_frames = split_scene_frames(frames, max(len(images), 1), fps,
                                        turn_durations=turns if cut_mode == "turns" else None)
        timings.append(SceneTiming(
            scene_id=sid, title=scene.title, audio_path=str(audio) if audio else None,
            audio_seconds=secs, frames=frames, image_paths=images,
            image_frames=img_frames if images else img_frames[:1], source=source,
            turns=len(turns),
        ))
    return AudioSyncPlan(fps=fps, scenes=timings,
                         episode_audio=str(episode_audio) if episode_audio else None,
                         episode_seconds=episode_secs, warnings=warnings)


def apply_audio_sync(script: ScriptDefinition, plan: AudioSyncPlan) -> ScriptDefinition:
    """
    Copia del guion con duration = cuadros/fps del plan e image_paths
    resueltos, para que render_video() (overlays, escenas Manim) también
    respete el audio. Las escenas Manim sin imágenes conservan render_type.
    """
    new_scenes = []
    for scene, t in zip(script.scenes, plan.scenes):
        update = {"duration": t.seconds(plan.fps)}
        if not scene.image_paths and t.image_paths:
            update["image_paths"] = list(t.image_paths)
        new_scenes.append(scene.model_copy(update=update))
    return script.model_copy(update={"scenes": new_scenes})


# -- Render del video base --------------------------------------------------

def _clip_key(image: str, frames: int, zoom_in: bool, res: Tuple[int, int], fps: int,
              profile: RenderProfile, ken_burns: bool) -> str:
    import hashlib

    try:
        st = os.stat(image)
        stamp = [st.st_size, int(st.st_mtime)]
    except OSError:
        stamp = [None, None]
    payload = [os.path.abspath(image), stamp, frames, zoom_in, list(res), fps,
               profile.x264_preset, profile.crf, ken_burns, 2]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]


def _render_still_clip(image: Optional[str], out: Path, frames: int, res: Tuple[int, int],
                       fps: int, profile: RenderProfile, zoom_in: bool, ken_burns: bool) -> None:
    """Un tramo del video base: Ken Burns (simple_animator) o imagen fija / negro."""
    w, h = res
    if image and ken_burns:
        from .simple_animator import create_ken_burns_clip

        ok = create_ken_burns_clip(Path(image), out, is_even_scene=zoom_in, fps=fps,
                                   width=w, height=h, encode_args=profile.x264_args(),
                                   frames=frames)
        if not ok:
            raise RuntimeError(f"FFmpeg no pudo animar {image}")
        return
    if image:
        src = ["-loop", "1", "-framerate", str(fps), "-i", str(image)]
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}"
    else:
        src = ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}"]
        vf = "setsar=1"
    cmd = ["ffmpeg", "-y", "-v", "error", *src, "-vf", vf, "-c:v", "libx264",
           "-pix_fmt", "yuv420p", *profile.x264_args(), "-r", str(fps),
           "-frames:v", str(frames), "-an", str(out)]
    res_ = subprocess.run(cmd, capture_output=True, text=True)
    if res_.returncode != 0:
        raise RuntimeError(f"FFmpeg falló creando {out.name}:\n{res_.stderr[-800:]}")


def _resolve_jobs(jobs: Optional[int], profile: RenderProfile) -> int:
    if jobs is None:
        env = os.environ.get("VA_JOBS", "").strip()
        if env.isdigit():
            jobs = int(env)
        elif profile.low_priority:
            jobs = 1
        else:
            jobs = min(4, max(1, (os.cpu_count() or 2) // 2))
    return max(1, int(jobs))


def _concat_copy(parts: Sequence[Path], output: Path) -> None:
    lst = output.with_suffix(".concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '{}'\n".format(str(Path(p).resolve()).replace("'", "'\\''")))
    try:
        res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                              "-i", str(lst), "-c", "copy", "-movflags", "+faststart",
                              str(output)], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg concat falló:\n{res.stderr[-800:]}")
    finally:
        lst.unlink(missing_ok=True)


def render_audio_synced_base(script: ScriptDefinition, output_path, *,
                             episode_audio=None, dialogues_dir=None, images_root=None,
                             profile: Optional[RenderProfile] = None,
                             resolution: Optional[Sequence[int]] = None,
                             fps: Optional[int] = None, ken_burns: bool = True,
                             strict: bool = True, cut_mode: str = "turns",
                             mux_audio: bool = False, use_cache: bool = True,
                             plan: Optional[AudioSyncPlan] = None,
                             jobs: Optional[int] = None) -> Path:
    """
    Video base del episodio que dura EXACTAMENTE lo que su audio multi-voz.

    - Escenas solo-imágenes (caso GUION-02): un clip FFmpeg por imagen con su
      número exacto de cuadros (Ken Burns alternando zoom in/out, o imagen
      fija con ken_burns=False) y concatenación sin recodificar. Los clips
      se guardan en <salida>/base_clips[_fast]/ con caché por imagen+cuadros.
    - Si alguna escena trae overlay o render_type "manim", se usa
      render_video() con las duraciones del audio (apply_audio_sync).

    Escribe además <salida>.sync.json con la línea de tiempo (para revisar o
    para que subtítulos/miniaturas usen los mismos tiempos).
    mux_audio=True deja la pista del episodio dentro del .mp4 (AAC).
    jobs: clips FFmpeg en paralelo (None → $VA_JOBS, o 1 en perfiles de baja
    prioridad y hasta 4 en producción). Zoompan usa ~1 núcleo por clip.
    Devuelve la ruta del video.
    """
    profile = profile or default_profile()
    res, out_fps = resolve_output_format(script, profile, resolution, fps)
    output_path = profile.tag_path(Path(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if plan is None or plan.fps != out_fps:
        plan = plan_audio_sync(script, out_fps, dialogues_dir=dialogues_dir,
                               episode_audio=episode_audio, images_root=images_root,
                               strict=strict, cut_mode=cut_mode)
    print(f"⚙️  {profile.summary(res, out_fps)}")
    print("🎧 Línea de tiempo sincronizada con el audio:\n" + plan.table())

    needs_moviepy = any(s.manim_overlay or s.render_type == "manim" for s in script.scenes)
    if needs_moviepy:
        # render_video vuelve a poner el sufijo del perfil: le pasamos el nombre sin él.
        plain = output_path.name
        if profile.suffix and output_path.stem.endswith(profile.suffix):
            plain = output_path.stem[: -len(profile.suffix)] + output_path.suffix
        synced = apply_audio_sync(script, plan).model_copy(
            update={"output_filename": plain, "audio_path": None, "subtitle_path": None})
        render_video(synced, str(output_path.parent), profile=profile,
                     resolution=resolution, fps=fps, use_cache=use_cache)
    else:
        clips_dir = profile.tag_dir(output_path.parent / "base_clips")
        clips_dir.mkdir(parents=True, exist_ok=True)
        parts: List[Path] = []
        todo = []
        k = 0
        for s in plan.scenes:
            images: List[Optional[str]] = list(s.image_paths) or [None]
            for img, frames in zip(images, s.image_frames):
                zoom_in = (k % 2 == 0)
                key = _clip_key(img or "black", frames, zoom_in, res, out_fps, profile, ken_burns)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", s.scene_id)
                out = clips_dir / f"{k:03d}_{safe}_{key}.mp4"
                k += 1
                parts.append(out)
                if not (use_cache and out.is_file() and out.stat().st_size > 0):
                    todo.append((k, s.scene_id, img, frames, zoom_in, out))
        if len(todo) < len(parts):
            print(f"♻️  {len(parts) - len(todo)} clip(s) en caché en {clips_dir}")

        def _one(item):
            n, sid, img, frames, zoom_in, out = item
            print(f"🎞️  [{n}/{len(parts)}] {sid}: {Path(img).name if img else 'negro'} "
                  f"→ {frames} cuadros ({frames / out_fps:.2f}s)", flush=True)
            tmp = out.with_name(out.stem + ".part.mp4")
            _render_still_clip(img, tmp, frames, res, out_fps, profile, zoom_in, ken_burns)
            os.replace(tmp, out)

        n_jobs = _resolve_jobs(jobs, profile)
        if n_jobs > 1 and len(todo) > 1:
            from concurrent.futures import ThreadPoolExecutor

            print(f"⚡ {len(todo)} clips en paralelo ({n_jobs} a la vez)")
            with ThreadPoolExecutor(max_workers=n_jobs) as pool:
                list(pool.map(_one, todo))
        else:
            for item in todo:
                _one(item)
        silent = output_path if not mux_audio else output_path.with_name(output_path.stem + ".video.mp4")
        _concat_copy(parts, silent)
        if mux_audio and plan.episode_audio:
            res_ = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent),
                                   "-i", str(plan.episode_audio), "-map", "0:v:0", "-map", "1:a:0",
                                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                   "-movflags", "+faststart", str(output_path)],
                                  capture_output=True, text=True)
            if res_.returncode != 0:
                raise RuntimeError(f"FFmpeg no pudo unir el audio:\n{res_.stderr[-800:]}")
            silent.unlink(missing_ok=True)

    # Verificación: cuadros reales del archivo vs. plan.
    try:
        real = probe_frame_count(output_path)
        if real != plan.total_frames:
            msg = (f"El video base tiene {real} cuadros y el plan {plan.total_frames} "
                   f"({(real - plan.total_frames) / out_fps:+.3f}s).")
            plan.warnings.append(msg)
            log.warning(msg)
        else:
            print(f"✅ Video base: {real} cuadros = {fmt_hms(real / out_fps)} "
                  f"(audio {fmt_hms(plan.episode_seconds) if plan.episode_seconds else 'n/d'})")
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as exc:
        log.warning("No se pudo verificar el número de cuadros: %s", exc)

    report = output_path.with_suffix(".sync.json")
    report.write_text(json.dumps({**plan.to_dict(), "video": str(output_path),
                                  "resolution": list(res)}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"📝 Línea de tiempo guardada en: {report}")
    return output_path
