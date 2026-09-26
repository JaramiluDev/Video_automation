#!/usr/bin/env python3
"""
Módulo simple_animator: Automatización multimedia con Python y FFmpeg.

Procesa imágenes estáticas (.png, .jpg, .jpeg) y genera clips de video
de 5 segundos a 30fps en resolución 1080p con efecto Ken Burns (Zoom In / Zoom Out
intercalado entre escenas pares e impares).
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES REQUERIDAS
# ==============================================================================
SOURCE_DIR = Path("assets/source_scripts/BUSCANDO-A-LA-X/BUSCANDO-A-LA-X") #TENGAN MUCHO CUIDADO CON LA RUTA DE LA CARPETA POR QUE  SI NO LE PONEMOS BIEN GENERA  ALV MUCHO CUIDADO
OUTPUT_DIR = SOURCE_DIR / "animated_clips"

DURATION_SECONDS = 5
FPS = 30
TOTAL_FRAMES = DURATION_SECONDS * FPS  # 150 cuadros
WIDTH = 1920
HEIGHT = 1080
VIDEO_CODEC = "libx264"
PIXEL_FORMAT = "yuv420p"
VALID_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def get_image_files(source_dir: Path, output_dir: Path) -> List[Path]:
    """
    Busca de forma ordenada todos los archivos de imagen (.png, .jpg, .jpeg).
    
    Verifica primero si hay imágenes directamente en el directorio raíz.
    Si no las hay, busca recursivamente en los subdirectorios, excluyendo
    el directorio de salida 'animated_clips'.
    """
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"❌ Error: La ruta de origen no existe o no es un directorio: {source_dir}")
        return []

    # Búsqueda en el directorio raíz
    direct_images = [
        f for f in source_dir.iterdir()
        if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS
    ]
    if direct_images:
        return sorted(direct_images, key=lambda p: p.name.lower())

    # Si no hay imágenes en la raíz, buscar recursivamente en subdirectorios
    nested_images = [
        f for f in source_dir.rglob("*")
        if f.is_file()
        and f.suffix.lower() in VALID_EXTENSIONS
        and output_dir not in f.parents
        and f.parent != output_dir
    ]
    return sorted(nested_images, key=lambda p: (str(p.parent).lower(), p.name.lower()))


def build_output_path(img_path: Path, source_dir: Path, output_dir: Path) -> Path:
    """
    Genera la ruta de salida para el clip .mp4 correspondiente.
    Si la imagen proviene de un subdirectorio, incluye el prefijo del directorio
    para evitar colisiones de nombres.
    """
    clean_stem = img_path.stem.rstrip(".")
    if img_path.parent == source_dir:
        filename = f"{clean_stem}.mp4"
    else:
        # Prevenir colisiones si distintas carpetas tienen imágenes con el mismo nombre
        folder_prefix = img_path.parent.name.replace(" ", "_")
        filename = f"{folder_prefix}_{clean_stem}.mp4"

    return output_dir / filename


def create_ken_burns_clip(
    image_path: Path,
    output_path: Path,
    is_even_scene: bool,
    duration: int = DURATION_SECONDS,
    fps: int = FPS,
    width: int = WIDTH,
    height: int = HEIGHT
) -> bool:
    """
    Ejecuta FFmpeg mediante subprocess.run para transformar una imagen estática
    en un clip de video con efecto Ken Burns continuo y centrado.
    
    - Escenas pares (is_even_scene = True): Zoom In continuo hacia el centro (1.0 -> 1.25).
    - Escenas impares (is_even_scene = False): Zoom Out continuo desde el centro (1.25 -> 1.0).
    """
    total_frames = duration * fps
    # Incremento/decremento por frame para cubrir de 1.0 a 1.25 en total_frames
    step = 0.25 / total_frames  # ~0.0016667 para 150 frames

    if is_even_scene:
        # Zoom In continuo hacia el centro
        zoom_expr = f"min(1.25,1.0+{step:.7f}*on)"
    else:
        # Zoom Out continuo desde el centro
        zoom_expr = f"max(1.0,1.25-{step:.7f}*on)"

    # Centrado dinámico respecto a las dimensiones de la imagen
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"

    # Pre-escalado inteligente a 16:9 + crop para evitar deformaciones
    # seguido del filtro zoompan para el movimiento continuo
    filter_complex = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={fps}"
    )

    cmd = [
        "ffmpeg",
        "-y",                       # Sobrescribir sin preguntar
        "-i", str(image_path),      # Archivo de imagen de entrada
        "-vf", filter_complex,      # Cadena de filtros de escala y zoompan
        "-c:v", VIDEO_CODEC,        # Códec libx264
        "-pix_fmt", PIXEL_FORMAT,   # Formato de píxel yuv420p
        "-r", str(fps),             # 30 fps
        "-t", str(duration),        # Duración exacta de 5 segundos
        str(output_path)
    ]

    try:
        # Ejecución silenciosa: solo captura errores
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            print(f"❌ Error al procesar {image_path.name} (código {result.returncode}):")
            print(result.stderr.strip())
            return False

        return True

    except Exception as e:
        print(f"❌ Error inesperado ejecutando FFmpeg en {image_path.name}: {e}")
        return False


def process_all_images(limit: Optional[int] = None) -> None:
    """
    Función principal que orquesta la detección de imágenes, la creación del
    directorio de salida y la aplicación intercalada del efecto Ken Burns.
    """
    print("🎬 ==================================================================")
    print("🎬  INICIANDO PROCESAMIENTO MULTIMEDIA: EFECTO KEN BURNS (FFMPEG)")
    print("🎬 ==================================================================")
    print(f"📁 Ruta de origen: {SOURCE_DIR}")

    # Crear dinámicamente el directorio de salida si no existe
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📂 Directorio de salida: {OUTPUT_DIR}")

    # Obtener imágenes ordenadas usando pathlib
    images = get_image_files(SOURCE_DIR, OUTPUT_DIR)

    if not images:
        print("⚠️ No se encontraron imágenes válidas (.png, .jpg, .jpeg) para procesar.")
        return

    total_images = len(images) if limit is None else min(len(images), limit)
    print(f"🖼️  Se encontraron {len(images)} imágenes en total. Procesando: {total_images}")
    print("------------------------------------------------------------------")

    exitosos = 0
    errores = 0

    # Contador para intercalar el efecto de zoompan:
    # Escenas pares (0, 2, 4...) -> Zoom In continuo
    # Escenas impares (1, 3, 5...) -> Zoom Out continuo
    for scene_index, img_path in enumerate(images[:total_images]):
        is_even = (scene_index % 2 == 0)
        effect_label = "Zoom In (Centro)" if is_even else "Zoom Out (Centro)"
        parity_label = "Par" if is_even else "Impar"

        output_file = build_output_path(img_path, SOURCE_DIR, OUTPUT_DIR)

        print(
            f"🚀 [{scene_index + 1}/{total_images}] Procesando escena {scene_index} "
            f"[{parity_label} - {effect_label}]: {img_path.name}"
        )

        success = create_ken_burns_clip(
            image_path=img_path,
            output_path=output_file,
            is_even_scene=is_even,
            duration=DURATION_SECONDS,
            fps=FPS,
            width=WIDTH,
            height=HEIGHT
        )

        if success:
            print(
                f"✅ Completado: {output_file.name} "
                f"({DURATION_SECONDS}s, {WIDTH}x{HEIGHT} @ {FPS}fps)"
            )
            exitosos += 1
        else:
            errores += 1

    print("==================================================================")
    print("🎉 RESUMEN DE PROCESAMIENTO FINALIZADO")
    print(f"✅ Clips generados exitosamente: {exitosos}")
    if errores > 0:
        print(f"❌ Errores encontrados: {errores}")
    print(f"📂 Carpeta de destino: {OUTPUT_DIR}")
    print("==================================================================")


if __name__ == "__main__":
    # Permite limitar la cantidad de imágenes procesadas si se pasa un argumento por consola
    limit_arg = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit_arg = int(sys.argv[1])
        print(f"⚙️ Límite especificado por argumento: {limit_arg} escenas.")

    process_all_images(limit=limit_arg)
