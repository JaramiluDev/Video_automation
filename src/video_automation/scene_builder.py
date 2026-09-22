from pathlib import Path
from typing import List

def get_scene_images(scene_path: str) -> List[str]:
    """
    Lee una carpeta, busca imágenes (.png, .jpg) y las ordena alfabéticamente.
    Ideal para secuencias de video.
    """
    folder = Path(scene_path)
    
    # Validar si existe y es carpeta
    if not folder.exists() or not folder.is_dir():
        print(f"⚠️ Error: No se encontró la carpeta {scene_path}")
        return []

    images = []
    valid_exts = {'.png', '.jpg', '.jpeg'}
    
    # Recorrer archivos y filtrar por extensión
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in valid_exts:
            images.append(str(file.absolute()))
            
    # Ordenar alfabéticamente para mantener la animación fluida
    images.sort()
    return images