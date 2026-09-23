import yaml
from pathlib import Path
from .models import ScriptDefinition

def parse_script(file_path: str) -> ScriptDefinition:
    """
    Parsea un archivo de guión en formato YAML y devuelve un objeto ScriptDefinition.
    """
    # Valida que el archivo exista
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Error: El archivo {file_path} no existe.")

    # Carga el archivo YAML
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Retorna el modelo validado en lugar de un diccionario crudo
    return ScriptDefinition(**data)
    