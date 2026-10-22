from pathlib import Path

from .compositor import compose_video
from .narrator import TTSNarrator
from .script_parser import parse_script
from .subtitles import SubtitleGenerator
from moviepy import AudioFileClip, VideoFileClip, concatenate_audioclips


def _resolve_project_path(value: str | Path, project_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate

    for base in (project_root, Path("/app"), Path.cwd()):
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return resolved
    return (project_root / candidate).resolve()


def validate_scene_assets(script, project_root: str | Path | None = None, output_dir: str | Path | None = None) -> None:
    """Valida la estructura Docker, las imagenes por escena y el directorio de salida antes del render."""
    base_root = Path(project_root) if project_root is not None else Path.cwd()

    if not getattr(script, "scenes", None):
        raise ValueError("El guion no tiene escenas para renderizar.")

    if len(script.scenes) >= 10:
        expected_ids = {f"ESCENA-{idx:02d}" for idx in range(1, 13)}
        scene_ids = {str(scene.id).upper() for scene in script.scenes}
        missing = sorted(expected_ids - scene_ids)
        if missing:
            raise ValueError(f"Faltan escenas obligatorias para el render: {', '.join(missing)}")

    for scene in script.scenes:
        if not getattr(scene, "image_paths", None):
            raise ValueError(f"La escena {scene.id} no tiene imagenes cargadas para renderizar.")

        for img in scene.image_paths:
            candidate = _resolve_project_path(img, base_root)
            if not candidate.exists():
                raise ValueError(f"La escena {scene.id} referencia una imagen inexistente: {img}")

    if output_dir is not None:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        for child in ("audio", "subtitles", "renders"):
            (output_root / child).mkdir(parents=True, exist_ok=True)

        if script.audio_path:
            audio_path = _resolve_project_path(script.audio_path, base_root)
            if not audio_path.exists():
                raise ValueError(f"El audio consolidado no existe: {audio_path}")


def validate_render_audio_match(video_path: str | Path, audio_path: str | Path, tolerance: float = 1.0) -> None:
    """Garantiza que el video final tenga la misma duracion que el audio consolidado antes de subirlo."""
    video_file = Path(video_path)
    audio_file = Path(audio_path)

    if not video_file.exists():
        raise ValueError(f"No existe el video final para validar: {video_file}")
    if not audio_file.exists():
        raise ValueError(f"No existe el audio para validar el render: {audio_file}")

    with VideoFileClip(str(video_file)) as video_clip:
        with AudioFileClip(str(audio_file)) as audio_clip:
            diff = abs(video_clip.duration - audio_clip.duration)
            if diff > tolerance:
                raise ValueError(
                    f"El video final no coincide con la duración del audio: "
                    f"video={video_clip.duration:.2f}s, audio={audio_clip.duration:.2f}s, diferencia={diff:.2f}s"
                )

    return None


def run_pipeline(script_path: str, output_dir: str, fps: int = 30, resolution: str = "1920x1080", include_audio: bool = True, combine_audio: bool = False) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)

    all_images = []
    all_durations = []
    narrative_audio = []

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    for scene in script.scenes:
        for img in scene.image_paths:
            all_images.append(img)
            all_durations.append(scene.duration / len(scene.image_paths))

        if include_audio and scene.narration.strip():
            audio_output = output_root / "audio" / f"{scene.id}.wav"
            audio_output.parent.mkdir(parents=True, exist_ok=True)
            narration_result = TTSNarrator().generate_audio(scene.narration, str(audio_output))
            generated_path = Path(narration_result["audio_path"])
            if not generated_path.exists() or generated_path.stat().st_size == 0:
                raise ValueError(f"El archivo de audio no se creó correctamente para la escena {scene.id}: {generated_path}")
            words = narration_result.get("words", [])
            srt_segments = []
            for w in words:
                srt_segments.append({"start": w["start"], "end": w["end"], "text": w["word"]})
            srt_path = output_root / "audio" / f"{scene.id}.srt"
            SubtitleGenerator.export_srt(srt_segments, str(srt_path))

            narrative_audio.append({
                "scene_id": scene.id,
                "audio_path": narration_result["audio_path"],
                "duration": narration_result["duration"],
                "srt_path": str(srt_path),
                "words": words,
            })

    validate_scene_assets(script, project_root=Path.cwd(), output_dir=output_root)

    output_file = output_root / script.output_filename
    compose_video(all_images, all_durations, str(output_file), fps=fps, resolution=resolution)

    if include_audio:
        combined_audio = output_root / "audio" / "combined.mp3"
        if combined_audio.exists():
            validate_render_audio_match(output_file, combined_audio, tolerance=1.0)
        elif narrative_audio:
            expected_total = sum(float(item.get("duration", 0.0)) for item in narrative_audio)
            with VideoFileClip(str(output_file)) as video_clip:
                if abs(video_clip.duration - expected_total) > 1.0:
                    raise ValueError(
                        f"El render final no coincide con la duración acumulada del audio: "
                        f"video={video_clip.duration:.2f}s, audio={expected_total:.2f}s"
                    )

    if include_audio and narrative_audio:
        subtitles_dir = output_root / "subtitles"
        subtitles_dir.mkdir(parents=True, exist_ok=True)
        combined_path = subtitles_dir / f"{Path(script.output_filename).stem}.srt"

        if combine_audio:
            audio_clips = []
            combined_words = []
            cursor = 0.0
            for item in narrative_audio:
                clip = AudioFileClip(str(item["audio_path"]))
                audio_clips.append(clip)
                for w in item.get("words", []):
                    combined_words.append({"start": round(float(w["start"]) + cursor, 3), "end": round(float(w["end"]) + cursor, 3), "text": w["word"]})
                cursor += float(item.get("duration", clip.duration))

            if audio_clips:
                final_audio = concatenate_audioclips(audio_clips)
                output_combined = output_root / "audio" / "combined.mp3"
                output_combined.parent.mkdir(parents=True, exist_ok=True)
                final_audio.write_audiofile(str(output_combined), codec="mp3")
                for c in audio_clips:
                    c.close()

                SubtitleGenerator.export_srt(combined_words, str(combined_path))
                print(f"Audio combinado en: {output_combined}. Subtitulos combinados: {combined_path}")
            else:
                print("No hay clips de audio para combinar.")
        else:
            all_text = []
            for item in narrative_audio:
                try:
                    text = Path(item["srt_path"]).read_text(encoding="utf-8")
                    all_text.append(text)
                except Exception:
                    pass
            with open(combined_path, "w", encoding="utf-8") as outf:
                for piece in all_text:
                    outf.write(piece)

            print(f"Audio generado para {len(narrative_audio)} escenas. Carpeta: {output_root / 'audio'}. Subtitulos: {combined_path}")

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return str(output_file)
