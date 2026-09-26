"""
Módulo de interfaz de línea de comandos (CLI) para Video Automation.
Permite validar guiones YAML y ejecutar el pipeline de renderizado de video.
"""

import argparse

from .pipeline import run_pipeline
from .script_parser import parse_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    val_parser = subparsers.add_parser("validate", help="Valida el formato del guión YAML")
    val_parser.add_argument("--script", required=True, help="Ruta al script YAML")

    ren_parser = subparsers.add_parser("render", help="Renderiza el video")
    ren_parser.add_argument("--script", required=True, help="Ruta al script YAML")
    ren_parser.add_argument("--output", default="data/renders", help="Directorio de salida")
    ren_parser.add_argument("--fps", type=int, default=30, help="Frames por segundo del video")
    ren_parser.add_argument("--resolution", default="1920x1080", help="Resolución del video (ej. 1280x720)")
    ren_parser.add_argument("--no-audio", action="store_true", help="Desactiva la generación de audio")

    return parser


def main():
    """Punto de entrada principal para la CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "validate":
        try:
            script = parse_script(args.script)
            print(f"✅ Guión '{script.title}' validado correctamente con {len(script.scenes)} escenas.")
        except Exception as e:
            print(f"❌ Error al validar: {e}")
    elif args.command == "render":
        run_pipeline(
            args.script,
            args.output,
            fps=args.fps,
            resolution=args.resolution,
            include_audio=not args.no_audio,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

