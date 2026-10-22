from pathlib import Path

class SubtitleGenerator:
    @staticmethod
    def _format_srt_timestamp(seconds: float) -> str:
        ms = int(round((seconds - int(seconds)) * 1000))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def export_srt(text_segments: list, output_path: str) -> bool:
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # UTF-8 vital para que no exploten los acentos y las ñ
            with open(output_path, 'w', encoding='utf-8') as file:
                for i, segment in enumerate(text_segments, start=1):
                    start_ts = SubtitleGenerator._format_srt_timestamp(float(segment['start']))
                    end_ts = SubtitleGenerator._format_srt_timestamp(float(segment['end']))
                    file.write(f"{i}\n")
                    file.write(f"{start_ts} --> {end_ts}\n")
                    file.write(f"{segment['text']}\n\n")
                    
            print(f"✅ Subtítulos exportados en: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Error al exportar subtítulos: {e}")
            return False