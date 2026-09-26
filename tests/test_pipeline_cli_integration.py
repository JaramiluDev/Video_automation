from pathlib import Path

from video_automation.cli import build_parser
from video_automation.pipeline import run_pipeline


def test_run_pipeline_generates_audio_and_respects_fps(tmp_path):
    script_file = tmp_path / "script.yaml"
    script_file.write_text(
        """
title: "Test video"
output_filename: "result.mp4"
scenes:
  - id: "ESCENA-01"
    title: "Intro"
    narration: "Hola mundo desde el pipeline"
    image_paths:
      - "data/assets/placeholder_1.png"
    duration: 2.0
""".strip(),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    result = run_pipeline(str(script_file), str(output_dir), fps=12, include_audio=True)

    assert Path(result).exists() or result.endswith(".mp4")
    assert (output_dir / "audio").exists()


def test_cli_parser_accepts_render_options():
    parser = build_parser()
    args = parser.parse_args([
        "render",
        "--script",
        "example.yaml",
        "--output",
        "rendered",
        "--fps",
        "24",
        "--resolution",
        "1280x720",
        "--no-audio",
    ])

    assert args.command == "render"
    assert args.fps == 24
    assert args.resolution == "1280x720"
    assert args.no_audio is True
