import os
import subprocess
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip


def build_image_clip(image_path: str, duration: float, resolution: tuple = (1920, 1080)):
    """
    Construye un único ImageClip ya redimensionado a la resolución de salida.
    Lo usan las escenas de tipo "images" (flujo original) desde heavy_render.py.
    """
    if not os.path.exists(image_path):
        print(f"Advertencia: No se encontró la imagen {image_path}")
        return None
    return ImageClip(image_path).with_duration(duration).resized(new_size=resolution)


def _burn_subtitles(video_path: str, subtitle_path: str, output_path: str) -> None:
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
) -> str:
    """
    Concatena una lista de clips de MoviePy YA CONSTRUIDOS (pueden venir de
    imágenes o de animaciones renderizadas con Manim, mezclados en cualquier
    orden) y exporta el video final, con audio real y subtítulos quemados si
    se proveen. Devuelve la ruta del archivo final.
    """
    clips = [c for c in clips if c is not None]
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    print(f"Ensamblando video final con {len(clips)} clip(s)...")
    final_video = concatenate_videoclips(clips, method="compose")

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
        final_video.write_videofile(temp_path, fps=fps)
        _burn_subtitles(temp_path, subtitle_path, output_path)
        os.remove(temp_path)
    else:
        final_video.write_videofile(output_path, fps=fps)

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
) -> str:
    """
    Compatibilidad hacia atrás: arma clips a partir de una lista de imágenes
    y duraciones (el flujo original, pre-Manim) y delega en compose_clips().
    """
    clips = [build_image_clip(img, dur, resolution) for img, dur in zip(image_paths, durations)]
    return compose_clips(
        clips, output_path,
        audio_path=audio_path, subtitle_path=subtitle_path,
        fps=fps, resolution=resolution,
    )
