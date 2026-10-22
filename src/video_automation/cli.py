"""
Módulo de interfaz de línea de comandos (CLI) para Video Automation.
Permite validar guiones YAML y ejecutar el pipeline de renderizado de video.
"""

import argparse

from .pipeline import run_pipeline
from .render_profiles import add_quality_arguments, ensure_utf8_stdio, profile_from_args
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

    sync_parser = subparsers.add_parser(
        "sync-base",
        help="Video base cuyas escenas duran lo que su audio multi-voz (*_consolidated.mp3)")
    sync_parser.add_argument("--script", required=True, help="Guion YAML (ej. assets/source_scripts/GUION-02.yaml)")
    sync_parser.add_argument("--audio", required=True,
                             help="Audio del episodio (ej. data/output/GUION-02_audio.mp3)")
    sync_parser.add_argument("--dialogues-dir", default=None,
                             help="Carpeta con <id>/<id>_consolidated.mp3 (por defecto <audio>_dialogues/)")
    sync_parser.add_argument("--images-root", default=None,
                             help="Carpeta con ESCENA-NN/ (por defecto la del guion: assets/source_scripts/<guion>/)")
    sync_parser.add_argument("--output", default=None,
                             help="Video de salida (por defecto <carpeta del audio>/<guion>_base.mp4)")
    sync_parser.add_argument("--fps", type=int, default=None)
    sync_parser.add_argument("--resolution", default=None, help="Resolución base, ej. 1920x1080")
    sync_parser.add_argument("--cut-mode", choices=["turns", "equal"], default="turns",
                             help="Cortes de imagen en los cambios de turno o en partes iguales")
    sync_parser.add_argument("--static", action="store_true", help="Imágenes fijas (sin Ken Burns)")
    sync_parser.add_argument("--mux", action="store_true", help="Incluye la pista de audio en el .mp4")
    sync_parser.add_argument("--allow-missing", action="store_true",
                             help="Si falta el audio de una escena, usa la duration del YAML en vez de fallar")
    sync_parser.add_argument("--plan-only", action="store_true",
                             help="Solo muestra la línea de tiempo (no renderiza)")
    sync_parser.add_argument("--no-cache", action="store_true", help="Vuelve a generar los clips")
    sync_parser.add_argument("--jobs", type=int, default=None,
                             help="Clips en paralelo (por defecto $VA_JOBS, 1 en borrador, hasta 4 en producción)")
    add_quality_arguments(sync_parser)

    prof_parser = subparsers.add_parser("profiles", help="Lista los perfiles de calidad")
    prof_parser.add_argument("--resolution", default="1920x1080", help="Resolución base para el ejemplo")
    prof_parser.add_argument("--fps", type=int, default=30)

    return parser


def run_sync_base(args) -> int:
    """cli sync-base: plan y render del video base sincronizado con el audio."""
    from pathlib import Path

    from .heavy_render import (AudioSyncError, default_images_root, plan_audio_sync,
                               render_audio_synced_base, resolve_output_format)
    from .pipeline import parse_resolution

    script = parse_script(args.script)
    profile = profile_from_args(args)
    images_root = args.images_root or default_images_root(args.script)
    _, fps = resolve_output_format(script, profile, parse_resolution(args.resolution), args.fps)
    try:
        plan = plan_audio_sync(script, fps, dialogues_dir=args.dialogues_dir,
                               episode_audio=args.audio, images_root=images_root,
                               strict=not args.allow_missing, cut_mode=args.cut_mode)
    except (AudioSyncError, FileNotFoundError) as exc:
        print(f"❌ {exc}")
        return 1
    if args.plan_only:
        print(plan.table())
        for w in plan.warnings:
            print(f"⚠️  {w}")
        return 0
    profile.apply_process_limits()
    output = args.output or str(Path(args.audio).parent / f"{Path(args.script).stem}_base.mp4")
    render_audio_synced_base(script, output, episode_audio=args.audio,
                             dialogues_dir=args.dialogues_dir, images_root=images_root,
                             profile=profile, resolution=parse_resolution(args.resolution),
                             fps=args.fps, ken_burns=not args.static, cut_mode=args.cut_mode,
                             mux_audio=args.mux, use_cache=not args.no_cache, plan=plan,
                             strict=not args.allow_missing, jobs=args.jobs)
    return 0


def main():
    """Punto de entrada principal para la CLI."""
    ensure_utf8_stdio()
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
    elif args.command == "sync-base":
        raise SystemExit(run_sync_base(args))
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

