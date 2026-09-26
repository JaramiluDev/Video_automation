from pydantic import BaseModel
from typing import List, Optional

class Scene(BaseModel):
    id: str
    title: str
    narration: str
    image_paths: List[str]
    duration: float
    voice: Optional[str] = "default"
    text_on_screen: Optional[str] = ""
    transitions: Optional[str] = "fade"
    # "images" = secuencia de imágenes (flujo actual). "manim" = animación
    # matemática generada por heavy_render.py.
    render_type: Optional[str] = "images"
    # Solo para render_type="manim": expresión LaTeX a animar (sin $ ni \[ \]),
    # ej. "ax^2 + bx + c = 0". Si no se puede renderizar con LaTeX (no
    # instalado), heavy_render.py hace fallback a texto plano.
    formula: Optional[str] = None

class OutputSettings(BaseModel):
    resolution: tuple = (1920, 1080)
    fps: int = 30

class ScriptDefinition(BaseModel):
    title: str
    scenes: List[Scene]
    output_filename: str
    # Audio ya mezclado de todas las escenas (lo produce el módulo de TTS de Richi).
    # Opcional por ahora para no romper guiones existentes sin audio real.
    audio_path: Optional[str] = None
    # .srt ya generado (lo produce subtitles.py). Si se da, se queman en el video.
    subtitle_path: Optional[str] = None
    output_settings: Optional[OutputSettings] = None
