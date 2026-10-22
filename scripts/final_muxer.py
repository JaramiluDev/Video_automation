#!/usr/bin/env python3
"""
Módulo final_muxer.py: Multiplexor final de audio y video con FFmpeg.

Este script orquesta el ensamblaje final de una producción audiovisual combinando:
1. Una pista de video base pre-renderizada (ej. 'video2_base_render.mp4').
2. Una pista de audio con la locución/TTS o banda sonora (ej. 'audio_tts.mp3' o '.wav').
3. Generación del contenedor de video final listo para distribución (ej. 'video_final_listo.mp4').

Requisitos técnicos de FFmpeg:
- Video lossless stream copy (-c:v copy): Evita re-codificación, ahorrando CPU y conservando 100% la calidad original.
- Audio encode AAC (-c:a aac -b:a 192k): Codifica la pista de audio en formato estándar AAC a 192 kbps.
- Mapeo de flujos (-map 0:v:0 -map 1:a:0): Asocia exclusivamente el video primario y el audio provisto,
  descartando audios residuales del video base o carátulas incrustadas en archivos MP3.
- Recorte automático (-shortest): Finaliza el contenedor tan pronto termine el flujo más corto.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Union


# ==============================================================================
# Excepciones personalizadas para el pipeline de video
# ==============================================================================

class MuxerError(Exception):
    """Excepción base para fallos durante el proceso de multiplexado."""
    pass


class FFmpegNotFoundError(MuxerError, FileNotFoundError):
    """Lanzada cuando el binario de FFmpeg no se encuentra en el sistema."""
    pass


class MediaNotFoundError(MuxerError, FileNotFoundError):
    """Lanzada cuando uno de los archivos multimedia requeridos no existe."""
    pass


class InvalidMediaError(MuxerError, ValueError):
    """Lanzada cuando un archivo multimedia no cumple con los requisitos mínimos."""
    pass


class FFmpegExecutionError(MuxerError):
    """Lanzada cuando FFmpeg finaliza con un código de error distinto de cero."""

    def __init__(self, returncode: int, cmd: List[str], stderr: str) -> None:
        self.returncode = returncode
        self.cmd = cmd
        self.stderr = stderr
        cmd_str = " ".join(cmd)
        message = (
            f"FFmpeg falló con código de salida {returncode}.\n"
            f"Comando ejecutado:\n  {cmd_str}\n\n"
            f"Salida de error (stderr):\n{stderr.strip()}"
        )
        super().__init__(message)


# ==============================================================================
# Funciones auxiliares de formateo y validación
# ==============================================================================

def format_file_size(size_in_bytes: int) -> str:
    """
    Convierte un tamaño en bytes a una representación legible por humanos.

    Args:
        size_in_bytes: Tamaño en bytes.

    Returns:
        Cadena con el tamaño formateado (B, KB, MB, GB).
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_in_bytes)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def validate_environment() -> str:
    """
    Verifica que el ejecutable de FFmpeg esté disponible en el PATH del sistema.

    Returns:
        Ruta absoluta al binario de FFmpeg encontrado.

    Raises:
        FFmpegNotFoundError: Si FFmpeg no está instalado o no se encuentra en el PATH.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegNotFoundError(
            "El binario 'ffmpeg' no fue encontrado en las variables de entorno (PATH). "
            "Asegúrate de instalar FFmpeg en el sistema antes de ejecutar este script."
        )
    return ffmpeg_path


def validate_inputs(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """
    Valida la existencia e integridad básica de los archivos multimedia y rutas.

    Args:
        video_path: Ruta al archivo de video base.
        audio_path: Ruta al archivo de audio.
        output_path: Ruta de destino para el video final.

    Raises:
        MediaNotFoundError: Si el video o el audio no existen.
        InvalidMediaError: Si los archivos están vacíos o las rutas colisionan.
    """
    # 1. Validar video base
    if not video_path.exists():
        raise MediaNotFoundError(f"El video base especificado no existe: {video_path}")
    if not video_path.is_file():
        raise InvalidMediaError(f"La ruta del video base no es un archivo regular: {video_path}")
    if video_path.stat().st_size == 0:
        raise InvalidMediaError(f"El video base está vacío (0 bytes): {video_path}")

    # 2. Validar archivo de audio
    if not audio_path.exists():
        raise MediaNotFoundError(f"El archivo de audio especificado no existe: {audio_path}")
    if not audio_path.is_file():
        raise InvalidMediaError(f"La ruta del audio no es un archivo regular: {audio_path}")
    if audio_path.stat().st_size == 0:
        raise InvalidMediaError(f"El archivo de audio está vacío (0 bytes): {audio_path}")

    # 3. Validar colisión de rutas (evitar sobrescribir insumos de entrada con la salida)
    resolved_video = video_path.resolve()
    resolved_audio = audio_path.resolve()
    resolved_output = output_path.resolve()

    if resolved_output == resolved_video:
        raise InvalidMediaError(
            f"La ruta de salida no puede ser idéntica al video de entrada: {output_path}"
        )
    if resolved_output == resolved_audio:
        raise InvalidMediaError(
            f"La ruta de salida no puede ser idéntica al archivo de audio de entrada: {output_path}"
        )


def build_ffmpeg_command(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    overwrite: bool = True,
    reencode: bool = False,
) -> List[str]:
    """
    Construye la lista de argumentos para el comando FFmpeg con las especificaciones técnicas:
    - Copia directa o re-encodificación de alta fidelidad: -c:v copy / libx264 -crf 18 -preset slow -pix_fmt yuv420p
    - Codificación de audio en AAC a 192k: -c:a aac -b:a 192k
    - Recorte al flujo más corto: -shortest
    - Mapeo explícito de flujos: -map 0:v:0 -map 1:a:0
    """
    cmd: List[str] = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
    ]

    if reencode:
        cmd.extend([
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "slow",
            "-pix_fmt", "yuv420p",
        ])
    else:
        cmd.extend(["-c:v", "copy"])

    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ])
    return cmd


# ==============================================================================
# Lógica principal de multiplexado
# ==============================================================================

def mux_video_audio(
    video_path: Union[str, Path],
    audio_path: Union[str, Path],
    output_path: Union[str, Path],
    overwrite: bool = True,
    timeout: Optional[float] = None,
    reencode: bool = False,
) -> Path:
    """
    Ejecuta el proceso de multiplexado (muxing) combinando video base y audio mediante FFmpeg.

    Args:
        video_path: Ruta al archivo de video base.
        audio_path: Ruta al archivo de audio (TTS, voz o música).
        output_path: Ruta deseada para el archivo de salida final.
        overwrite: Si es True, sobrescribe el archivo de salida en caso de existir.
        timeout: Tiempo máximo en segundos para la ejecución del subproceso (opcional).
        reencode: Si es True, re-encodifica con libx264 -crf 18 -preset slow -pix_fmt yuv420p.
    """
    # 1. Asegurar tipos Path
    video = Path(video_path)
    audio = Path(audio_path)
    output = Path(output_path)

    # 2. Validar entorno y parámetros de entrada
    validate_environment()
    validate_inputs(video_path=video, audio_path=audio, output_path=output)

    # 3. Crear directorios padre de destino si no existen
    if output.parent and not output.parent.exists():
        output.parent.mkdir(parents=True, exist_ok=True)

    # 4. Construir comando de FFmpeg
    cmd = build_ffmpeg_command(
        video_path=video,
        audio_path=audio,
        output_path=output,
        overwrite=overwrite,
        reencode=reencode,
    )

    print("=" * 70)
    print("🎬 INICIANDO FFMPEG FINAL MUXER")
    print("=" * 70)
    print(f"📹 Video base:    {video} ({format_file_size(video.stat().st_size)})")
    print(f"🎵 Audio entrada: {audio} ({format_file_size(audio.stat().st_size)})")
    print(f"💾 Salida final:  {output}")
    print(f"⚙️  Comando CLI:   {' '.join(cmd)}")
    print("-" * 70)

    start_time = time.perf_counter()

    # 5. Ejecución con subprocess
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"❌ Error: El proceso de FFmpeg excedió el tiempo límite de {timeout} segundos.")
        raise exc

    elapsed_time = time.perf_counter() - start_time

    # 6. Manejo de fallos en FFmpeg
    if process.returncode != 0:
        raise FFmpegExecutionError(
            returncode=process.returncode,
            cmd=cmd,
            stderr=process.stderr,
        )

    # 7. Verificación final del archivo generado
    if not output.exists() or output.stat().st_size == 0:
        raise InvalidMediaError(
            f"El proceso finalizó pero el archivo de salida no fue creado o está vacío: {output}"
        )

    output_size = output.stat().st_size
    print("✅ Multiplexado completado con éxito.")
    print(f"⏱️  Tiempo de procesamiento: {elapsed_time:.2f} s")
    print(f"📦 Tamaño del video final:   {format_file_size(output_size)}")
    print(f"📍 Ruta completa:            {output.resolve()}")
    print("=" * 70)

    return output.resolve()


# ==============================================================================
# Interfaz de línea de comandos (CLI)
# ==============================================================================

def parse_args(args: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """
    Configura y analiza los argumentos de la línea de comandos con argparse.

    Permite tanto argumentos posicionales como banderas nombradas (-v, -a, -o).

    Args:
        args: Argumentos explícitos (útil para pruebas unitarias). Si es None, usa sys.argv[1:].

    Returns:
        Namespace con los argumentos parseados.
    """
    parser = argparse.ArgumentParser(
        prog="final_muxer.py",
        description=(
            "Muxer de producción audiovisual con FFmpeg: Combina un video base con una pista de "
            "audio (TTS/Voz) utilizando copia directa de video (-c:v copy), codificación AAC a 192k "
            "(-c:a aac -b:a 192k) y ajuste al flujo más corto (-shortest)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Argumentos posicionales principales
    parser.add_argument(
        "video",
        type=Path,
        nargs="?",
        default=None,
        help="Ruta del video base (ej. video2_base_render.mp4).",
    )
    parser.add_argument(
        "audio",
        type=Path,
        nargs="?",
        default=None,
        help="Ruta del archivo de audio (ej. audio_tts.mp3 o .wav).",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Ruta del video final resultante (ej. video_final_listo.mp4).",
    )

    # Banderas opcionales alternativas para mayor ergonomía en scripts de automatización
    parser.add_argument(
        "-v", "--video",
        dest="video_flag",
        type=Path,
        default=None,
        help="Ruta alternativa del video base.",
    )
    parser.add_argument(
        "-a", "--audio",
        dest="audio_flag",
        type=Path,
        default=None,
        help="Ruta alternativa del archivo de audio.",
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_flag",
        type=Path,
        default=None,
        help="Ruta alternativa de salida.",
    )

    # Opciones de control de sobrescritura
    parser.add_argument(
        "-y", "--overwrite",
        action="store_true",
        dest="overwrite",
        default=True,
        help="Sobrescribe el archivo de salida si ya existe (por defecto: True).",
    )
    parser.add_argument(
        "-n", "--no-overwrite",
        action="store_false",
        dest="overwrite",
        help="No sobrescribe el archivo si ya existe.",
    )

    # Límite de tiempo opcional
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Tiempo límite de ejecución en segundos antes de abortar el subproceso.",
    )

    # Opción de re-encodificación de alta fidelidad
    parser.add_argument(
        "--reencode",
        action="store_true",
        default=False,
        help="Re-encodifica el video usando libx264 -crf 18 -preset slow -pix_fmt yuv420p en vez de stream copy.",
    )

    parsed = parser.parse_args(args)
    return parsed


def main() -> None:
    """Punto de entrada de ejecución desde la línea de comandos."""
    args = parse_args()

    # Resolver parámetros soportando tanto posicionales como banderas nombradas
    video_path: Optional[Path] = args.video or args.video_flag
    audio_path: Optional[Path] = args.audio or args.audio_flag
    output_path: Optional[Path] = args.output or args.output_flag

    # Validar que los 3 argumentos requeridos hayan sido proporcionados
    missing_args: List[str] = []
    if not video_path:
        missing_args.append("Ruta del video base (video / -v / --video)")
    if not audio_path:
        missing_args.append("Ruta del archivo de audio (audio / -a / --audio)")
    if not output_path:
        missing_args.append("Ruta del video final de salida (output / -o / --output)")

    if missing_args:
        print("❌ Error: Faltan argumentos obligatorios en la línea de comandos:\n")
        for item in missing_args:
            print(f"   • {item}")
        print("\nUso básico (posicional):")
        print("   python scripts/final_muxer.py <video_base.mp4> <audio.mp3> <video_final.mp4>")
        print("\nUso alternativo con flags:")
        print("   python scripts/final_muxer.py -v <video_base.mp4> -a <audio.mp3> -o <video_final.mp4>")
        print("\nEjemplo práctico:")
        print("   python scripts/final_muxer.py animated_clips/video2_base_render.mp4 audio_tts.mp3 video_final_listo.mp4\n")
        sys.exit(1)

    try:
        mux_video_audio(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            overwrite=args.overwrite,
            timeout=args.timeout,
            reencode=args.reencode,
        )
        sys.exit(0)
    except MediaNotFoundError as err:
        print(f"\n❌ [ERROR DE ARCHIVO]: {err}")
        sys.exit(1)
    except InvalidMediaError as err:
        print(f"\n❌ [ERROR DE PARÁMETRO]: {err}")
        sys.exit(1)
    except FFmpegNotFoundError as err:
        print(f"\n❌ [ERROR DE ENTORNO]: {err}")
        sys.exit(1)
    except FFmpegExecutionError as err:
        print(f"\n❌ [ERROR FFMPEG]: {err}")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("\n❌ [ERROR TIMEOUT]: La ejecución de FFmpeg excedió el tiempo máximo permitido.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Proceso interrumpido por el usuario.")
        sys.exit(130)
    except Exception as err:
        print(f"\n❌ [ERROR INESPERADO]: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
