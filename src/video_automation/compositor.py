from moviepy import ImageClip, concatenate_videoclips

def build_image_clip(image_path, duration):
    """Construye un clip de imagen con la duración dada."""
    return ImageClip(str(image_path)).set_duration(duration)

def compose_clips(clips):
    """Une una lista de clips de video."""
    return concatenate_videoclips(clips, method="compose")
