from pathlib import Path

from .compositor import compose_video
from .narrator import TTSNarrator
from .script_parser import parse_script
from .subtitles import SubtitleGenerator
from moviepy import AudioFileClip, concatenate_audioclips


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
            # Write per-scene SRT (word-level) and keep for a combined SRT
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

    output_file = output_root / script.output_filename
    compose_video(all_images, all_durations, str(output_file), fps=fps, resolution=resolution)

    # Merge per-scene srt segments into a single subtitles file aligned to
    # the composed timeline start. If requested, also create a single MP3.
    if include_audio and narrative_audio:
        subtitles_dir = output_root / "subtitles"
        subtitles_dir.mkdir(parents=True, exist_ok=True)
        combined_path = subtitles_dir / f"{Path(script.output_filename).stem}.srt"

        if combine_audio:
            # Build combined audio and remap word timestamps
            audio_clips = []
            combined_words = []
            cursor = 0.0
            for item in narrative_audio:
                clip = AudioFileClip(str(item["audio_path"]))
                audio_clips.append(clip)
                for w in item.get("words", []):
                    combined_words.append({"start": round(float(w["start"]) + cursor, 3), "end": round(float(w["end"]) + cursor, 3), "text": w["word"]})
                # Advance cursor by the duration of the clip for correct offsets
                cursor += float(item.get("duration", clip.duration))

            if audio_clips:
                final_audio = concatenate_audioclips(audio_clips)
                output_combined = output_root / "audio" / "combined.mp3"
                output_combined.parent.mkdir(parents=True, exist_ok=True)
                final_audio.write_audiofile(str(output_combined), codec="mp3")
                # Close clips
                for c in audio_clips:
                    c.close()

                # Export combined SRT using remapped combined_words
                SubtitleGenerator.export_srt(combined_words, str(combined_path))
                print(f"Audio combinado en: {output_combined}. Subtítulos combinados: {combined_path}")
            else:
                print("No hay clips de audio para combinar.")
        else:
            # Simple concatenation of per-scene SRT files
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

            print(f"Audio generado para {len(narrative_audio)} escenas. Carpeta: {output_root / 'audio'}. Subtítulos: {combined_path}")

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return str(output_file)
