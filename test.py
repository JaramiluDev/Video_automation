from src.video_automation.script_parser import parse_script

# Apuntamos a tu guión de ejemplo (asegúrate de que la ruta exista)
ruta_yaml = "examples/sample_script.yaml"

print(f"🚀 Iniciando prueba del parser con el archivo: {ruta_yaml}")

try:
    # Llamamos a tu función recién horneada
    resultado = parse_script(ruta_yaml)
    print("✅ ¡Éxito, papá! El YAML se leyó y se validó perfecto. Esto es lo que trajo:")
    print(resultado)
except Exception as e:
    print(f"❌ Tronó algo we, revisa este error: {e}")