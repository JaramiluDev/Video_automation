"""
Módulo de interfaz de línea de comandos (CLI) para Video Automation.
Permite validar guiones YAML y ejecutar el pipeline de renderizado de video.
"""

import argparse

from .pipeline import run_pipeline
from .script_parser import parse_script
from typing import Optional
from importlib import import_module


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
    ren_parser.add_argument("--combine-audio", action="store_true", help="Combina los audios por escena en un MP3 único y remapea los subtítulos")

    fetch_render = subparsers.add_parser("fetch-render", help="Descarga un guion desde Google Sheets y lo renderiza")
    fetch_render.add_argument("--sheet-id", required=True, help="ID del Google Sheet")
    fetch_render.add_argument("--credentials", required=False, help="Ruta al JSON de la service account")
    fetch_render.add_argument("--episode", required=True, type=int, help="Número de episodio (ej. 3)")
    fetch_render.add_argument("--output", default="data/renders", help="Directorio de salida")
    fetch_render.add_argument("--fps", type=int, default=30, help="Frames por segundo del video")
    fetch_render.add_argument("--resolution", default="1920x1080", help="Resolución del video (ej. 1280x720)")
    fetch_render.add_argument("--no-audio", action="store_true", help="Desactiva la generación de audio")
    fetch_render.add_argument("--combine-audio", action="store_true", help="Combina los audios por escena en un MP3 único y remapea los subtítulos")

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
            combine_audio=args.combine_audio,
        )
    elif args.command == "fetch-render":
        # Lazy import to avoid adding Sheets deps for users who don't need it
        try:
            fetch_mod = import_module("scripts.fetch_sheet_script")
        except Exception:
            # try package-style import
            fetch_mod = import_module("..scripts.fetch_sheet_script", package=__package__)

        # Call the fetcher to write YAML into assets/source_scripts/GUION-XX/
        fetch_args = [
            "--sheet-id",
            args.sheet_id,
            "--episode",
            str(args.episode),
        ]
        if getattr(args, "credentials", None):
            fetch_args += ["--credentials", args.credentials]

        try:
            ret = fetch_mod.main(fetch_args)
        except SystemExit as e:
            # fetch_mod.main may call SystemExit; swallow non-zero only if failed
            if getattr(e, "code", 0) != 0:
                print("❌ La descarga del guion falló. Abortando render.")
                return
        except Exception as e:
            print(f"❌ Error ejecutando el fetch: {e}")
            return

        # Construct expected YAML path and render
        ep = int(args.episode)
        script_path = f"assets/source_scripts/GUION-{ep:02d}/GUION-{ep:02d}.yaml"
        run_pipeline(
            script_path,
            args.output,
            fps=args.fps,
            resolution=args.resolution,
            include_audio=not args.no_audio,
            combine_audio=args.combine_audio,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

