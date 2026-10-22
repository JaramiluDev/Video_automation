#!/usr/bin/env python3
"""
Renderiza y verifica las escenas Manim del Video 2 (scenes_video2.py).

Cada clip se guarda como <salida>/<id>.mp4 con:
  - resolución y fps de output_settings (1920x1080 @ 30 por defecto),
  - número de cuadros EXACTO = round(duration * fps),
  - libx264 + yuv420p + CFR, igual que simple_animator.py.
Al final imprime una tabla de verificación con ffprobe y sale con código 1 si
algo no cumple, así sirve como prueba de fuego dentro de Docker.

Ejemplos:
  python scripts/render_video2_scenes.py examples/video2_manim.yaml
  python scripts/render_video2_scenes.py examples/video2_manim.yaml --only V2E02_ProductosCruzados
  python scripts/render_video2_scenes.py examples/video2_manim.yaml --fast      # 480p/15fps, no satura el equipo
  python scripts/render_video2_scenes.py examples/video2_manim.yaml --low-res   # 720p/30fps
  python scripts/render_video2_scenes.py examples/video2_manim.yaml --production
  python scripts/render_video2_scenes.py --fps 60 --all                         # todas con duración por defecto
  python scripts/render_video2_scenes.py --check-latex                          # solo pre-vuelo de LaTeX
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.video_automation.manim_timing import check_latex, probe_video, render_timed_scene, strict_latex  # noqa: E402
from src.video_automation.scenes_video2 import SCENE_REGISTRY  # noqa: E402
from src.video_automation.render_profiles import add_quality_arguments, profile_from_args  # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "data" / "renders" / "video2_manim"


def _jobs_from_yaml(path: str):
    from src.video_automation.script_parser import parse_script

    script = parse_script(path)
    settings = script.output_settings
    jobs = [(s.id, s.manim_scene, s.duration, s.manim_params)
            for s in script.scenes if s.render_type == "manim" and s.manim_scene]
    res = tuple(settings.resolution) if settings else (1920, 1080)
    fps = settings.fps if settings else 30
    return jobs, res, fps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?", help="YAML del guion (escenas render_type: manim)")
    ap.add_argument("--all", action="store_true", help="Renderiza todas las clases registradas con su duración por defecto")
    ap.add_argument("--only", nargs="*", help="Nombres de clase a renderizar (filtra)")
    ap.add_argument("-o", "--output-dir", default=None,
                    help=f"Carpeta de salida (por defecto {DEFAULT_OUT.relative_to(PROJECT_ROOT)}"
                         "[_fast|_lowres] según el perfil)")
    ap.add_argument("--fps", type=int, help="Sobrescribe fps base (30 o 60)")
    ap.add_argument("--check-latex", action="store_true", help="Solo verifica que LaTeX compile")
    ap.add_argument("--no-cache", action="store_true", help="Re-renderiza aunque el clip esté en caché")
    add_quality_arguments(ap, preview_alias=True)
    args = ap.parse_args()
    profile = profile_from_args(args)

    ok, msg = check_latex()
    print(("✅ " if ok else "❌ ") + msg)
    if args.check_latex:
        return 0 if ok else 1

    if args.script:
        jobs, res, fps = _jobs_from_yaml(args.script)
    elif args.all:
        jobs = [(name, name, cls.DEFAULT_DURATION, None) for name, cls in SCENE_REGISTRY.items()]
        res, fps = (1920, 1080), 30
    else:
        ap.error("Indica un YAML o usa --all")
        return 2

    if args.only:
        jobs = [j for j in jobs if j[1] in args.only or j[0] in args.only]
    if args.fps:
        fps = args.fps
    res, fps = profile.resolve(res, fps)
    profile.apply_process_limits()
    print(f"⚙️  {profile.summary(res, fps)}")

    out_dir = Path(args.output_dir) if args.output_dir else profile.tag_dir(DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, failed = [], 0
    for scene_id, cls_name, duration, params in jobs:
        t0 = time.time()
        out = out_dir / f"{scene_id}.mp4"
        try:
            render_timed_scene(cls_name, str(out), duration=duration, params=params, resolution=res, fps=fps,
                               profile=profile, use_cache=not args.no_cache)
            info = probe_video(str(out))
            expected = int(round(duration * fps))
            good = (info["width"], info["height"]) == res and info["frames"] == expected \
                and abs(info["avg_fps"] - fps) < 0.01
            rows.append((scene_id, cls_name, f"{duration:.3f}", f"{info['frames']}/{expected}",
                         f"{info['width']}x{info['height']}", f"{info['avg_fps']:.2f}",
                         "OK" if good else "FALLA", f"{time.time() - t0:.1f}s"))
            failed += 0 if good else 1
        except Exception as exc:  # se reporta y se sigue con las demás
            failed += 1
            rows.append((scene_id, cls_name, f"{duration:.3f}", "-", "-", "-", f"ERROR: {exc}"[:60],
                         f"{time.time() - t0:.1f}s"))

    header = ("id", "clase", "dur(s)", "cuadros", "res", "fps", "estado", "t")
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    print()
    for r in [header] + rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
    print(f"\n{len(rows) - failed}/{len(rows)} escenas OK → {out_dir}")
    # Sin LaTeX solo es error si se pidió modo estricto (Docker / prueba de fuego).
    return 0 if failed == 0 and (ok or not strict_latex()) else 1


if __name__ == "__main__":
    sys.exit(main())
