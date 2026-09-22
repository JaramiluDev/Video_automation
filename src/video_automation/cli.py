import argparse
from .pipeline import run_pipeline
from .script_parser import parse_script

def main():
    parser = argparse.ArgumentParser(description="Video Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    val_parser = subparsers.add_parser("validate", help="Valida el formato del guión YAML")
    val_parser.add_argument("--script", required=True, help="Ruta al script YAML")

    ren_parser = subparsers.add_parser("render", help="Renderiza el video")
    ren_parser.add_argument("--script", required=True, help="Ruta al script YAML")
    ren_parser.add_argument("--output", default="data/renders", help="Directorio de salida")

    args = parser.parse_args()

    if args.command == "validate":
        try:
            script = parse_script(args.script)
            print(f"✅ Guión '{script.title}' validado correctamente con {len(script.scenes)} escenas.")
        except Exception as e:
            print(f"❌ Error al validar: {e}")
    elif args.command == "render":
        run_pipeline(args.script, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
