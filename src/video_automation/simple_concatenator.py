#!/usr/bin/env python3
"""
Módulo simple_concatenator: Concatenación multimedia rápida y sin pérdida con FFmpeg.

Lee todos los clips .mp4 generados previamente en assets/source_scripts/animated_clips,
crea dinámicamente un archivo de lista temporal para el demuxer concat de FFmpeg,
ejecuta la unión con 'stream copy' (-c copy) para ensamblar el video final 'final_render.mp4',
y limpia los archivos temporales al finalizar.
"""

import subprocess
import sys
from pathlib import Path
from typing import List


def get_target_directory() -> Path:
    """
    Localiza y valida la carpeta de entrada requerida:
    assets/source_scripts/animated_clips.
    """
    # Ruta relativa requerida
    target_path = Path("assets/source_scripts/animated_clips")

    if target_path.exists():
        return target_path.resolve()

    # Si se ejecuta desde un subdirectorio o con ruta absoluta conocida
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "assets/source_scripts/animated_clips",
        script_dir.parent.parent / "assets/source_scripts/animated_clips",
        Path("/home/taekjoss/Projects/proyects/GitHub/Video_automation/assets/source_scripts/animated_clips"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    # Por defecto retorna la ruta requerida resuelta
    return target_path.resolve()


def concatenate_clips(input_dir: Path) -> bool:
    """
    Concatena todos los clips .mp4 en input_dir y genera final_render.mp4.
    """
    print("🎞️ ==================================================================")
    print("🎞️  INICIANDO CONCATENADOR DE CLIPS MULTIMEDIA (FFMPEG)")
    print("🎞️ ==================================================================")
    print(f"📂 Carpeta de entrada: {input_dir}")

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"❌ Error: La carpeta especificada no existe: {input_dir}")
        print("💡 Sugerencia: Ejecuta primero simple_animator.py para generar los clips.")
        return False

    output_video_name = "final_render.mp4"
    output_video_path = input_dir / output_video_name

    # 1. Leer y ordenar alfabéticamente todos los archivos .mp4 (excluyendo el render final si ya existe)
    mp4_files: List[Path] = sorted(
        [
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".mp4" and f.name != output_video_name
        ],
        key=lambda p: p.name.lower()
    )

    if not mp4_files:
        print(f"⚠️ No se encontraron archivos .mp4 para concatenar en: {input_dir}")
        return False

    print(f"📋 Se encontraron {len(mp4_files)} clips para unir:")
    for idx, clip in enumerate(mp4_files, start=1):
        print(f"   {idx}. {clip.name}")

    concat_file_name = "concat_list.txt"
    concat_file_path = input_dir / concat_file_name

    try:
        # 2. Crear dinámicamente concat_list.txt con el formato estricto: file 'nombre_del_video.mp4'
        print(f"\n📝 Creando lista temporal de concatenación: {concat_file_name}")
        with open(concat_file_path, "w", encoding="utf-8") as f:
            for video in mp4_files:
                # Escapar comillas simples si el nombre las contuviera
                safe_name = video.name.replace("'", "'\\''")
                f.write(f"file '{safe_name}'\n")

        print("🚀 Uniendo clips con FFmpeg (lossless stream copy)...")

        # 3. Ejecutar subprocess.run con el comando exacto solicitado
        # ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy final_render.mp4
        cmd = [
            "ffmpeg",
            "-y",                   # Sobrescribir sin pedir confirmación interactiva
            "-f", "concat",         # Demuxer concat de FFmpeg
            "-safe", "0",           # Permitir rutas de archivo flexibles
            "-i", concat_file_name, # Archivo de lista
            "-c", "copy",           # Unión instantánea sin recodificación
            output_video_name       # Archivo de salida
        ]

        result = subprocess.run(
            cmd,
            cwd=str(input_dir),
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            print(f"❌ Error durante la concatenación de videos (código {result.returncode}):")
            print(result.stderr.strip())
            return False

        print(f"✅ Render final listo: {output_video_path.name}")
        print(f"📍 Ubicación del video final: {output_video_path}")
        return True

    except Exception as e:
        print(f"❌ Error inesperado durante el proceso de concatenación: {e}")
        return False

    finally:
        # 4. Eliminar el archivo temporal concat_list.txt al finalizar
        if concat_file_path.exists():
            try:
                concat_file_path.unlink()
                print("🧹 Archivo temporal concat_list.txt eliminado con éxito.")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar el archivo temporal: {e}")

        print("==================================================================")


def main() -> None:
    target_dir = get_target_directory()
    success = concatenate_clips(target_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
