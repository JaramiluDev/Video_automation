#!/usr/bin/env python3
"""
Renderiza clips de overlay Manim (src/video_automation/animations/) para
incrustarlos sobre la base visual del guion.

La extensión de --output decide el formato:
  .mp4   opaco, libx264 + yuv420p (igual que simple_animator.py)
  .mov   CON ALFA, QuickTime ProRes 4444      ← recomendado para overlay
  .webm  CON ALFA, VP9 (yuva420p)

Siempre 1920x1080 a 30 fps constantes con cuadros exactos (round(dur*fps)),
salvo que se pida otra cosa con --fps / --preview. Al terminar verifica la
salida con ffprobe y sale con código 1 si algo no cumple.

Ejemplos:
  python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mp4
  python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mov
  python scripts/render_manim_clips.py --scene Scene02Math --output assets/source_scripts/GUION-02/manim_overlay.mp4 --alpha
  python scripts/render_manim_clips.py --scene Scene02Math --output prueba.mov --preview
  python scripts/render_manim_clips.py --scene Scene02Math --output o.mov --param orden=[img06,img04,img05]
  python scripts/render_manim_clips.py --list
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.video_automation.animations import SCENE_REGISTRY, render_overlay  # noqa: E402
from src.video_automation.manim_timing import check_latex, strict_latex  # noqa: E402

PREVIEW_RES = (854, 480)


def parse_param(text: str):
    """key=value → (key, valor). El valor se interpreta como YAML (números, listas)."""
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"--param espera clave=valor, no {text!r}")
    key, raw = text.split("=", 1)
    try:
        import yaml
        value = yaml.safe_load(raw)
    except Exception:
        value = raw
    return key.strip(), value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", help="Clase de animations/math_scenes.py (ver --list)")
    ap.add_argument("--output", help="Ruta del clip: .mp4 (opaco), .mov o .webm (con alfa)")
    ap.add_argument("--alpha", action="store_true",
                    help="Fuerza canal alfa: si --output es .mp4 se escribe un .mov ProRes 4444 al lado")
    ap.add_argument("--duration", type=float, help="Duración total en segundos (por defecto, la de la escena)")
    ap.add_argument("--fps", type=int, default=30, choices=(30, 60), help="Cuadros por segundo (30 por defecto)")
    ap.add_argument("--preview", action="store_true", help="854x480 para revisar rápido")
    ap.add_argument("--param", action="append", type=parse_param, default=[], metavar="CLAVE=VALOR",
                    help="Parámetro de la escena (repetible). Ej.: --param a=2/4 --param posicion=arriba")
    ap.add_argument("--list", action="store_true", help="Lista las escenas disponibles y sale")
    ap.add_argument("--no-verify", action="store_true", help="No verificar la salida con ffprobe")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.list:
        for name, cls in SCENE_REGISTRY.items():
            doc = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""
            print(f"{name:<16} {cls.DEFAULT_DURATION:>5.1f}s  tramos={list(cls.SEGMENTS)}  {doc}")
        return 0
    if not args.scene or not args.output:
        ap.error("--scene y --output son obligatorios (o usa --list)")
    if args.scene not in SCENE_REGISTRY:
        ap.error(f"Escena desconocida {args.scene!r}. Disponibles: {', '.join(SCENE_REGISTRY)}")

    output = Path(args.output)
    ext = output.suffix.lower()
    if ext not in (".mp4", ".mov", ".webm"):
        ap.error("--output debe terminar en .mp4, .mov o .webm")
    if args.alpha and ext == ".mp4":
        output = output.with_suffix(".mov")
        print(f"ℹ️  MP4/H.264 no admite transparencia: se exporta {output} (ProRes 4444 con alfa).")

    ok, msg = check_latex()
    print(("✅ " if ok else "⚠️  ") + msg)
    if not ok and strict_latex():
        return 1

    res = PREVIEW_RES if args.preview else (1920, 1080)
    params = dict(args.param) or None
    cls = SCENE_REGISTRY[args.scene]
    duration = args.duration or cls.DEFAULT_DURATION
    alpha = output.suffix.lower() in (".mov", ".webm")

    print(f"🎬 {args.scene}: {duration:.3f}s @ {args.fps}fps, {res[0]}x{res[1]}, "
          f"{'con alfa' if alpha else 'opaco'} → {output}")
    t0 = time.time()
    try:
        info = render_overlay(args.scene, str(output), duration=duration, params=params,
                              resolution=res, fps=args.fps, verify=not args.no_verify)
    except Exception as exc:
        print(f"❌ {exc}")
        return 1

    expected = int(round(duration * args.fps))
    print(f"✅ {output}  {info['width']}x{info['height']}  {info['avg_fps']:.2f}fps  "
          f"{info['frames']}/{expected} cuadros  {info['codec']}/{info['pix_fmt']}  "
          f"alfa={'sí' if info['has_alpha'] else 'no'}  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
