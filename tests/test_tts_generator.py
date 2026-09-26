from pathlib import Path

from video_automation.narrator import TTSNarrator


def test_tts_narrator_creates_audio_and_timestamps(tmp_path):
    output_file = tmp_path / "narration.wav"

    result = TTSNarrator().generate_audio("Hola mundo desde Python", str(output_file))

    assert output_file.exists()
    assert result["audio_path"] == str(output_file)
    assert result["engine"] in {"pyttsx3", "gtts", "fallback"}
    assert len(result["words"]) >= 2
    assert result["words"][0]["word"] == "Hola"
