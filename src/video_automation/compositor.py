import os
from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips


def _normalize_resolution(resolution):
    if isinstance(resolution, str):
        try:
            width, height = [int(part.strip()) for part in resolution.lower().split("x")]
            return (width, height)
        except ValueError as exc:
            raise ValueError(f"Resolución inválida: {resolution!r}. Usa el formato '1280x720'.") from exc
    if isinstance(resolution, (list, tuple)) and len(resolution) == 2:
        return (int(resolution[0]), int(resolution[1]))
    raise TypeError(f"Tipo de resolución no soportado: {type(resolution).__name__}")


def build_image_clip(image_path: str, duration: float, resolution: tuple[int, int] = (1920, 1080)):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"No se encontró la imagen: {image_path}")

    clip = ImageClip(image_path).with_duration(duration)
    return clip.resized(resolution)


def compose_clips(clips, output_path: str, audio_path: str | None = None, subtitle_path: str | None = None, fps: int = 30, resolution: tuple[int, int] | str = (1920, 1080)) -> str:
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    normalized_resolution = _normalize_resolution(resolution)
    final_video = concatenate_videoclips(clips, method="compose")

    if audio_path and os.path.exists(audio_path):
        final_video = final_video.with_audio(AudioFileClip(audio_path))

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(str(output_file), fps=fps, codec="libx264")
    return str(output_file)


def compose_video(images_or_clips, durations_or_clips, output_path: str, audio_path: str | None = None, subtitle_path: str | None = None, fps: int = 30, resolution: tuple[int, int] | str = (1920, 1080)) -> str:
    """Compatibilidad con el pipeline y con la API pública esperada por el proyecto.

    Acepta dos formas:
    - una lista de clips ya creados
    - una lista de rutas de imagen + una lista de duraciones
    """
    normalized_resolution = _normalize_resolution(resolution)

    if images_or_clips and isinstance(images_or_clips[0], str):
        if not isinstance(durations_or_clips, (list, tuple)):
            raise TypeError("Cuando se pasan rutas de imagen, se requiere una lista de duraciones.")
        clips = [build_image_clip(img, duration, normalized_resolution) for img, duration in zip(images_or_clips, durations_or_clips)]
    else:
        clips = list(images_or_clips)

    return compose_clips(
        clips,
        output_path,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        fps=fps,
        resolution=normalized_resolution,
    )

