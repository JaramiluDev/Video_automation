from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from googleapiclient.errors import HttpError
import httplib2

from src.video_automation.youtube_uploader import YouTubeUploader


def test_scopes():
    expected_scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
    assert YouTubeUploader.DEFAULT_SCOPES == expected_scopes


def test_missing_credentials_raises_error(tmp_path):
    missing_secrets = tmp_path / "subdir" / "missing_client_secrets.json"
    missing_token = tmp_path / "subdir" / "missing_token.json"

    with pytest.raises(FileNotFoundError) as exc_info:
        YouTubeUploader(
            client_secrets_file=missing_secrets,
            token_file=missing_token,
        )
    assert "No se encontró el archivo de credenciales de cliente" in str(exc_info.value)


@patch("src.video_automation.youtube_uploader.build")
@patch("src.video_automation.youtube_uploader.Credentials")
def test_authentication_with_token(mock_creds_cls, mock_build, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "dummy"}')
    client_secrets = tmp_path / "client_secrets.json"
    client_secrets.write_text('{"installed": {}}')

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds

    uploader = YouTubeUploader(
        client_secrets_file=client_secrets,
        token_file=token_file,
    )

    mock_creds_cls.from_authorized_user_file.assert_called_once_with(
        str(token_file), uploader.scopes
    )
    mock_build.assert_called_once_with("youtube", "v3", credentials=mock_creds)
    assert uploader.service is not None


@patch("src.video_automation.youtube_uploader.build")
@patch("src.video_automation.youtube_uploader.Credentials")
@patch("src.video_automation.youtube_uploader.MediaFileUpload")
def test_upload_thumbnail_success(mock_media_cls, mock_creds_cls, mock_build, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "dummy"}')
    client_secrets = tmp_path / "client_secrets.json"
    client_secrets.write_text('{"installed": {}}')

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    uploader = YouTubeUploader(
        client_secrets_file=client_secrets,
        token_file=token_file,
    )

    # Missing file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        uploader.upload_thumbnail(video_id="video123", thumbnail_path=tmp_path / "missing.jpg")

    thumb_path = tmp_path / "cover.jpg"
    thumb_path.write_bytes(b"\xff\xd8\xff\xe0")

    mock_thumbnails_res = MagicMock()
    mock_set_req = MagicMock()
    mock_set_req.execute.return_value = {"kind": "youtube#thumbnailSetResponse"}
    mock_thumbnails_res.set.return_value = mock_set_req
    mock_service.thumbnails.return_value = mock_thumbnails_res

    res = uploader.upload_thumbnail(video_id="video123", thumbnail_path=thumb_path)
    assert res == {"kind": "youtube#thumbnailSetResponse"}
    mock_service.thumbnails().set.assert_called_once()


@patch("src.video_automation.youtube_uploader.build")
@patch("src.video_automation.youtube_uploader.Credentials")
@patch("src.video_automation.youtube_uploader.MediaFileUpload")
def test_upload_thumbnail_http_error(mock_media_cls, mock_creds_cls, mock_build, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "dummy"}')
    client_secrets = tmp_path / "client_secrets.json"
    client_secrets.write_text('{"installed": {}}')

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    uploader = YouTubeUploader(
        client_secrets_file=client_secrets,
        token_file=token_file,
    )

    thumb_path = tmp_path / "cover.jpg"
    thumb_path.write_bytes(b"\xff\xd8\xff\xe0")

    mock_set_req = MagicMock()
    http_resp = httplib2.Response({"status": 403})
    mock_set_req.execute.side_effect = HttpError(resp=http_resp, content=b"Forbidden")
    mock_service.thumbnails().set.return_value = mock_set_req

    with pytest.raises(RuntimeError) as exc_info:
        uploader.upload_thumbnail(video_id="video123", thumbnail_path=thumb_path)
    assert "Error HTTP al asignar miniatura (403)" in str(exc_info.value)


@patch("src.video_automation.youtube_uploader.build")
@patch("src.video_automation.youtube_uploader.Credentials")
@patch("src.video_automation.youtube_uploader.MediaFileUpload")
def test_upload_video_with_thumbnail(mock_media_cls, mock_creds_cls, mock_build, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "dummy"}')
    client_secrets = tmp_path / "client_secrets.json"
    client_secrets.write_text('{"installed": {}}')

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    uploader = YouTubeUploader(
        client_secrets_file=client_secrets,
        token_file=token_file,
    )

    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"fake-video-bytes")

    thumb_file = tmp_path / "sample.jpg"
    thumb_file.write_bytes(b"fake-thumb-bytes")

    mock_insert_req = MagicMock()
    mock_insert_req.execute.return_value = {"id": "vid999"}
    mock_service.videos().insert.return_value = mock_insert_req

    with patch.object(uploader, "upload_thumbnail") as mock_thumb_method:
        res = uploader.upload_video(
            title="Video Test",
            file_path=video_file,
            thumbnail_path=thumb_file,
        )
        assert res == {"id": "vid999"}
        mock_thumb_method.assert_called_once_with(video_id="vid999", thumbnail_path=thumb_file)
