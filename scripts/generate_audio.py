#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from video_automation.audio.tts_engine import AudioUnifiedEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera un audio consolidado a partir de un guion local o de Google Sheets.")
    parser.add_argument("--script", required=True, help="Ruta al YAML del guion o a la carpeta que lo contiene.")
    parser.add_argument("--output", required=True, help="Ruta del archivo MP3 final.")
    parser.add_argument("--sheet-id", default=None, help="ID del documento de Google Sheets (opcional).")
    parser.add_argument("--sheet-name", default="Hoja1", help="Nombre de la hoja de Google Sheets.")
    parser.add_argument("--credentials-file", default=None, help="Ruta opcional al JSON de credenciales de servicio.")
    parser.add_argument("--title", default="Guion importado", help="Título del guion para metadatos.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = AudioUnifiedEngine()
    result = engine.generate(
        script_path=args.script,
        output_path=str(output_path),
        sheet_id=args.sheet_id,
        sheet_name=args.sheet_name,
        credentials_file=args.credentials_file,
        title=args.title,
    )
    print(f"Audio generado correctamente: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
