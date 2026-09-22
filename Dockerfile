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
