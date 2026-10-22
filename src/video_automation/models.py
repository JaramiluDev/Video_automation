from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Optional

class Dialogue(BaseModel):
    character: str
    voice_model: str
    text: str

from pydantic import BaseModel, model_validator


class Scene(BaseModel):
    id: Optional[str] = None
    title: str
    dialogues: Optional[List[Dialogue]] = []
    dialogue: Optional[List[Dialogue]] = []
    narration: Optional[str] = ""
    image_paths: Optional[List[str]] = []
    duration: Optional[float] = 5.0
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
    # Solo para render_type="manim": nombre de una clase registrada en
    # scenes_video2.SCENE_REGISTRY (ej. "V2E02_ProductosCruzados"). Si se da,
    # tiene prioridad sobre `formula`. La duración del clip = `duration`.
    manim_scene: Optional[str] = None
    # Parámetros opcionales para esa clase (ej. {"a": "2/4", "b": "4/8"}).
    manim_params: Optional[Dict[str, Any]] = None
    # Solo para render_type="images": overlay Manim con transparencia que se
    # incrusta SOBRE las imágenes de la escena (clase de
    # animations.math_scenes.SCENE_REGISTRY, ej. "FormulaOverlay" o
    # "Scene02Math"). Cada imagen es un tramo del overlay, así que el
    # contenido cambia en el mismo cuadro que la imagen.
    manim_overlay: Optional[str] = None
    manim_overlay_params: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def sync_dialogue_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            dialogue = data.get("dialogue")
            dialogues = data.get("dialogues")
            if dialogue is not None and dialogues is None:
                data["dialogues"] = dialogue
            elif dialogues is not None and dialogue is None:
                data["dialogue"] = dialogues
        return data

    @model_validator(mode="before")
    @classmethod
    def normalize_narration_fields(cls, data):
        if isinstance(data, dict):
            if data.get("narration") in (None, ""):
                if data.get("dialogue") is not None:
                    data["narration"] = data["dialogue"]
                elif data.get("text") is not None:
                    data["narration"] = data["text"]
        return data

class OutputSettings(BaseModel):
    resolution: tuple = (1920, 1080)
    fps: int = 30

class ScriptDefinition(BaseModel):
    title: Optional[str] = None
    scenes: List[Scene]
    output_filename: Optional[str] = None
    # Audio ya mezclado de todas las escenas (lo produce el módulo de TTS de Richi).
    # Opcional por ahora para no romper guiones existentes sin audio real.
    audio_path: Optional[str] = None
    # .srt ya generado (lo produce subtitles.py). Si se da, se queman en el video.
    subtitle_path: Optional[str] = None
    output_settings: Optional[OutputSettings] = None
