import os
import subprocess
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip

from .render_profiles import RenderProfile, default_profile


def build_image_clip(image_path: str, duration: float, resolution: tuple = (1920, 1080)):
    """
    Construye un único ImageClip ya redimensionado a la resolución de salida.
    Lo usan las escenas de tipo "images" (flujo original) desde heavy_render.py.
    """
    if not os.path.exists(image_path):
        print(f"Advertencia: No se encontró la imagen {image_path}")
        return None
    return ImageClip(image_path).with_duration(duration).resized(new_size=resolution)


#: Segundos que se le quitan al final de cada clip (salvo el último) al concatenar.
BOUNDARY_EPS = 1e-6


def _separate_boundaries(clips: list) -> list:
    """
    MoviePy decide qué clip suena en `t` con `start <= t < end` en flotantes.
    Cuando un corte cae justo en la rejilla de cuadros (t = k/fps, lo normal
    con clips Manim de cuadros exactos), el error de redondeo hace que a veces
    se pida al clip que termina un cuadro más allá de su último cuadro
    ("bytes wanted but 0 bytes read ... Using the last valid frame").
    Recortar 1 µs a cada clip (excepto el último) deja el corte del lado del
    clip siguiente sin cambiar el número de cuadros del video final.
    """
    out = []
    for i, clip in enumerate(clips):
        last = i == len(clips) - 1
        if not last and clip.duration and clip.duration > BOUNDARY_EPS:
            clip = clip.with_duration(clip.duration - BOUNDARY_EPS)
        out.append(clip)
    return out


def lazy_video_clip(path: str, duration: float, fps: int):
    """
    VideoClip que abre el archivo SOLO mientras se están leyendo sus cuadros.

    Cada VideoFileClip de MoviePy arranca un proceso ffmpeg lector al crearse
    y lo deja vivo hasta el final: a 1080p son ~220 MB por clip, así que un
    episodio con 17 escenas Manim/overlay pasaría de 3.5 GB solo en lectores.
    Este clip abre el lector al pedir su primer cuadro y lo cierra en el
    último, de modo que al exportar solo hay uno o dos lectores vivos.
    La duración es la de sus cuadros exactos: round(duration × fps) / fps.
    """
    from moviepy import VideoClip, VideoFileClip

    frames = max(1, int(round(float(duration) * fps)))
    exact = frames / float(fps)
    last_t = (frames - 1) / float(fps)
    state = {"clip": None}

    def _open():
        if state["clip"] is None:
            state["clip"] = VideoFileClip(str(path), audio=False)
        return state["clip"]

    def frame_function(t):
        clip = _open()
        frame = clip.get_frame(min(float(t), last_t))
        if t >= last_t - 0.5 / fps:          # último cuadro: se libera el lector
            clip.close()
            state["clip"] = None
        return frame

    probe = VideoFileClip(str(path), audio=False)
    size = tuple(probe.size)
    probe.close()
    # Sin frame_function en el constructor: VideoClip pediría el cuadro 0 (y
    # abriría el lector) solo para conocer el tamaño, que ya sabemos.
    clip = VideoClip(duration=exact)
    clip.frame_function = frame_function
    clip.size = size
    clip.fps = fps
    return clip


def overlay_scene_ffmpeg(image_paths: list, durations: list, overlay_path: str, output_path: str,
                         fps: int, resolution: tuple, profile: RenderProfile = None) -> str:
    """
    Compone UNA escena "imágenes + overlay Manim con alfa" directamente con
    FFmpeg (filtros overlay/concat en C, multihilo) y la deja en un .mp4
    H.264 con cuadros exactos: round(suma(durations) × fps).

    Por qué no MoviePy: CompositeVideoClip mezcla cada cuadro en Python y deja
    abiertos los lectores del .mov con alfa (dos procesos ffmpeg por overlay,
    ~400 MB cada uno a 1080p) hasta el final del video. En el Episodio 3 a
    1080p eso eran 15 min y 3.7 GB de RAM; así cada escena se compone y se
    cierra antes de pasar a la siguiente.

    - Imagen faltante → tramo negro de la misma duración (se conserva el tiempo).
    - Las imágenes se estiran a `resolution`, igual que build_image_clip().
    - Intermedio de alta calidad (crf del perfil - 6): el video final se
      vuelve a codificar en compose_clips().
    """
    profile = profile or default_profile()
    w, h = int(resolution[0]), int(resolution[1])
    if len(image_paths) != len(durations) or not image_paths:
        raise ValueError("overlay_scene_ffmpeg: una duración por imagen (al menos una imagen)")

    # Cuadros por imagen con fronteras acumuladas redondeadas (la suma cuadra).
    frames, acc, prev = [], 0.0, 0
    for d in durations:
        acc += float(d)
        edge = int(round(acc * fps))
        frames.append(edge - prev)
        prev = edge
    total = sum(frames)

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    chains, labels = [], []
    k = 0
    for img, n in zip(image_paths, frames):
        if n <= 0:
            continue
        if os.path.exists(img):
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(img)]
            src = f"[{k}:v]scale={w}:{h},setsar=1,format=yuv420p,"
        else:
            print(f"Advertencia: No se encontró la imagen {img} (tramo negro)")
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}"]
            src = f"[{k}:v]format=yuv420p,"
        chains.append(f"{src}fps={fps},trim=end_frame={n},setpts=PTS-STARTPTS[b{k}]")
        labels.append(f"[b{k}]")
        k += 1
    cmd += ["-i", str(overlay_path)]
    base = f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[base]" if len(labels) > 1 else None
    base_label = "[base]" if base else labels[0]
    graph = ";".join(chains + ([base] if base else []) +
                     [f"{base_label}[{k}:v]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]"])
    quality = ["-preset", "veryfast" if profile.is_production else profile.x264_preset,
               "-crf", str(max(0, profile.crf - 6))] + profile.ffmpeg_thread_args()
    cmd += ["-filter_complex", graph, "-map", "[v]", "-frames:v", str(total),
            "-c:v", "libx264", *quality, "-pix_fmt", "yuv420p", "-r", str(fps),
            "-fps_mode", "cfr", "-an", "-movflags", "+faststart", str(output_path)]
    os.makedirs(os.path.dirname(str(output_path)) or ".", exist_ok=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 and "-fps_mode" in cmd:
        i = cmd.index("-fps_mode")      # ffmpeg < 5.1 no conoce -fps_mode
        cmd[i:i + 2] = ["-vsync", "cfr"]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo componer {output_path}:\n{res.stderr[-1500:]}")
    return str(output_path)


def _burn_subtitles(video_path: str, subtitle_path: str, output_path: str,
                    profile: RenderProfile = None) -> None:
    """
    Quema (hardcodea) un archivo .srt directamente sobre el video usando el
    filtro 'subtitles' de FFmpeg. MoviePy no hace esto bien de forma nativa,
    por eso se delega al binario de FFmpeg instalado en el Dockerfile.
    """
    print(f"Quemando subtítulos desde: {subtitle_path}")

    # FFmpeg es quisquilloso con las rutas en el filtro subtitles en Windows/rutas
    # con caracteres especiales; escapamos los dos puntos por seguridad.
    safe_subtitle_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{safe_subtitle_path}'",
        "-c:v", "libx264", *(profile or default_profile()).x264_args(), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"❌ Error al quemar subtítulos con FFmpeg:\n{result.stderr}")


def compose_clips(
    clips: list,
    output_path: str,
    audio_path: str = None,
    subtitle_path: str = None,
    fps: int = 30,
    resolution: tuple = (1920, 1080),
    profile: RenderProfile = None,
) -> str:
    """
    Concatena una lista de clips de MoviePy YA CONSTRUIDOS (pueden venir de
    imágenes o de animaciones renderizadas con Manim, mezclados en cualquier
    orden) y exporta el video final, con audio real y subtítulos quemados si
    se proveen. Devuelve la ruta del archivo final.

    `profile` (render_profiles.py) decide preset/CRF/hilos de la exportación;
    sin perfil se usa $VA_QUALITY o "production".
    """
    profile = profile or default_profile()
    write_kwargs = profile.moviepy_write_kwargs()
    clips = [c for c in clips if c is not None]
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    print(f"Ensamblando video final con {len(clips)} clip(s)...")
    # Cuadros del video = round(suma de duraciones × fps): mismo criterio de
    # cuadros exactos que manim_timing. El +ε evita que int(dur*fps) de MoviePy
    # pierda el último cuadro por redondeo de flotantes.
    total_frames = int(round(sum(float(c.duration) for c in clips) * fps))
    final_video = concatenate_videoclips(_separate_boundaries(clips), method="compose")
    final_video = final_video.with_duration(total_frames / float(fps) + BOUNDARY_EPS / 10)

    # --- Audio real (si el módulo de TTS ya entregó una pista) ---
    has_audio = bool(audio_path) and os.path.exists(audio_path)
    if audio_path and not has_audio:
        print(f"⚠️ Advertencia: no se encontró el audio {audio_path}, se exporta sin audio.")

    if has_audio:
        audio_clip = AudioFileClip(audio_path)
        # Si el audio es más largo/corto que el video, lo recortamos a la
        # duración del video para no desincronizar.
        if audio_clip.duration > final_video.duration:
            audio_clip = audio_clip.subclipped(0, final_video.duration)
        final_video = final_video.with_audio(audio_clip)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    has_subtitles = bool(subtitle_path) and os.path.exists(subtitle_path)
    if subtitle_path and not has_subtitles:
        print(f"⚠️ Advertencia: no se encontró el .srt {subtitle_path}, se exporta sin subtítulos.")

    if has_subtitles:
        # Primero exportamos un intermedio sin subtítulos, luego lo quemamos con FFmpeg.
        temp_path = output_path.replace(".mp4", "_temp.mp4")
        # El intermedio se re-encoda al quemar: va con el preset más rápido.
        temp_kwargs = {**write_kwargs, "preset": "ultrafast"}
        final_video.write_videofile(temp_path, fps=fps, **temp_kwargs)
        _burn_subtitles(temp_path, subtitle_path, output_path, profile=profile)
        os.remove(temp_path)
    else:
        final_video.write_videofile(output_path, fps=fps, **write_kwargs)

    print(f"✅ Video final exportado en: {output_path}")
    return output_path


def compose_video(
    image_paths: list,
    durations: list,
    output_path: str,
    audio_path: str = None,
    subtitle_path: str = None,
    fps: int = 30,
    resolution: tuple = (1920, 1080),
    profile: RenderProfile = None,
) -> str:
    """
    Compatibilidad hacia atrás: arma clips a partir de una lista de imágenes
    y duraciones (el flujo original, pre-Manim) y delega en compose_clips().
    """
    clips = [build_image_clip(img, dur, resolution) for img, dur in zip(image_paths, durations)]
    return compose_clips(
        clips, output_path,
        audio_path=audio_path, subtitle_path=subtitle_path,
        fps=fps, resolution=resolution, profile=profile,
    )
