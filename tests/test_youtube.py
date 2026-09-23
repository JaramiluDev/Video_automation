import os
from src.video_automation.youtube_uploader import YouTubeUploader

def main():
    print("Iniciando prueba de YouTube API...")
    uploader = YouTubeUploader('client_secrets.json')
    youtube_service = uploader.authenticate()
    print("✅ ¡Autenticación perrona! Conexión exitosa con YouTube.")

    # --- NUEVO CÓDIGO PARA PROBAR LA SUBIDA ---
    video_path = "data/test.mp4"
    
    if not os.path.exists(video_path):
        print(f"⚠️ ¡Ojo! No encontré ningún video en '{video_path}'. Mete un MP4 ahí para calar la subida.")
        return

    print(f"Arrancando motores para subir {video_path}...")
    
    # Llamamos al método que ya tienes programado
    uploader.upload_video(
        youtube_service=youtube_service,
        file_path=video_path,
        title="Prueba de Automatización - Sprint 5",
        description="Este es un video de prueba subido 100% desde Python y Docker. ¡El pipeline está vivo!",
        tags=["prueba", "automatizacion", "python", "docker"],
        category_id="27" # 27 es la categoría de Educación en YouTube
    )

if __name__ == "__main__":
    main()