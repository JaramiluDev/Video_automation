from video_automation.script_parser import parse_script


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
