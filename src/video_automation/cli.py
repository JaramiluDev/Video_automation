"""
Módulo de interfaz de línea de comandos (CLI) para Video Automation.
Permite validar guiones YAML y ejecutar el pipeline de renderizado de video.
"""

import argparse
from .pipeline import run_pipeline
from .script_parser import parse_script

def main():
    """Punto de entrada principal para la CLI."""
    # Configuración del parser principal de argumentos
    parser = argparse.ArgumentParser(description="Video Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # --- Subcomando: validate ---
    # Permite verificar la sintaxis y estructura de un guión YAML sin renderizar
    val_parser = subparsers.add_parser("validate", help="Valida el formato del guión YAML")
    val_parser.add_argument("--script", required=True, help="Ruta al script YAML")

    # --- Subcomando: render ---
    # Inicia el pipeline completo para generar el video a partir del guión
    ren_parser = subparsers.add_parser("render", help="Renderiza el video")
    ren_parser.add_argument("--script", required=True, help="Ruta al script YAML")
    ren_parser.add_argument("--output", default="data/renders", help="Directorio de salida")

    # Procesar los argumentos de la línea de comandos pasados por el usuario
    args = parser.parse_args()

    # Ejecución de la lógica según el subcomando proporcionado
    if args.command == "validate":
        # Valida el archivo YAML y muestra un resumen de las escenas si es correcto
        try:
            script = parse_script(args.script)
            print(f"✅ Guión '{script.title}' validado correctamente con {len(script.scenes)} escenas.")
        except Exception as e:
            print(f"❌ Error al validar: {e}")
    elif args.command == "render":
        # Ejecuta el flujo de renderizado del video y lo guarda en el directorio especificado
        run_pipeline(args.script, args.output)
    else:
        # Si no se pasó ningún comando o no es válido, muestra la ayuda de uso
        parser.print_help()

if __name__ == "__main__":
    # Permite la ejecución directa del script desde la terminal
    main()

