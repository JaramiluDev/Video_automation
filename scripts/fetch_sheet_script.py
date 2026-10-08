#!/usr/bin/env python3
"""Fetch a script from Google Sheets and emit a YAML file compatible with
the project's parser.

Usage:
  python scripts/fetch_sheet_script.py --sheet-id <ID> --episode 3 \
    [--credentials service-account.json]

This script supports Google Service Account JSON credentials (recommended for
server automation). If credentials are not provided or Sheets API calls fail,
it falls back to writing a sample YAML using a local example.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

try:
    import yaml
except Exception:
    print("PyYAML is required. Install with: pip install pyyaml")
    raise

SCRIPTS_DIR = Path("assets/source_scripts")


def rows_to_script(sheet_rows: List[Dict[str, Any]], episode: int) -> Dict[str, Any]:
    scenes = []
    for idx, row in enumerate(sheet_rows, start=1):
        scene_id = f"GUION-{episode:02d}-ESCENA-{idx:02d}"
        narration = row.get("Narracion") or row.get("Narración") or row.get("Narration") or row.get("Narr") or ""
        render_type = (row.get("TipoVisual") or row.get("Tipo") or "images").lower()
        recurso = row.get("Recurso") or row.get("Resource") or ""
        try:
            duration = float(row.get("DuracionEstimada") or row.get("DuraciónEstimada") or row.get("Duration") or 2.0)
        except Exception:
            duration = 2.0

        image_paths = [recurso] if recurso else []

        scenes.append({
            "id": scene_id,
            "title": row.get("Escena") or row.get("Scene") or scene_id,
            "narration": narration,
            "image_paths": image_paths,
            "duration": duration,
            "render_type": render_type,
        })

    script = {
        "title": f"GUION-{episode:02d}",
        "output_filename": f"guion-{episode:02d}.mp4",
        "scenes": scenes,
    }
    return script


def save_script_yaml(script: Dict[str, Any], episode: int) -> Path:
    folder = SCRIPTS_DIR / f"GUION-{episode:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"GUION-{episode:02d}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(script, f, sort_keys=False, allow_unicode=True)
    print(f"✅ Script saved to: {path}")
    return path


def fetch_sheet_rows(sheet_id: str, credentials_path: str | None = None) -> List[Dict[str, Any]]:
    # Lazy import the Google client to avoid failing environments that don't
    # need this script.
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError("Missing google-api-python-client or oauth libraries. Install them via pip: pip install google-api-python-client google-auth") from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    if credentials_path:
        creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=scopes)
    else:
        # No credentials path provided: try application default credentials
        from google.auth import default as default_creds

        creds, _ = default_creds(scopes=scopes)

    service = build("sheets", "v4", credentials=creds)
    # Read the first sheet grid. Users should ensure they have a simple table.
    sheet = service.spreadsheets()
    meta = sheet.get(spreadsheetId=sheet_id).execute()
    first_title = meta["sheets"][0]["properties"]["title"]
    range_ = f"'{first_title}'"
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_).execute()
    values = result.get("values", [])
    if not values:
        return []

    headers = [h.strip() for h in values[0]]
    rows = []
    for row in values[1:]:
        item: Dict[str, Any] = {}
        for i, h in enumerate(headers):
            item[h] = row[i] if i < len(row) else ""
        rows.append(item)
    return rows


def fallback_sample_yaml(episode: int) -> Path:
    sample = {
        "title": f"GUION-{episode:02d} (sample)",
        "output_filename": f"guion-{episode:02d}.mp4",
        "scenes": [
            {
                "id": f"GUION-{episode:02d}-ESCENA-01",
                "title": "Intro",
                "narration": "Este es un guion de ejemplo generado como fallback.",
                "image_paths": ["data/assets/placeholder_1.png"],
                "duration": 3.0,
            }
        ],
    }
    return save_script_yaml(sample, episode)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--credentials", help="Path to Google service account JSON for Sheets API")

    args = parser.parse_args(argv)

    try:
        rows = fetch_sheet_rows(args.sheet_id, args.credentials)
        if not rows:
            print("⚠️ La hoja está vacía o no se pudieron leer filas. Generando fallback.")
            fallback_sample_yaml(args.episode)
            return 0

        script = rows_to_script(rows, args.episode)
        path = save_script_yaml(script, args.episode)
        return 0
    except Exception as exc:
        print(f"❌ Error al leer Google Sheets: {exc}\nGenerando YAML de fallback.")
        fallback_sample_yaml(args.episode)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
