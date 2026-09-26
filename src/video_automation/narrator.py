from __future__ import annotations

import math
import re
import wave
from pathlib import Path
from typing import Any


class TTSNarrator:
    """Generate audio and timing metadata from text using the best available engine.

    Strategy:
    1. Try a real TTS engine such as pyttsx3 when installed.
    2. Fallback to a generated WAV file when no engine is available.
    3. Always return word and phrase timestamps for timeline alignment.
    """

    def generate_audio(self, text: str, output_path: str) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("El texto de la narración no puede estar vacío.")

        clean_text = re.sub(r"\s+", " ", text).strip()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        words = self._build_word_timestamps(clean_text)
        phrases = self._build_phrase_timestamps(clean_text)

        engine = self._try_native_tts(clean_text, output)
        if engine is None or not output.exists() or output.stat().st_size == 0:
            self._write_fallback_wav(clean_text, output, words)
            engine = "fallback"

        duration = max((words[-1]["end"] if words else 0.0), 0.1)
        return {
            "audio_path": str(output),
            "engine": engine,
            "words": words,
            "phrases": phrases,
            "duration": round(duration, 3),
        }

    def _try_native_tts(self, text: str, output_path: Path) -> str | None:
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            if output_path.exists() and output_path.stat().st_size > 0:
                return "pyttsx3"
        except Exception:
            pass

        try:
            from gtts import gTTS  # type: ignore

            tts = gTTS(text=text, lang="es", slow=False)
            tts.save(str(output_path))
            if output_path.exists() and output_path.stat().st_size > 0:
                return "gtts"
        except Exception:
            pass

        return None

    def _write_fallback_wav(self, text: str, output_path: Path, words: list[dict[str, float | str]]) -> None:
        sample_rate = 22050
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
                value = math.sin(2 * math.pi * frequency * t) * 0.25 * envelope
                audio_index = int(sample_rate * start + sample_index)
                if 0 <= audio_index < total_samples:
                    audio[audio_index] += value

        scaled = []
        for value in audio:
            sample = max(-1.0, min(1.0, value))
            scaled.append(int(max(-32768, min(32767, sample * 32767))))

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(int(value).to_bytes(2, byteorder="little", signed=True) for value in scaled))

    def _build_word_timestamps(self, text: str) -> list[dict[str, float | str]]:
        words = re.findall(r"\b\w+\b", text)
        if not words:
            return [{"word": text, "start": 0.0, "end": 0.2}]

        timestamps = []
        cursor = 0.0
        for word in words:
            word_duration = max(0.18, min(0.8, 0.2 + len(word) * 0.05))
            start = cursor
            end = cursor + word_duration
            timestamps.append({"word": word, "start": round(start, 3), "end": round(end, 3)})
            cursor = end
        return timestamps

    def _build_phrase_timestamps(self, text: str) -> list[dict[str, float | str]]:
        phrase_parts = re.split(r"(?<=[.!?])\s+|\s*[,;]\s*", text)
        phrase_parts = [part.strip() for part in phrase_parts if part and part.strip()]
        if not phrase_parts:
            return [{"text": text, "start": 0.0, "end": 0.2}]

        all_words = self._build_word_timestamps(text)
        phrase_timestamps = []
        cursor = 0
        for phrase in phrase_parts:
            phrase_words = re.findall(r"\b\w+\b", phrase)
            phrase_duration = sum(float(item["end"]) - float(item["start"]) for item in all_words[cursor:cursor + len(phrase_words)] or [])
            start = float(all_words[cursor]["start"]) if cursor < len(all_words) else 0.0
            end = start + max(phrase_duration, 0.2)
            phrase_timestamps.append({"text": phrase, "start": round(start, 3), "end": round(end, 3)})
            cursor += len(phrase_words)
        return phrase_timestamps
