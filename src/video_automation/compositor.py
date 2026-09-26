import os

from moviepy import ImageClip, concatenate_videoclips


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

