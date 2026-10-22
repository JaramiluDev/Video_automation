import json
from pathlib import Path

import pytest

from video_automation.google_sheet_ingest import rows_to_script_definition
from video_automation.script_parser import parse_script


def test_rows_to_script_definition_maps_sheet_columns():
    rows = [
        {
            "Número de Escena": "1",
            "Título de la Escena": "Introducción",
            "Texto a Narrar": "Hola mundo desde Google Sheets",
            "Archivo de Imagen/Animación": "data/assets/placeholder_1.png",
            "Duración (segundos)": "2.5",
            "Voz": "jaime",
        },
        {
            "Número de Escena": "2",
            "Título de la Escena": "Desarrollo",
            "Texto a Narrar": "Seguimos con la explicación",
            "Archivo de Imagen/Animación": "data/assets/placeholder_2.png",
            "Duración (segundos)": "3.0",
            "Voz": "default",
        },
    ]

    script = rows_to_script_definition(rows, title="Guion desde Sheet", output_filename="sheet_output.mp4")

    assert script.title == "Guion desde Sheet"
    assert len(script.scenes) == 2
    assert script.scenes[0].id == "ESCENA-01"
    assert script.scenes[0].narration == "Hola mundo desde Google Sheets"
    assert script.scenes[0].image_paths == ["data/assets/placeholder_1.png"]
    assert script.scenes[0].duration == 2.5
    assert script.scenes[0].voice == "jaime"


def test_local_fallback_works_when_google_api_fail(tmp_path):
    fallback_file = tmp_path / "fallback.yaml"
    fallback_file.write_text(
        """
title: "Fallback local"
output_filename: "fallback.mp4"
scenes:
  - id: "ESCENA-01"
    title: "Intro"
    narration: "Esto viene del fallback local"
    image_paths:
      - "data/assets/placeholder_1.png"
    duration: 2.0
""".strip(),
        encoding="utf-8",
    )

    from video_automation.google_sheet_ingest import load_script_from_google_sheet

    script = load_script_from_google_sheet(
        sheet_id="invalid",
        sheet_name="Hoja1",
        local_fallback=str(fallback_file),
        google_credentials_path="missing.json",
    )

    assert script.title == "Fallback local"
    assert script.scenes[0].narration == "Esto viene del fallback local"
