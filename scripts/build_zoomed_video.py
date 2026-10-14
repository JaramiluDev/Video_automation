#!/usr/bin/env python3
"""
Script orquestador: build_zoomed_video.py

Automatiza la generación de un video completo con efectos Ken Burns (Zoom In / Zoom Out)
intercalados a partir de un directorio de imágenes de entrada.

Flujo secuencial:
1. Importa las funciones principales de 'src.video_automation.simple_animator' y 'src.video_automation.simple_concatenator'.
2. Lee y valida la carpeta de imágenes de entrada proporcionada por el usuario por CLI.
3. Itera sobre las imágenes y genera miniclips individuales en MP4 aplicando Zoom In / Zoom Out alternados.
4. Guarda todos los miniclips generados en la ruta 'animated_clips/'.
5. Invoca a 'simple_concatenator' sobre 'animated_clips/' para fusionar los clips en 'video2_base_render.mp4'.
"""

import argparse
import inspect
import sys
from pathlib import Path
from typing import List, Optional

# Asegurar que el directorio raíz del proyecto esté en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 1. Importación de funciones principales de simple_animator y simple_concatenator
from src.video_automation.simple_animator import (
    DURATION_SECONDS,
    FPS,
    HEIGHT,
    VALID_EXTENSIONS,
    WIDTH,
    build_output_path,
    create_ken_burns_clip,
    get_image_files,
)
from src.video_automation.simple_concatenator import concatenate_clips
from src.video_automation.render_profiles import (
    RenderProfile, add_quality_arguments, get_profile, profile_from_args,
)

# Configuración por defecto
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "animated_clips"
DEFAULT_RENDER_NAME = "video2_base_render.mp4"


def build_zoomed_video(
    input_dir: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_video_name: str = DEFAULT_RENDER_NAME,
    duration: int = DURATION_SECONDS,
    fps: int = FPS,
    width: int = WIDTH,
    height: int = HEIGHT,
    limit: Optional[int] = None,
    clean: bool = False,
    profile: Optional[RenderProfile] = None,
) -> bool:
    """
    Orquesta la animación y concatenación secuencial de imágenes.

    Args:
        input_dir: Carpeta con las imágenes de entrada (.png, .jpg, .jpeg).
        output_dir: Carpeta donde se guardarán los miniclips ('animated_clips/').
        output_video_name: Nombre del video unificado ('video2_base_render.mp4').
        duration: Duración en segundos de cada clip animado.
        fps: Cuadros por segundo de cada clip.
        width: Ancho en píxeles de resolución (1080p -> 1920).
        height: Alto en píxeles de resolución (1080p -> 1080).
        limit: Límite opcional de escenas a procesar.
        clean: Si es True, elimina clips .mp4 previos en output_dir antes de iniciar.
        profile: Perfil de calidad (render_profiles.py). Escala width/height/fps
            y decide preset/CRF/hilos de libx264. None → $VA_QUALITY o production.

    Returns:
        bool: True si el proceso completó exitosamente, False en caso contrario.
    """
    print("=" * 70)
    print("🚀 INICIANDO ORQUESTADOR DE VIDEO ZOOMED (build_zoomed_video.py)")
    print("=" * 70)

    profile = profile or get_profile(None)
    (width, height), fps = profile.resolve((width, height), fps)
    print(f"⚙️  {profile.summary((width, height), fps)}")

    # 2. Validación de la carpeta de imágenes de entrada
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"❌ Error: La carpeta de entrada no existe o no es un directorio válido:")
        print(f"   {input_dir}")
        return False

    print(f"📁 Carpeta de imágenes de entrada: {input_dir}")
    print(f"📂 Carpeta para miniclips:         {output_dir}")
    print(f"🎞️  Nombre del video final:         {output_video_name}")

    # 4. Asegurar existencia del directorio 'animated_clips/'
    output_dir.mkdir(parents=True, exist_ok=True)

    if clean:
        print("\n🧹 Limpiando clips .mp4 previos en el directorio de salida...")
        for old_file in output_dir.glob("*.mp4"):
            try:
                old_file.unlink()
                print(f"   🗑️ Eliminado: {old_file.name}")
            except Exception as e:
                print(f"   ⚠️ No se pudo eliminar {old_file.name}: {e}")

    # Obtener imágenes disponibles
    images: List[Path] = get_image_files(source_dir=input_dir, output_dir=output_dir)
    if not images:
        valid_ext_str = ", ".join(sorted(VALID_EXTENSIONS))
        print(f"❌ Error: No se encontraron imágenes válidas ({valid_ext_str}) en: {input_dir}")
        return False

    total_available = len(images)
    if limit is not None and limit > 0:
        images = images[:limit]

    total_to_process = len(images)
    print(f"🖼️  Imágenes encontradas: {total_available} | A procesar: {total_to_process}")
    print("-" * 70)

    # 3. Iteración sobre las imágenes y aplicación de Zoom In / Zoom Out con simple_animator
    successful_clips: List[Path] = []
    failed_clips: List[Path] = []

    for scene_index, img_path in enumerate(images):
        # Paridad de la escena: par -> Zoom In, impar -> Zoom Out
        is_even = (scene_index % 2 == 0)
        parity_label = "Par" if is_even else "Impar"
        effect_label = "Zoom In (1.0 -> 1.25)" if is_even else "Zoom Out (1.25 -> 1.0)"

        # Determinar ruta del miniclip en animated_clips/
        output_clip_path = build_output_path(img_path, input_dir, output_dir)

        print(
            f"🎬 [{scene_index + 1}/{total_to_process}] Procesando escena {scene_index} "
            f"[{parity_label} - {effect_label}]: {img_path.name}"
        )

        success = create_ken_burns_clip(
            image_path=img_path,
            output_path=output_clip_path,
            is_even_scene=is_even,
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            encode_args=profile.x264_args(),
        )

        if success:
            successful_clips.append(output_clip_path)
            print(f"   ✅ Miniclip generado: {output_clip_path.name}")
        else:
            failed_clips.append(img_path)
            print(f"   ❌ Error al generar miniclip para: {img_path.name}")

    print("-" * 70)
    print(f"📊 Resumen de animación:")
    print(f"   • Miniclips exitosos: {len(successful_clips)}/{total_to_process}")
    if failed_clips:
        print(f"   • Miniclips fallidos: {len(failed_clips)}")

    if not successful_clips:
        print("❌ Error crítico: No se generó ningún miniclip. Proceso abortado.")
        return False

    # 5. Llamar a simple_concatenator sobre 'animated_clips/' para generar video2_base_render.mp4
    print("\n" + "=" * 70)
    print(f"🔗 FUSIONANDO MINICLIPS CON simple_concatenator...")
    print("=" * 70)

    # Invocación compatible de concatenate_clips
    sig = inspect.signature(concatenate_clips)
    if "output_video_name" in sig.parameters:
        concat_success = concatenate_clips(output_dir, output_video_name=output_video_name)
    else:
        # Modo de compatibilidad en caso de firma legacy
        concat_success = concatenate_clips(output_dir)
        if concat_success:
            legacy_file = output_dir / "final_render.mp4"
            target_file = output_dir / output_video_name
            if legacy_file.exists() and legacy_file != target_file:
                if target_file.exists():
                    target_file.unlink()
                legacy_file.rename(target_file)

    final_video_path = output_dir / output_video_name

    if concat_success and final_video_path.exists():
        video_size_mb = final_video_path.stat().st_size / (1024 * 1024)
        print("=" * 70)
        print("🎉 ¡ORQUESTACIÓN FINALIZADA CON ÉXITO!")
        print(f"✅ Video unificado creado: {final_video_path.name}")
        print(f"📍 Ruta completa:          {final_video_path}")
        print(f"📦 Tamaño del archivo:     {video_size_mb:.2f} MB")
        print(f"🎞️  Clips concatenados:     {len(successful_clips)}")
        print("=" * 70)
        return True
    else:
        print(f"❌ Error al concatenar los clips en: {final_video_path}")
        return False


def parse_args() -> argparse.Namespace:
    """Configura y procesa los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description=(
            "Orquestador multimedia: genera miniclips Ken Burns (Zoom In/Out) "
            "desde una carpeta de imágenes y los fusiona en 'video2_base_render.mp4'."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Ruta de la carpeta de imágenes de entrada.",
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_dir_flag",
        type=Path,
        default=None,
        help="Ruta alternativa de la carpeta de imágenes de entrada.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Directorio de los miniclips (por defecto 'animated_clips/', o "
             "'animated_clips_fast/' / '_lowres/' según el perfil, para no mezclar resoluciones).",
    )
    parser.add_argument(
        "-f", "--final-name",
        dest="output_video_name",
        type=str,
        default=None,
        help=f"Nombre del video final (por defecto '{DEFAULT_RENDER_NAME}', con sufijo _fast/_lowres "
             "fuera de producción).",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Límite opcional de escenas/imágenes a procesar.",
    )
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=DURATION_SECONDS,
        help="Duración en segundos de cada clip animado.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=FPS,
        help="Cuadros por segundo (FPS) del renderizado.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpia miniclips .mp4 previos en la carpeta de salida antes de procesar.",
    )
    add_quality_arguments(parser)
    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal para ejecución por consola."""
    args = parse_args()
    input_path = args.input_dir or args.input_dir_flag

    if not input_path:
        print("❌ Error: Debes especificar una carpeta de imágenes de entrada.")
        print("\nUso básico:")
        print("  python scripts/build_zoomed_video.py <carpeta_de_imagenes>")
        print("\nEjemplo:")
        print("  python scripts/build_zoomed_video.py assets/source_scripts/BUSCANDO-A-LA-X/BUSCANDO-A-LA-X --limit 2\n")
        sys.exit(1)

    profile = profile_from_args(args)
    profile.apply_process_limits()
    success = build_zoomed_video(
        input_dir=input_path,
        output_dir=args.output_dir or profile.tag_dir(DEFAULT_OUTPUT_DIR),
        output_video_name=args.output_video_name or profile.tag_path(DEFAULT_RENDER_NAME).name,
        duration=args.duration,
        fps=args.fps,
        limit=args.limit,
        clean=args.clean,
        profile=profile,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
