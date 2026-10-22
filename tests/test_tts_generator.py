from pathlib import Path

import pytest

from scripts.fetch_sheet_script import rows_to_script
from video_automation.models import Scene
from video_automation.narrator import TTSNarrator


def test_rows_to_script_requires_narration_for_each_scene():
    with pytest.raises(ValueError, match="Narracion|dialogo|diálogo"):
        rows_to_script([
            {
                "Escena": "Intro",
                "Narracion": "",
                "TipoVisual": "images",
                "Recurso": "data/assets/placeholder_1.png",
                "DuracionEstimada": "2.0",
            }
        ], 3)


def test_edge_tts_event_parser_handles_ms_and_ticks():
    narrator = TTSNarrator()
    events = [
        {"type": "WordBoundary", "offset": 5000, "duration": 1200, "text": "Hola"},
        {"type": "WordBoundary", "offset": 6200, "duration": 900, "text": "mundo"},
    ]

    parsed = narrator._parse_word_events(events)

    assert parsed[0]["word"] == "Hola"
    assert parsed[0]["start"] == pytest.approx(5.0)
    assert parsed[0]["end"] == pytest.approx(6.2)
    assert parsed[1]["word"] == "mundo"
    assert parsed[1]["start"] == pytest.approx(6.2)
    assert parsed[1]["end"] == pytest.approx(7.1)


def test_tts_narrator_creates_audio_and_timestamps(tmp_path):
    output_file = tmp_path / "narration.wav"

    result = TTSNarrator().generate_audio("Hola mundo desde Python", str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 0
    assert result["audio_path"] == str(output_file)
    assert result["engine"] in {"pyttsx3", "gtts", "fallback"}
    assert len(result["words"]) >= 2
    assert result["words"][0]["word"] == "Hola"


def test_scene_accepts_dialogue_alias_and_generates_valid_audio(tmp_path):
    scene = Scene.model_validate({
        "id": "ESCENA-01",
        "title": "Intro",
        "dialogue": "Este texto viene desde el campo dialogue.",
        "image_paths": ["data/assets/placeholder_1.png"],
        "duration": 2.0,
    })

    assert scene.narration == "Este texto viene desde el campo dialogue."

    output_file = tmp_path / "dialogue.wav"
    result = TTSNarrator().generate_audio(scene.narration, str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 0
    assert result["engine"] in {"pyttsx3", "gtts", "fallback"}
