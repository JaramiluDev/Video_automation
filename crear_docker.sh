cat << 'EOF' > .dockerignore
.venv/
.env
__pycache__/
*.pyc
data/renders/*
data/thumbnails/*
EOF

cat << 'EOF' > Dockerfile
FROM python:3.11-slim

# Instalar FFmpeg a nivel sistema operativo (necesario para moviepy)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar requerimientos de Python primero (aprovecha el caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Por defecto, mostrar la ayuda del CLI
CMD ["python", "-m", "src.video_automation.cli", "--help"]
EOF

cat << 'EOF' > docker-compose.yml
services:
  video-app:
    build: .
    # Mapeamos las carpetas de datos para que los renders se guarden en tu máquina host
    volumes:
      - ./data:/app/data
      - ./examples:/app/examples
    env_file:
      - .env
EOF

echo "¡Archivos de Docker generados con éxito!"
