from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from video_automation.narrator import (
    VOICE_MAPPING,
    concatenate_audio_files,
    generate_script_audio,
    resolve_voice,
)


def test_resolve_voice_mappings():
    # Detective / Varonil 1 (DrSimi)
    assert resolve_voice("Detective", "DrSimi") == "es-MX-JorgeNeural"
    assert resolve_voice("detective") == "es-MX-JorgeNeural"
    assert resolve_voice(voice_model="DrSimi") == "es-MX-JorgeNeural"
    assert resolve_voice("Varonil 1") == "es-MX-JorgeNeural"
    assert resolve_voice(voice_model="PersonajeVaronil1") == "es-MX-JorgeNeural"

    # Agente Cero / Varonil 2
    assert resolve_voice("AgenteCero", "PersonajeVaronil2") == "es-GT-AndresNeural"
    assert resolve_voice("Agente Cero") == "es-GT-AndresNeural"
    assert resolve_voice(voice_model="PersonajeVaronil2") == "es-GT-AndresNeural"
    assert resolve_voice("Varonil 2") == "es-GT-AndresNeural"

    # Ana / Personaje Femenino
    assert resolve_voice("Ana", "PersonajeFemenino") == "es-MX-DaliaNeural"
    assert resolve_voice("ana") == "es-MX-DaliaNeural"
    assert resolve_voice(voice_model="PersonajeFemenino") == "es-MX-DaliaNeural"

    # Desconocido -> fallback por defecto
    assert resolve_voice("Desconocido", default_voice="es-MX-JorgeNeural") == "es-MX-JorgeNeural"


import asyncio

def test_generate_script_audio_processes_dialogues(tmp_path):
    async def _run():
        yaml_content = """
scenes:
  - id: escena_01
    title: Escena 1. Inicio
    dialogue:
      - character: Detective
        voice_model: DrSimi
        text: "Hola Agente Cero."
      - character: AgenteCero
        voice_model: PersonajeVaronil2
        text: "Hola Detective."
      - character: Ana
        voice_model: PersonajeFemenino
        text: "Hola a todos."
  - id: escena_02
    title: Escena 2. Cierre
    narration: "Narración de cierre general."
"""
        yaml_path = tmp_path / "test_guion.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        output_audio = tmp_path / "final_output.mp3"
        turns_dir = tmp_path / "dialogue_turns"

        # Simulamos generate_turn_audio para no depender de la conexión de red en tests unitarios
        recorded_calls = []

        async def mock_generate_turn(text, out_path, voice):
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"dummy mp3 data")
            recorded_calls.append({"text": text, "voice": voice, "path": str(out)})
            return True

        with patch("video_automation.narrator.generate_turn_audio", side_effect=mock_generate_turn):
            with patch("video_automation.narrator.concatenate_audio_files") as mock_concat:
                def fake_concat(files, target):
                    t = Path(target)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_bytes(b"merged audio")
                    return True

                mock_concat.side_effect = fake_concat

                success = await generate_script_audio(
                    yaml_path=yaml_path,
                    output_path=output_audio,
                    turns_dir=turns_dir,
                )

        assert success is True

        # Verificar que se procesaron los 3 turnos con sus voces correspondientes
        assert len(recorded_calls) == 4  # 3 diálogos de escena 1 + 1 narración de escena 2

        assert recorded_calls[0]["voice"] == "es-MX-JorgeNeural"
        assert recorded_calls[0]["text"] == "Hola Agente Cero."

        assert recorded_calls[1]["voice"] == "es-GT-AndresNeural"
        assert recorded_calls[1]["text"] == "Hola Detective."

        assert recorded_calls[2]["voice"] == "es-MX-DaliaNeural"
        assert recorded_calls[2]["text"] == "Hola a todos."

        assert recorded_calls[3]["voice"] == "es-MX-JorgeNeural"
        assert recorded_calls[3]["text"] == "Narración de cierre general."

        # Verificar existencia de archivos simulados
        scene1_dir = turns_dir / "escena_01"
        assert (scene1_dir / "turn_01_Detective.mp3").exists()
        assert (scene1_dir / "turn_02_AgenteCero.mp3").exists()
        assert (scene1_dir / "turn_03_Ana.mp3").exists()
        assert output_audio.exists()

    asyncio.run(_run())


def test_concatenate_single_audio_file(tmp_path):
    f1 = tmp_path / "single.mp3"
    f1.write_bytes(b"some audio data")
    target = tmp_path / "out.mp3"

    ok = concatenate_audio_files([f1], target)
    assert ok is True
    assert target.exists()
    assert target.read_bytes() == b"some audio data"


def test_concatenate_empty_audio_files(tmp_path):
    target = tmp_path / "empty_out.mp3"
    ok = concatenate_audio_files([], target)
    assert ok is False
    assert not target.exists()

