FROM python:3.11-slim

# Instalar FFmpeg (moviepy + quemado de subtítulos) y dependencias de
# sistema requeridas por Manim (LaTeX + Cairo/Pango para renderizar texto
# y curvas matemáticas).
RUN apt-get update && \
    apt-get install -y \
        ffmpeg \
        fonts-dejavu-core \
        fontconfig \
        libcairo2-dev \
        libpango1.0-dev \
        texlive \
        texlive-latex-extra \
        dvisvgm \
        build-essential \
        pkg-config \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar requerimientos de Python primero (aprovecha el caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Por defecto, mostrar la ayuda del CLI
CMD ["python", "-m", "src.video_automation.cli", "--help"]
