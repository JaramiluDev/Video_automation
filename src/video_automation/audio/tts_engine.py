from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Iterable, List, Sequence

import yaml

from video_automation.models import ScriptDefinition, Scene

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover - opcional en ambientes sin Google SDK
    service_account = None
    build = None


class AudioUnifiedEngine:
    """Genera un archivo de audio consolidado para un guion, con fallback local y en Google Sheets."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

    def generate(
        self,
        script_path: str | Path,
        output_path: str | Path,
        *,
        sheet_id: str | None = None,
        sheet_name: str = "Hoja1",
        credentials_file: str | None = None,
        title: str = "Guion importado",
    ) -> str:
        script = self._load_script(script_path, sheet_id=sheet_id, sheet_name=sheet_name, credentials_file=credentials_file, title=title)
        texts = [scene.narration.strip() for scene in script.scenes if scene.narration and scene.narration.strip()]
        if not texts:
            raise ValueError("El guion no contiene narraciones válidas para sintetizar audio.")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        temp_dir = Path(tempfile.mkdtemp(prefix="audio_unified_"))
        wav_segments: list[Path] = []

        try:
            for index, text in enumerate(texts, start=1):
                segment_path = temp_dir / f"segment_{index:02d}.wav"
                self._render_text_to_wav(text, segment_path)
                wav_segments.append(segment_path)

            merged_wav = temp_dir / "merged.wav"
            self._merge_wavs(wav_segments, merged_wav)
            self._convert_wav_to_mp3(merged_wav, output_file)
            return str(output_file)
        finally:
            for segment in wav_segments:
                if segment.exists():
                    segment.unlink(missing_ok=True)
            if (temp_dir / "merged.wav").exists():
                (temp_dir / "merged.wav").unlink(missing_ok=True)

    def _load_script(
        self,
        script_path: str | Path,
        *,
        sheet_id: str | None,
        sheet_name: str,
        credentials_file: str | None,
        title: str,
    ) -> ScriptDefinition:
        if sheet_id:
            try:
                return self._load_script_from_google_sheet(sheet_id, sheet_name=sheet_name, credentials_file=credentials_file, title=title)
            except Exception:
                pass

        local_path = self._resolve_script_path(script_path)
        with open(local_path, "r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
        return ScriptDefinition(**payload)

    def _resolve_script_path(self, script_path: str | Path) -> Path:
        path = Path(script_path)
        if path.is_dir():
            candidates = [
                path / "script.yaml",
                path / "script.yml",
                path / "guion.yaml",
                path / "guion.yml",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
            yaml_files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
            if yaml_files:
                return yaml_files[0]
            raise FileNotFoundError(f"No se encontró ningún archivo YAML válido en: {path}")

        if not path.exists():
            raise FileNotFoundError(f"El guion no existe: {path}")
        return path

    def _load_script_from_google_sheet(
        self,
        sheet_id: str,
        *,
        sheet_name: str,
        credentials_file: str | None,
        title: str,
    ) -> ScriptDefinition:
        if service_account is None or build is None:
            raise RuntimeError("La librería de Google no está disponible.")

        credentials_path = credentials_file or os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path is None:
            raise RuntimeError("No hay credenciales de Google configuradas.")

        credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        service = build("sheets", "v4", credentials=credentials)
        payload = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=sheet_name).execute()
        rows = payload.get("values", [])
        if not rows:
            raise ValueError("La hoja de Google está vacía.")

        headers = [str(value).strip() for value in rows[0]]
        scene_rows = []
        for row in rows[1:]:
            if not row or all(not str(cell).strip() for cell in row):
                continue
            record = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
            narration = record.get("Texto", record.get("Narration", record.get("texto", record.get("Guion", ""))))
            title_value = record.get("Título", record.get("Title", record.get("titulo", "Escena")))
            duration = record.get("Duración", record.get("Duration", record.get("duracion", "2.0")))

            if not narration:
                continue
            try:
                seconds = float(str(duration).replace(",", "."))
            except ValueError:
                seconds = 2.0
            scene_rows.append(
                Scene(
                    id=f"ESCENA-{len(scene_rows) + 1:02d}",
                    title=str(title_value).strip() or f"Escena {len(scene_rows) + 1}",
                    narration=str(narration).strip(),
                    image_paths=["data/assets/placeholder_1.png"],
                    duration=max(seconds, 0.1),
                    voice="default",
                )
            )

        if not scene_rows:
            raise ValueError("No se encontraron escenas válidas en la hoja de Google.")

        return ScriptDefinition(title=title, scenes=scene_rows, output_filename="guion_importado.mp4")

    def _render_text_to_wav(self, text: str, output_path: Path) -> Path:
        text = " ".join(text.split()).strip()
        if not text:
            raise ValueError("El texto no puede estar vacío.")

        try:
            from gtts import gTTS

            temp_mp3 = output_path.with_suffix(".mp3")
            gTTS(text=text, lang="es", slow=False).save(str(temp_mp3))
            if shutil.which("ffmpeg"):
                subprocess.run([
                    shutil.which("ffmpeg"),
                    "-y",
                    "-i",
                    str(temp_mp3),
                    "-ar",
                    str(self.sample_rate),
                    str(output_path),
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                temp_mp3.unlink(missing_ok=True)
                return output_path
        except Exception:
            pass

        self._write_synthetic_wav(text, output_path)
        return output_path

    def _write_synthetic_wav(self, text: str, output_path: Path) -> None:
        duration = max(0.8, len(text) * 0.09)
        total_samples = int(self.sample_rate * duration)
        frames = []

        for index in range(total_samples):
            t = index / self.sample_rate
            base = 150 + (index % 11) * 18
            drift = 30 * math.sin(2 * math.pi * 0.2 * t)
            freq = base + drift + (len(text) % 10) * 10
            envelope = min(1.0, t / 0.05) * (1.0 - max(0.0, (t - duration * 0.8) / (duration * 0.2)))
            value = math.sin(2 * math.pi * freq * t) * 0.25 * envelope
            sample = max(-1.0, min(1.0, value))
            frames.append(int(sample * 32767))

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(b"".join(int(sample).to_bytes(2, byteorder="little", signed=True) for sample in frames))

    def _merge_wavs(self, wav_paths: Sequence[Path], output_path: Path) -> None:
        if not wav_paths:
            raise ValueError("No hay segmentos de audio para consolidar.")

        with wave.open(str(wav_paths[0]), "rb") as first:
            sample_rate = first.getframerate()
            channels = first.getnchannels()
            sample_width = first.getsampwidth()
            merged = []
            for path in wav_paths:
                with wave.open(str(path), "rb") as wav_file:
                    merged.append(wav_file.readframes(wav_file.getnframes()))

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(merged))

    def _convert_wav_to_mp3(self, wav_path: Path, output_mp3: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg no está instalado; no es posible convertir el audio a MP3.")

        subprocess.run([
            ffmpeg,
            "-y",
            "-i",
            str(wav_path),
            "-ar",
            str(self.sample_rate),
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_mp3),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def generate_audio_for_script(
    script_path: str | Path,
    output_path: str | Path,
    *,
    sheet_id: str | None = None,
    sheet_name: str = "Hoja1",
    credentials_file: str | None = None,
    title: str = "Guion importado",
) -> str:
    return AudioUnifiedEngine().generate(
        script_path=script_path,
        output_path=output_path,
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        credentials_file=credentials_file,
        title=title,
    )
