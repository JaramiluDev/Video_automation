import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import googleapiclient.discovery
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


class YouTubeUploader:
    DEFAULT_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/youtube.upload",
    ]
    API_SERVICE_NAME: str = "youtube"
    API_VERSION: str = "v3"

    def __init__(
        self,
        client_secrets_file: Union[str, Path] = "client_secrets.json",
        token_file: Union[str, Path] = "token.json",
        scopes: Optional[List[str]] = None,
        port: int = 8080,
    ) -> None:
        self.client_secrets_file: Path = Path(client_secrets_file)
        self.token_file: Path = Path(token_file)
        self.scopes: List[str] = scopes or self.DEFAULT_SCOPES
        self.port: int = port
        self.service: Optional[Resource] = None
        self.youtube: Optional[Resource] = None

        self.authenticate()

    def authenticate(self, force: bool = False) -> Resource:
        if self.service is not None and not force:
            return self.service

        creds: Optional[Credentials] = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_file), self.scopes
                )
            except Exception as e:
                logger.warning("Error leyendo token guardado (%s). Solicitando nuevo token...", e)
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Refrescando token de acceso expirado...")
                    print("🔄 Refrescando token de acceso expirado...")
                    creds.refresh(Request())
                except RefreshError as e:
                    logger.warning("Token inválido o revocado (%s). Solicitando nueva autorización...", e)
                    print(f"⚠️ Token inválido o revocado ({e}). Solicitando nueva autorización...")
                    creds = None

            if not creds or not creds.valid:
                if not self.client_secrets_file.exists():
                    raise FileNotFoundError(
                        f"No se encontró el archivo de credenciales de cliente: '{self.client_secrets_file}'"
                    )

                logger.info("Iniciando flujo OAuth desde %s", self.client_secrets_file)
                print(f"🔐 Iniciando flujo OAuth con '{self.client_secrets_file}'...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_file), self.scopes
                )
                creds = flow.run_local_server(port=self.port, open_browser=False)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())

        self.service = build(self.API_SERVICE_NAME, self.API_VERSION, credentials=creds)
        self.youtube = self.service
        return self.service

    def upload_video(
        self,
        title: str = "",
        description: str = "",
        file_path: Optional[Union[str, Path]] = None,
        tags: Optional[List[str]] = None,
        category_id: str = "27",
        privacy_status: str = "private",
        youtube_service: Optional[Resource] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        if file_path is None and isinstance(title, (str, Path)):
            title_as_path = Path(title)
            if title_as_path.is_file() or str(title).lower().endswith(
                (".mp4", ".mov", ".avi", ".mkv", ".webm")
            ):
                file_path = title
                title = description
                description = str(kwargs.get("extra_desc", ""))

        if not file_path:
            logger.error("No se especificó ninguna ruta de video.")
            print("❌ Error: No se especificó ninguna ruta de video.")
            return None

        video_path = Path(file_path)
        if not video_path.is_file():
            logger.error("El archivo de video no existe en '%s'.", video_path)
            print(f"❌ Error: El archivo de video '{video_path}' no existe.")
            return None

        service = youtube_service or self.service
        if service is None:
            service = self.authenticate()

        valid_privacy = ("private", "unlisted", "public")
        normalized_privacy = privacy_status.lower()
        if normalized_privacy not in valid_privacy:
            logger.warning(
                "Estado de privacidad '%s' inválido. Se utilizará 'private'.",
                privacy_status,
            )
            normalized_privacy = "private"

        body: Dict[str, Any] = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": normalized_privacy,
            },
        }

        try:
            print(f"🚀 Subiendo video: '{title}' a YouTube...")
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/*",
                resumable=True,
            )

            insert_request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response: Dict[str, Any] = insert_request.execute()
            video_id = response.get("id")
            logger.info("Video subido exitosamente. ID: %s", video_id)
            print(f"✅ ¡Video subido exitosamente! ID: {video_id}")
            return response

        except HttpError as e:
            error_details = (
                e.content.decode("utf-8", errors="ignore")
                if isinstance(e.content, bytes)
                else str(e.content)
            )
            logger.error("Error HTTP de YouTube API (%s): %s", e.resp.status, error_details)
            print(f"❌ Error HTTP de la API de YouTube ({e.resp.status}): {error_details}")
            return None
        except Exception as e:
            logger.error("Error inesperado al subir el video: %s", e)
            print(f"❌ Error inesperado al subir el video: {e}")
            return None

    def set_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Union[str, Path],
        youtube_service: Optional[Resource] = None,
    ) -> Optional[Dict[str, Any]]:
        service = youtube_service or self.service or self.authenticate()
        thumb_path = Path(thumbnail_path)
        if not thumb_path.is_file():
            logger.error("No se encontró la miniatura en '%s'.", thumb_path)
            print(f"❌ Error: No se encontró la miniatura en '{thumb_path}'.")
            return None

        try:
            media = MediaFileUpload(
                str(thumb_path), mimetype="image/jpeg", resumable=True
            )
            request = service.thumbnails().set(videoId=video_id, media_body=media)
            response: Dict[str, Any] = request.execute()
            print(f"✅ ¡Miniatura actualizada para el video {video_id}!")
            return response
        except Exception as e:
            logger.error("Error al asignar la miniatura: %s", e)
            print(f"❌ Error al asignar la miniatura: {e}")
            return None