import os
import subprocess
from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

from .render_profiles import RenderProfile, default_profile


def build_image_clip(image_path: str, duration: float, resolution: tuple[int, int] = (1920, 1080)):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"No se encontró la imagen: {image_path}")

    clip = ImageClip(image_path).with_duration(duration)
    return clip.resized(resolution)


def _burn_subtitles(video_path: str, subtitle_path: str, output_path: str,
                    profile: RenderProfile = None) -> None:
    """
    Quema (hardcodea) un archivo .srt directamente sobre el video usando el
    filtro 'subtitles' de FFmpeg.
    """
    print(f"Quemando subtítulos desde: {subtitle_path}")

    safe_subtitle_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{safe_subtitle_path}'",
<<<<<<< HEAD
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
=======
        "-c:v", "libx264", *(profile or default_profile()).x264_args(), "-pix_fmt", "yuv420p",
>>>>>>> origin/HG
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
<<<<<<< HEAD
    Concatena una lista de clips de MoviePy y exporta el video final,
    con audio real y subtítulos quemados si se proveen.
=======
    Concatena una lista de clips de MoviePy YA CONSTRUIDOS (pueden venir de
    imágenes o de animaciones renderizadas con Manim, mezclados en cualquier
    orden) y exporta el video final, con audio real y subtítulos quemados si
    se proveen. Devuelve la ruta del archivo final.

    `profile` (render_profiles.py) decide preset/CRF/hilos de la exportación;
    sin perfil se usa $VA_QUALITY o "production".
>>>>>>> origin/HG
    """
    profile = profile or default_profile()
    write_kwargs = profile.moviepy_write_kwargs()
    clips = [c for c in clips if c is not None]
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    final_video = concatenate_videoclips(clips, method="compose")

    if audio_path and os.path.exists(audio_path):
        final_video = final_video.with_audio(AudioFileClip(audio_path))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    has_subtitles = bool(subtitle_path) and os.path.exists(subtitle_path)
    if subtitle_path and not has_subtitles:
        print(f"⚠️ Advertencia: no se encontró el .srt {subtitle_path}, se exporta sin subtítulos.")

    video_export_kwargs = {
        "fps": fps,
        "bitrate": "12000k",
        "ffmpeg_params": ["-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p"],
    }

    if has_subtitles:
        temp_path = output_path.replace(".mp4", "_temp.mp4")
<<<<<<< HEAD
        final_video.write_videofile(temp_path, **video_export_kwargs)
        _burn_subtitles(temp_path, subtitle_path, output_path)
        os.remove(temp_path)
    else:
        final_video.write_videofile(output_path, **video_export_kwargs)
=======
        # El intermedio se re-encoda al quemar: va con el preset más rápido.
        temp_kwargs = {**write_kwargs, "preset": "ultrafast"}
        final_video.write_videofile(temp_path, fps=fps, **temp_kwargs)
        _burn_subtitles(temp_path, subtitle_path, output_path, profile=profile)
        os.remove(temp_path)
    else:
        final_video.write_videofile(output_path, fps=fps, **write_kwargs)
>>>>>>> origin/HG

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
    y duraciones y delega en compose_clips().
    """
    clips = [build_image_clip(img, dur, resolution) for img, dur in zip(image_paths, durations)]
    return compose_clips(
        clips, output_path,
        audio_path=audio_path, subtitle_path=subtitle_path,
<<<<<<< HEAD
        fps=fps, resolution=resolution,
    )
=======
        fps=fps, resolution=resolution, profile=profile,
    )
>>>>>>> origin/HG
