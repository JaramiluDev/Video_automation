#!/usr/bin/env python3
"""
Módulo de Locución y Generación de Voz TTS Multi-Voz (Narrator).

Procesa los bloques de diálogo de cada escena asignando una voz distinta de Edge-TTS
a cada personaje:
- Detective / Varonil 1 (DrSimi o similar): es-MX-JorgeNeural
- Agente Cero / Varonil 2: es-GT-AndresNeural
- Ana / Personaje Femenino: es-MX-DaliaNeural

Genera el audio individual para cada turno de diálogo, concatena los audios
por escena y ensambla el resultado final en el archivo de audio del episodio.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml


# Mapeo de personajes y modelos a voces de Edge-TTS
VOICE_MAPPING: Dict[str, str] = {
    # Detective / Varonil 1 (DrSimi o similar) -> es-MX-JorgeNeural
    "detective": "es-MX-JorgeNeural",
    "drsimi": "es-MX-JorgeNeural",
    "dr simi": "es-MX-JorgeNeural",
    "personajevaronil1": "es-MX-JorgeNeural",
    "varonil1": "es-MX-JorgeNeural",

    # Agente Cero / Varonil 2 -> es-GT-AndresNeural
    "agentecero": "es-GT-AndresNeural",
    "agente cero": "es-GT-AndresNeural",
    "personajevaronil2": "es-GT-AndresNeural",
    "varonil2": "es-GT-AndresNeural",

    # Ana / Personaje Femenino -> es-MX-DaliaNeural
    "ana": "es-MX-DaliaNeural",
    "personajefemenino": "es-MX-DaliaNeural",
    "femenino": "es-MX-DaliaNeural",
}

DEFAULT_VOICE = "es-MX-JorgeNeural"


def resolve_voice(
    character: Optional[str] = None,
    voice_model: Optional[str] = None,
    default_voice: str = DEFAULT_VOICE,
) -> str:
    """
    Determina la voz de Edge-TTS asignada a un personaje o modelo de voz.
    - Detective / Varonil 1 (DrSimi): es-MX-JorgeNeural
    - Agente Cero / Varonil 2: es-GT-AndresNeural
    - Ana / Personaje Femenino: es-MX-DaliaNeural
    """
    candidates = [voice_model, character]
    for candidate in candidates:
        if not candidate:
            continue
        cleaned = str(candidate).strip().lower()
        if cleaned in VOICE_MAPPING:
            return VOICE_MAPPING[cleaned]

        normalized = cleaned.replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
        if normalized in VOICE_MAPPING:
            return VOICE_MAPPING[normalized]

        for key, voice in VOICE_MAPPING.items():
            key_norm = key.replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
            if key_norm in normalized or normalized in key_norm:
                return voice

    return default_voice


async def generate_tts_edge(
    text: str,
    output_path: Path | str,
    voice: str = DEFAULT_VOICE,
) -> bool:
    """Genera audio a partir de texto utilizando edge-tts."""
    try:
        import edge_tts

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out))
        return True
    except Exception as e:
        print(f"⚠️ Error al usar edge-tts ({voice}): {e}")
        return False


def generate_tts_gtts(text: str, output_path: Path | str, lang: str = "es") -> bool:
    """Genera audio a partir de texto utilizando gTTS (respaldo)."""
    try:
        from gtts import gTTS

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tts = gTTS(text=text, lang=lang)
        tts.save(str(out))
        return True
    except Exception as e:
        print(f"❌ Error al usar gTTS: {e}")
        return False


async def generate_turn_audio(
    text: str,
    output_path: Path | str,
    voice: str = DEFAULT_VOICE,
) -> bool:
    """Genera audio para un turno de diálogo intentando edge-tts y haciendo fallback a gTTS."""
    out = Path(output_path)
    success = await generate_tts_edge(text, out, voice=voice)
    if not success:
        print(f"🔄 Intentando fallback con gTTS para {out.name}...")
        success = generate_tts_gtts(text, out)
    return success


def concatenate_audio_files(
    audio_files: Sequence[Path | str],
    output_path: Path | str,
) -> bool:
    """
    Concatena múltiples archivos de audio MP3 en uno solo utilizando ffmpeg.
    Si solo hay un archivo, se copia directamente.
    """
    paths = [Path(p) for p in audio_files]
    valid_files = [p for p in paths if p.exists() and p.stat().st_size > 0]
    if not valid_files:
        print("⚠️ No hay archivos de audio válidos para concatenar.")
        return False

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if len(valid_files) == 1:
        shutil.copyfile(valid_files[0], out)
        return True

    # Generar lista temporal de archivos para el concat demuxer de ffmpeg
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in valid_files:
            escaped = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        list_file = Path(f.name)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(out),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        print(f"❌ Error al concatenar audios con ffmpeg: {err_msg}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado al concatenar audios: {e}")
        return False
    finally:
        if list_file.exists():
            list_file.unlink(missing_ok=True)


async def generate_script_audio(
    yaml_path: str | Path,
    output_path: str | Path,
    *,
    turns_dir: Optional[str | Path] = None,
    default_voice: str = DEFAULT_VOICE,
) -> bool:
    """
    Procesa los bloques de diálogo del guion escena por escena:
    1. Asigna a cada personaje su voz correspondiente de Edge-TTS.
    2. Genera el audio individual para cada turno de diálogo.
    3. Concatena los turnos de cada escena en un audio por escena.
    4. Concatena los audios de todas las escenas en el archivo final del episodio.
    """
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        print(f"❌ Archivo de guion no encontrado: {yaml_file}")
        return False

    with open(yaml_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    scenes = data.get("scenes", [])
    if not scenes:
        print(f"❌ El guion no contiene escenas: {yaml_file}")
        return False

    final_output = Path(output_path).resolve()
    final_output.parent.mkdir(parents=True, exist_ok=True)

    if turns_dir is None:
        base_turns_dir = final_output.parent / f"{final_output.stem}_dialogues"
    else:
        base_turns_dir = Path(turns_dir).resolve()
    base_turns_dir.mkdir(parents=True, exist_ok=True)

    print(f"🎬 Iniciando síntesis multi-voz para {len(scenes)} escenas...")
    print(f"📂 Carpeta de turnos individuales: {base_turns_dir}")

    scene_audio_files: List[Path] = []

    for s_idx, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue

        scene_id = scene.get("id") or f"escena_{s_idx:02d}"
        scene_title = scene.get("title", f"Escena {s_idx}")
        dialogues = scene.get("dialogue") or scene.get("dialogues") or []

        scene_folder = base_turns_dir / scene_id
        scene_folder.mkdir(parents=True, exist_ok=True)
        scene_output = scene_folder / f"{scene_id}_consolidated.mp3"

        print(f"\n🎭 [{s_idx}/{len(scenes)}] {scene_id}: '{scene_title}'")

        if dialogues:
            turn_audio_files: List[Path] = []
            print(f"   💬 Procesando {len(dialogues)} turnos de diálogo...")

            for d_idx, d in enumerate(dialogues, 1):
                if not isinstance(d, dict):
                    continue
                char = d.get("character", "Personaje")
                voice_model = d.get("voice_model", "")
                text = (d.get("text") or "").strip()
                if not text:
                    continue

                voice = resolve_voice(character=char, voice_model=voice_model, default_voice=default_voice)
                safe_char = "".join(c for c in char if c.isalnum() or c in ("_", "-")).strip() or "char"
                turn_path = scene_folder / f"turn_{d_idx:02d}_{safe_char}.mp3"

                print(f"      Turno {d_idx:02d} | {char} ({voice_model}) -> voz: {voice} | {len(text)} car.")
                ok = await generate_turn_audio(text, turn_path, voice=voice)
                if not ok:
                    print(f"      ❌ Error generando audio para el turno {d_idx} ({char})")
                    return False

                turn_audio_files.append(turn_path)

            if not turn_audio_files:
                print(f"   ⚠️ Escena {scene_id} sin turnos de audio válidos.")
                continue

            print(f"   🔗 Concatenando {len(turn_audio_files)} turnos en: {scene_output.name}...")
            ok_concat = concatenate_audio_files(turn_audio_files, scene_output)
            if not ok_concat:
                print(f"   ❌ Falló la concatenación de la escena {scene_id}")
                return False

            scene_audio_files.append(scene_output)

        else:
            narration_text = (scene.get("narration") or scene.get("text") or "").strip()
            if narration_text:
                print(f"   🎙️ Generando narración unificada base: {len(narration_text)} caracteres")
                ok = await generate_turn_audio(narration_text, scene_output, voice=default_voice)
                if not ok:
                    print(f"   ❌ Error generando narración para la escena {scene_id}")
                    return False
                scene_audio_files.append(scene_output)
            else:
                print(f"   ⚠️ Escena {scene_id} sin diálogos ni texto. Omitiendo.")

    if not scene_audio_files:
        print("❌ No se generó ningún audio de escena válido.")
        return False

    print(f"\n📦 Ensamblando audio final del episodio desde {len(scene_audio_files)} escenas...")
    final_ok = concatenate_audio_files(scene_audio_files, final_output)
    if not final_ok:
        print(f"❌ Falló el ensamble del archivo final: {final_output}")
        return False

    print("=" * 65)
    print(f"✅ ¡Audio multi-voz generado con éxito!")
    print(f"🎙️ Archivo de audio final : {final_output}")
    print(f"📂 Turnos individuales en  : {base_turns_dir}")
    print("=" * 65)
    return True


def parse_yaml_text(yaml_path: Path | str) -> str:
    """Lee el archivo YAML del guion y extrae el texto consolidado de todas las escenas."""
    path = Path(yaml_path)
    if not path.exists():
        print(f"❌ Archivo de guion no encontrado: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    paragraphs: List[str] = []
    if isinstance(data, dict) and "scenes" in data:
        for scene in data["scenes"]:
            if isinstance(scene, dict):
                text_val = scene.get("narration") or scene.get("text")
                if text_val:
                    paragraphs.append(str(text_val).strip())
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                text_val = item.get("narration") or item.get("text")
                if text_val:
                    paragraphs.append(str(text_val).strip())

    return " ".join(paragraphs)


class TTSNarrator:
    """
    Generador de audio y metadatos de temporización desde texto.
    Mantiene compatibilidad con la suite de pruebas unitarias.
    """

    def generate_audio(self, text: str, output_path: str) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("El texto de la narración no puede estar vacío.")

        clean_text = re.sub(r"\s+", " ", text).strip()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Try edge-tts first to obtain precise word timings (if installed).
        words = []
        engine_used: Optional[str] = None
        try:
            result = asyncio.run(self._try_edge_tts(clean_text, output))
            if result:
                engine_used, words = result
        except Exception as exc:
            print(f"⚠️ edge-tts no disponible o falló ({exc}). Intentando otros motores.")

        # If edge-tts didn't produce audio, try other engines
        if not self._audio_file_is_valid(output):
            engine = self._try_native_tts(clean_text, output)
            if engine:
                engine_used = engine

        # If still no audio, fallback local synth
        if not self._audio_file_is_valid(output):
            print(f"⚠️ Advertencia: la síntesis TTS falló o no generó un archivo válido. Usando fallback local.")
            words = self._build_word_timestamps(clean_text)
            self._write_fallback_wav(clean_text, output, words)
            engine_used = "fallback"

        if not self._audio_file_is_valid(output):
            raise ValueError(f"El archivo de audio no se creó correctamente: {output}")

        phrases = self._build_phrase_timestamps(clean_text, words)
        duration = max((words[-1]["end"] if words else 0.0), 0.1)
        return {
            "audio_path": str(output),
            "engine": engine_used or "unknown",
            "words": words,
            "phrases": phrases,
            "duration": round(duration, 3),
        }

    def _try_native_tts(self, text: str, output_path: Path) -> Optional[str]:
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            if self._audio_file_is_valid(output_path):
                return "pyttsx3"
        except Exception as exc:
            print(f"⚠️ Advertencia: pyttsx3 falló ({exc}). Probando fallback TTS.")

        try:
            from gtts import gTTS  # type: ignore

            tts = gTTS(text=text, lang="es", slow=False)
            tts.save(str(output_path))
            if self._audio_file_is_valid(output_path):
                return "gtts"
        except Exception as exc:
            print(f"⚠️ Advertencia: gTTS falló ({exc}). Se usará voz sintética local.")

        return None

    def _write_fallback_wav(self, text: str, output_path: Path, words: List[Dict[str, Any]]) -> None:
        sample_rate = 44100
        total_duration = max(words[-1]["end"] if words else 0.0, 0.8)
        total_samples = int(sample_rate * total_duration)
        audio = [0.0] * total_samples

        for index, word_info in enumerate(words):
            start = float(word_info["start"])
            end = float(word_info["end"])
            duration = max(end - start, 0.15)
            segment_samples = int(sample_rate * duration)
            frequency = 180 + (index % 10) * 18

            for sample_index in range(segment_samples):
                t = sample_index / sample_rate
                envelope = min(1.0, t / 0.05) * (1.0 - max(0.0, (t - duration * 0.85) / (duration * 0.15)))
                value = 0.25 * envelope
                audio_index = int(sample_rate * start + sample_index)
                if 0 <= audio_index < total_samples:
                    audio[audio_index] += value

        scaled = [int(max(-32768, min(32767, v * 32767))) for v in audio]
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(int(v).to_bytes(2, byteorder="little", signed=True) for v in scaled))

    def _build_word_timestamps(self, text: str) -> List[Dict[str, float | str]]:
        words = re.findall(r"\b\w+\b", text)
        if not words:
            return [{"word": text, "start": 0.0, "end": 0.2}]

        timestamps: List[Dict[str, float | str]] = []
        cursor = 0.0
        for word in words:
            word_duration = max(0.18, min(0.8, 0.2 + len(word) * 0.05))
            start = cursor
            end = cursor + word_duration
            timestamps.append({"word": word, "start": round(start, 3), "end": round(end, 3)})
            cursor = end
        return timestamps

    def _build_phrase_timestamps(self, text: str, word_timestamps: List[Dict[str, Any]]) -> List[Dict[str, float | str]]:
        phrase_parts = re.split(r"(?<=[.!?])\s+|\s*[,;]\s*", text)
        phrase_parts = [part.strip() for part in phrase_parts if part and part.strip()]
        if not phrase_parts:
            return [{"text": text, "start": 0.0, "end": 0.2}]

        phrase_timestamps: List[Dict[str, float | str]] = []
        cursor = 0
        for phrase in phrase_parts:
            phrase_words = re.findall(r"\b\w+\b", phrase)
            phrase_duration = sum(float(item["end"]) - float(item["start"]) for item in word_timestamps[cursor:cursor + len(phrase_words)] or [])
            start = float(word_timestamps[cursor]["start"]) if cursor < len(word_timestamps) else 0.0
            end = start + max(phrase_duration, 0.2)
            phrase_timestamps.append({"text": phrase, "start": round(start, 3), "end": round(end, 3)})
            cursor += len(phrase_words)
        return phrase_timestamps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generador de Voz TTS Multi-Voz por Escena y Diálogo (Video Automation)"
    )
    parser.add_argument(
        "yaml_path",
        type=str,
        help="Ruta al archivo YAML del guion (ej. assets/source_scripts/GUION-02.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/output/audio_tts.mp3",
        help="Ruta del archivo MP3 final del episodio",
    )
    parser.add_argument(
        "--turns-dir",
        type=str,
        default=None,
        help="Directorio donde guardar los turnos individuales de diálogo",
    )
    parser.add_argument(
        "--voice",
        "-v",
        type=str,
        default=DEFAULT_VOICE,
        help="Voz Edge-TTS por defecto o fallback",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    success = asyncio.run(
        generate_script_audio(
            yaml_path=args.yaml_path,
            output_path=args.output,
            turns_dir=args.turns_dir,
            default_voice=args.voice,
        )
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
