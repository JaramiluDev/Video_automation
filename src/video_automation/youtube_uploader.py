import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
    API_SERVICE_NAME: str = "youtube"
    API_VERSION: str = "v3"

    def __init__(
        self,
        client_secrets_file: Optional[Union[str, Path]] = None,
        token_file: Optional[Union[str, Path]] = None,
        scopes: Optional[List[str]] = None,
        port: int = 8080,
        auto_authenticate: bool = True,
    ) -> None:
        self.scopes: List[str] = scopes or self.DEFAULT_SCOPES
        self.port: int = port
        self.client_secrets_file: Path = self._resolve_path(
            client_secrets_file, "client_secrets.json"
        )
        self.token_file: Path = self._resolve_path(
            token_file, "token.json", for_write=True
        )
        self.service: Optional[Resource] = None
        self.youtube: Optional[Resource] = None

        if auto_authenticate:
            self.authenticate()

    @staticmethod
    def _resolve_path(
        provided_path: Optional[Union[str, Path]],
        filename: str,
        for_write: bool = False,
    ) -> Path:
        if provided_path is not None:
            p = Path(provided_path)
            if p.is_file() or (for_write and p.parent.exists()):
                return p.resolve() if p.is_absolute() else p
            if p.name != str(provided_path) or p.is_absolute():
                return p

        candidates = [
            Path("/app/secrets") / filename,
            Path("secrets") / filename,
            Path("/app") / filename,
            Path(filename),
        ]

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve() if candidate.is_absolute() else candidate

        if provided_path is not None:
            return Path(provided_path)

        docker_secrets = Path("/app/secrets")
        if docker_secrets.is_dir():
            return docker_secrets / filename
        return Path("secrets") / filename

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
                    print("🔄 Refrescando token de acceso OAuth expirado...")
                    creds.refresh(Request())
                except RefreshError as e:
                    logger.warning("Token inválido o revocado (%s). Solicitando nueva autorización...", e)
                    print(f"⚠️ Token inválido o revocado ({e}). Solicitando nueva autorización...")
                    creds = None

            if not creds or not creds.valid:
                if not self.client_secrets_file.exists():
                    error_msg = (
                        f"❌ Error de autenticación: No se encontró el archivo de credenciales de cliente "
                        f"en '{self.client_secrets_file}'. Verifique que exista 'secrets/client_secrets.json' "
                        f"o '/app/secrets/client_secrets.json'."
                    )
                    logger.error(error_msg)
                    print(error_msg)
                    raise FileNotFoundError(error_msg)

                logger.info("Iniciando flujo OAuth desde %s", self.client_secrets_file)
                print(f"🔐 Iniciando flujo OAuth con '{self.client_secrets_file}'...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_file), self.scopes
                )
                creds = flow.run_local_server(port=self.port, open_browser=False)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())
            print(f"💾 Token de acceso almacenado en '{self.token_file}'.")

        self.service = build(self.API_SERVICE_NAME, self.API_VERSION, credentials=creds)
        self.youtube = self.service
        return self.service

    def upload_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Union[str, Path],
    ) -> Dict[str, Any]:
        service = self.service or self.authenticate()

        thumb_path = Path(thumbnail_path)
        if not thumb_path.is_file():
            candidates = [
                Path("/app/thumbnails") / thumb_path.name,
                Path("thumbnails") / thumb_path.name,
                Path("/app/data/thumbnails") / thumb_path.name,
                Path("data/thumbnails") / thumb_path.name,
            ]
            for c in candidates:
                if c.is_file():
                    thumb_path = c
                    break

        if not thumb_path.is_file():
            error_msg = (
                f"❌ Error: No se encontró el archivo de miniatura en '{thumb_path}' "
                f"(verificado también en '/app/thumbnails/' y 'thumbnails/')."
            )
            logger.error(error_msg)
            print(error_msg)
            raise FileNotFoundError(error_msg)

        mime_type = mimetypes.guess_type(str(thumb_path))[0] or "image/jpeg"
        media = MediaFileUpload(str(thumb_path), mimetype=mime_type, resumable=True)

        try:
            print(f"🖼️ Subiendo miniatura para video ID '{video_id}'...")
            request = service.thumbnails().set(videoId=video_id, media_body=media)
            response: Dict[str, Any] = request.execute()
            logger.info("Miniatura asignada exitosamente al video %s", video_id)
            print(f"✅ ¡Miniatura asignada exitosamente al video ID: {video_id}!")
            return response
        except HttpError as e:
            error_details = (
                e.content.decode("utf-8", errors="ignore")
                if isinstance(e.content, bytes)
                else str(e.content)
            )
            error_msg = f"❌ Error HTTP al asignar miniatura ({e.resp.status}): {error_details}"
            logger.error(error_msg)
            print(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"❌ Error inesperado al asignar miniatura: {e}"
            logger.error(error_msg)
            print(error_msg)
            raise RuntimeError(error_msg) from e

    def set_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Union[str, Path],
        youtube_service: Optional[Resource] = None,
    ) -> Optional[Dict[str, Any]]:
        """Intenta subir la miniatura de forma defensiva sin romper la ejecución principal."""
        if youtube_service:
            self.service = youtube_service
            self.youtube = youtube_service

        path_obj = Path(thumbnail_path)
        if not path_obj.exists():
            print(f"⚠️ Advertencia: No existe el archivo de miniatura en '{path_obj}'")
            return None

        try:
            print(f"🖼️ Intentando subir miniatura desde: {path_obj}")
            return self.upload_thumbnail(video_id=video_id, thumbnail_path=path_obj)

        except (HttpError, RuntimeError) as e:
            print(f"\n⚠️ [AVISO API YOUTUBE]")
            print("No se pudo subir la miniatura automáticamente.")
            print(f"📌 Detalle: {e}")
            print(f"👉 Solución manual: Sube '{path_obj}' en YouTube Studio.\n")
            return None

        except Exception as e:
            print(f"⚠️ Error inesperado al procesar la miniatura: {e}")
            return None

    def upload_video(
        self,
        title: str = "",
        description: str = "",
        file_path: Optional[Union[str, Path]] = None,
        thumbnail_path: Optional[Union[str, Path]] = None,
        tags: Optional[List[str]] = None,
        category_id: str = "27",
        privacy_status: str = "private",
        youtube_service: Optional[Resource] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        file_path = file_path or kwargs.get("video_path")
        thumbnail_path = thumbnail_path or kwargs.get("thumbnail") or kwargs.get("thumbnail_file")

        if file_path is None and isinstance(title, (str, Path)):
            title_as_path = Path(title)
            if title_as_path.is_file() or str(title).lower().endswith(
                (".mp4", ".mov", ".avi", ".mkv", ".webm")
            ):
                file_path = title
                title = description
                description = str(kwargs.get("extra_desc", ""))

        if not file_path:
            error_msg = "❌ Error: No se especificó ninguna ruta de archivo de video."
            logger.error(error_msg)
            print(error_msg)
            raise ValueError(error_msg)

        video_path = Path(file_path)
        if not video_path.is_file():
            error_msg = f"❌ Error: El archivo de video '{video_path}' no existe."
            logger.error(error_msg)
            print(error_msg)
            raise FileNotFoundError(error_msg)

        service = youtube_service or self.service or self.authenticate()

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
            print(f"🚀 Subiendo video '{title}' a YouTube...")
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

            # Uso defensivo de set_thumbnail para evitar crash en cuota HTTP 403
            if video_id and thumbnail_path:
                self.set_thumbnail(video_id=video_id, thumbnail_path=thumbnail_path)

            return response

        except HttpError as e:
            error_details = (
                e.content.decode("utf-8", errors="ignore")
                if isinstance(e.content, bytes)
                else str(e.content)
            )
            error_msg = f"❌ Error HTTP de la API de YouTube ({e.resp.status}): {error_details}"
            logger.error(error_msg)
            print(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"❌ Error inesperado al subir el video: {e}"
            logger.error(error_msg)
            print(error_msg)
            raise RuntimeError(error_msg) from e