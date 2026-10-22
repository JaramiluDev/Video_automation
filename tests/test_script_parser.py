from video_automation.script_parser import (
    docx_to_yaml,
    docx_to_yaml_data,
    parse_script,
)
from pathlib import Path


def test_parse_valid_script(tmp_path):
    script_file = tmp_path / "script.yaml"
    script_file.write_text(
        """
title: "Test script"
output_filename: "result.mp4"
scenes:
  - id: "ESCENA-01"
    title: "Introducción"
    narration: "Hola mundo"
    image_paths:
      - "data/assets/placeholder_1.png"
    duration: 2.5
""".strip(),
        encoding="utf-8",
    )

    script = parse_script(str(script_file))

    assert script.title == "Test script"
    assert script.output_filename == "result.mp4"
    assert len(script.scenes) == 1
    assert script.scenes[0].image_paths == ["data/assets/placeholder_1.png"]
    assert script.scenes[0].duration == 2.5


def test_docx_conversion_if_asset_exists(tmp_path):
    docx_path = Path("assets/source_scripts/Guion_visual_12_escenas_36_imagenes_DIALOGOS.docx")
    if not docx_path.exists():
        return

    output_yaml = tmp_path / "test_out.yaml"
    docx_to_yaml(docx_path=docx_path, output_path=output_yaml)

    assert output_yaml.exists()
    raw_data = docx_to_yaml_data(docx_path=docx_path)
    assert len(raw_data["scenes"]) == 12
    first_raw = raw_data["scenes"][0]
    assert first_raw["id"] == "escena_01"
    assert first_raw["title"].startswith("Escena 1")
    assert "dialogue" in first_raw
    assert len(first_raw["dialogue"]) == 14
    assert first_raw["narration"] != ""
    assert "(muestra el cartel)" in first_raw["narration"]

    script = parse_script(str(output_yaml))
    assert len(script.scenes) == 12
    assert script.scenes[0].id == "escena_01"
    assert script.scenes[0].title.startswith("Escena 1")
    assert len(script.scenes[0].dialogues) == 14
    assert len(script.scenes[0].dialogue) == 14
    assert script.scenes[0].dialogues[0].character == "AgenteCero"
    assert script.scenes[0].dialogues[0].voice_model == "PersonajeVaronil2"
    assert script.scenes[0].narration.startswith("(muestra el cartel)")


