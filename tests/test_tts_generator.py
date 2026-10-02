from pathlib import Path

from video_automation.models import Scene
from video_automation.narrator import TTSNarrator


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
