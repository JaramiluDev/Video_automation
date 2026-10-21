from __future__ import annotations

import asyncio
import math
import re
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional


class TTSNarrator:
    """Generate audio and timing metadata from text using the best available engine.

    Strategy:
    - Prefer `edge_tts` when available to extract word-level timestamps.
    - Fall back to `pyttsx3` or `gtts` when present.
    - If no real TTS is available, synthesize a simple WAV as fallback.
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

    def _audio_file_is_valid(self, output: Path) -> bool:
        return output.exists() and output.stat().st_size > 0

    def _convert_to_seconds(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                value = float(value)
            except ValueError:
                return None
        if not isinstance(value, (int, float)):
            return None
        if value > 1_000_000_000:
            return float(value) / 10_000_000.0
        if value > 1_000:
            return float(value) / 1000.0
        return float(value)

    def _parse_word_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        word_events: List[Dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if "words" in event and isinstance(event["words"], list):
                word_events.extend(self._parse_word_events(event["words"]))
                continue

            text = (
                event.get("word")
                or event.get("Word")
                or event.get("text")
                or event.get("Text")
                or event.get("wordText")
                or event.get("word_text")
            )
            if text is None or str(text).strip() == "":
                continue

            offset = (
                event.get("offset")
                or event.get("Offset")
                or event.get("offsetInMs")
                or event.get("offsetInTicks")
                or event.get("audio_offset")
                or event.get("audioOffset")
            )
            duration = (
                event.get("duration")
                or event.get("Duration")
                or event.get("durationInMs")
                or event.get("durationInTicks")
                or event.get("word_duration")
                or event.get("wordDuration")
            )

            start_s = self._convert_to_seconds(offset)
            duration_s = self._convert_to_seconds(duration)
            if start_s is None:
                start_s = 0.0
            if duration_s is None:
                duration_s = 0.2

            cleaned_word = str(text).strip()
            if cleaned_word in {"", " ", "\n"}:
                continue
            word_events.append({
                "word": cleaned_word,
                "start": round(start_s, 3),
                "end": round(start_s + duration_s, 3),
            })

        # Remove duplicate or empty entries and keep strict ordering.
        unique: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in word_events:
            key = (item["word"], item["start"], item["end"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    async def _edge_stream_to_file(self, text: str, output_path: Path):
        """Internal helper that streams audio from edge-tts and yields events.

        Returns a tuple (word_events, wrote_audio)
        """
        try:
            import edge_tts
        except Exception as exc:
            raise RuntimeError("edge-tts is not installed") from exc

        communicate = edge_tts.Communicate(text)
        word_events: List[Dict[str, Any]] = []
        wrote_audio = False

        out_file = open(output_path, "wb")
        try:
            async for msg in communicate.stream():
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type") or msg.get("event")
                if mtype in ("AudioChunk", "audio"):
                    chunk = msg.get("data") or msg.get("audio") or msg.get("chunk")
                    if isinstance(chunk, bytes):
                        out_file.write(chunk)
                        wrote_audio = True
                elif mtype == "WordBoundary" or "offset" in msg or "duration" in msg or "word" in msg or "words" in msg:
                    word_events.extend(self._parse_word_events([msg]))
        finally:
            out_file.close()

        return word_events, wrote_audio

    async def _try_edge_tts_async(self, text: str, output_path: Path):
        try:
            events, wrote = await self._edge_stream_to_file(text, output_path)
            if wrote:
                return ("edge-tts", events)
            return None
        except Exception:
            return None

    def _try_edge_tts(self, text: str, output_path: Path) -> Optional[tuple[str, List[Dict[str, Any]]]]:
        try:
            return asyncio.run(self._try_edge_tts_async(text, output_path))
        except Exception:
            return None

    def _try_native_tts(self, text: str, output_path: Path) -> str | None:
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
