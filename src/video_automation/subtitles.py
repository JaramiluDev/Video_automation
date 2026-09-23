from pathlib import Path

class SubtitleGenerator:
    @staticmethod
    def export_srt(text_segments: list, output_path: str) -> bool:
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # UTF-8 vital para que no exploten los acentos y las ñ
            with open(output_path, 'w', encoding='utf-8') as file:
                for i, segment in enumerate(text_segments, start=1):
                    file.write(f"{i}\n")
                    file.write(f"{segment['start']} --> {segment['end']}\n")
                    file.write(f"{segment['text']}\n\n")
                    
            print(f"✅ Subtítulos exportados en: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Error al exportar subtítulos: {e}")
            return False