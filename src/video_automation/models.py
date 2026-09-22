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

class ScriptDefinition(BaseModel):
    title: str
    scenes: List[Scene]
    output_filename: str

class OutputSettings(BaseModel):
    resolution: tuple = (1920, 1080)
    fps: int = 30
