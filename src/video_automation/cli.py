"""
Módulo de interfaz de línea de comandos (CLI) para Video Automation.
Permite validar guiones YAML y ejecutar el pipeline de renderizado de video.
"""

import argparse

from .pipeline import run_pipeline
from .render_profiles import add_quality_arguments, profile_from_args
from .script_parser import parse_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    val_parser = subparsers.add_parser("validate", help="Valida el formato del guión YAML")
    val_parser.add_argument("--script", required=True, help="Ruta al script YAML")

    ren_parser = subparsers.add_parser("render", help="Renderiza el video")
    ren_parser.add_argument("--script", required=True, help="Ruta al script YAML")
    ren_parser.add_argument("--output", default="data/renders", help="Directorio de salida")
    ren_parser.add_argument("--fps", type=int, default=None,
                            help="Frames por segundo (por defecto, output_settings del guion o 30)")
    ren_parser.add_argument("--resolution", default=None,
                            help="Resolución base, ej. 1280x720 (por defecto, la del guion o 1920x1080). "
                                 "El perfil de calidad la escala después.")
    ren_parser.add_argument("--no-audio", action="store_true", help="Desactiva la generación de audio")
    ren_parser.add_argument("--no-cache", action="store_true",
                            help="Vuelve a renderizar los clips Manim aunque estén en caché")
    add_quality_arguments(ren_parser)

    prof_parser = subparsers.add_parser("profiles", help="Lista los perfiles de calidad")
    prof_parser.add_argument("--resolution", default="1920x1080", help="Resolución base para el ejemplo")
    prof_parser.add_argument("--fps", type=int, default=30)

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
            profile=profile_from_args(args),
            use_cache=not args.no_cache,
        )
    elif args.command == "profiles":
        from .pipeline import parse_resolution
        from .render_profiles import ENV_VAR, PROFILES, get_profile

        base = parse_resolution(args.resolution)
        current = get_profile(None).name
        for name, prof in PROFILES.items():
            res, fps = prof.resolve(base, args.fps)
            mark = "*" if name == current else " "
            print(f"{mark} {name:<11} {prof.summary(res, fps)}")
            print(f"  {'':<11} {prof.description}")
        print(f"\n* = perfil por defecto (${ENV_VAR} o production)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

