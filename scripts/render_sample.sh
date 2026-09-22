#!/bin/bash
if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
echo "Generando imagen de prueba temporal..."
python -c "from PIL import Image; Image.new('RGB', (1920, 1080), color = 'blue').save('data/assets/placeholder_1.png')"
echo "Corriendo renderizado..."
python -m src.video_automation.cli render --script examples/sample_script.yaml
