import yaml
from pathlib import Path
from .models import ScriptDefinition

def parse_script(file_path: str) -> ScriptDefinition:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return ScriptDefinition(**data)
