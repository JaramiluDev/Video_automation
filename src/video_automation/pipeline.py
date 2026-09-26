from .script_parser import parse_script
from .heavy_render import render_video

def run_pipeline(script_path: str, output_dir: str) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)

    output_file = render_video(script, output_dir)

    print(f"Pipeline completado. Video guardado en: {output_file}")
    return output_file
