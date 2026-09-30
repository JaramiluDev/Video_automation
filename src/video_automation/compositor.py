import os
from pathlib import Path

from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, ImageClip, concatenate_videoclips


def build_image_clip(image_path: str, duration: float, resolution: tuple[int, int] = (1920, 1080)):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"No se encontró la imagen: {image_path}")

    clip = ImageClip(image_path).with_duration(duration)
    return clip.resized(resolution)


def compose_clips(clips, output_path: str, audio_path: str | None = None, subtitle_path: str | None = None, fps: int = 30, resolution: tuple[int, int] = (1920, 1080)) -> str:
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    final_video = concatenate_videoclips(clips, method="compose")

    if audio_path and os.path.exists(audio_path):
        final_video = final_video.with_audio(AudioFileClip(audio_path))

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(str(output_file), fps=fps, codec="libx264")
    return str(output_file)


def compose_video(image_paths: list, durations: list, output_path: str, fps: int = 30, resolution: str = "1920x1080") -> str:
    print(f"Ensamblando video con {len(image_paths)} imágenes...")
    clips = []

    width, height = (int(value) for value in resolution.split("x"))

    for img, dur in zip(image_paths, durations):
        if os.path.exists(img):
            clip = ImageClip(img).resized((width, height)).with_duration(dur)
            clips.append(clip)
        else:
            print(f"Advertencia: No se encontró la imagen {img}")

    if not clips:
        raise ValueError("No se generaron clips válidos.")

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_path, fps=fps)
    return output_path

