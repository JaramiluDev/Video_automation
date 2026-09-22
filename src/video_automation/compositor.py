import os
from moviepy import ImageClip, concatenate_videoclips

def compose_video(image_paths: list, durations: list, output_path: str):
    print(f"Ensamblando video con {len(image_paths)} imágenes...")
    clips = []
    for img, dur in zip(image_paths, durations):
        if os.path.exists(img):
            clip = ImageClip(img).set_duration(dur)
            clips.append(clip)
        else:
            print(f"Advertencia: No se encontró la imagen {img}")
    
    if not clips:
        raise ValueError("No se generaron clips válidos.")

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_path, fps=30)
