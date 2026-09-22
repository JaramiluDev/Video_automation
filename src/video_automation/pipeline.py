from pathlib import Path
from .script_parser import parse_script
from .compositor import compose_video

def run_pipeline(script_path: str, output_dir: str) -> str:
    print(f"Iniciando pipeline para: {script_path}")
    script = parse_script(script_path)
    
    all_images = []
    all_durations = []
    
    for scene in script.scenes:
        for img in scene.image_paths:
            all_images.append(img)
            all_durations.append(scene.duration / len(scene.image_paths))
            
    output_file = Path(output_dir) / script.output_filename
    compose_video(all_images, all_durations, str(output_file))
    print(f"Pipeline completado. Video guardado en: {output_file}")
    return str(output_file)
