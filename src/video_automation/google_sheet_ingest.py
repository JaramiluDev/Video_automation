import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .script_parser import parse_script
from .models import ScriptDefinition, Scene


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("\n", " ").replace("_", " ")


def _find_value(row: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    aliases = tuple(_normalize_header(alias) for alias in aliases)
    for key, value in row.items():
        if _normalize_header(key) in aliases:
            return value
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


def rows_to_script_definition(rows: Iterable[Mapping[str, Any]], title: str = "Guion importado desde Google Sheets", output_filename: str = "guion_importado.mp4") -> ScriptDefinition:
    scene_rows = []

    for index, row in enumerate(rows, start=1):
        if not row:
            continue
        scene_id = _find_value(row, ["Número de Escena", "Numero de Escena", "Scene Number", "scene_number", "Escena", "scene"])
        narration = _find_value(row, ["Texto a Narrar", "Texto", "Narration", "Narrativo", "Guion", "texto narrado"])
        image_value = _find_value(row, ["Archivo de Imagen/Animación", "Archivo de Imagen", "Imagen", "Archivo", "Image Path", "image_path", "Archivo de Video"])
        duration = _find_value(row, ["Duración (segundos)", "Duracion (segundos)", "Duración", "Duration", "duracion", "duración"])
        scene_title = _find_value(row, ["Título de la Escena", "Titulo de la Escena", "Title", "titulo", "nombre de la escena"])
        voice = _find_value(row, ["Voz", "Voice", "voice"])

        if narration is None and not any(cell is not None for cell in row.values()):
            continue

        file_path = image_value
        if isinstance(file_path, str):
            image_paths = [p.strip() for p in file_path.split("|") if p.strip()]
        elif file_path is None:
            image_paths = []
        else:
            image_paths = [str(file_path)]

        scene_number = index
        if scene_id not in (None, ""):
            try:
                scene_number = int(str(scene_id).strip())
            except ValueError:
                scene_number = index

        normalized_duration = 2.0
        if duration not in (None, ""):
            try:
                normalized_duration = float(str(duration).replace(",", "."))
            except ValueError:
                normalized_duration = 2.0

        scene_title_value = str(scene_title).strip() if scene_title not in (None, "") else f"Escena {scene_number}"
        narration_value = str(narration).strip() if narration not in (None, "") else ""

        if not narration_value:
            continue

        scene_rows.append(
            Scene(
                id=f"ESCENA-{scene_number:02d}",
                title=scene_title_value,
                narration=narration_value,
                image_paths=image_paths or ["data/assets/placeholder_1.png"],
                duration=max(normalized_duration, 0.1),
                voice=str(voice).strip() if voice not in (None, "") else "default",
            )
        )

    if not scene_rows:
        raise ValueError("No se encontraron escenas válidas en la hoja de cálculo.")

    return ScriptDefinition(
        title=title,
        scenes=scene_rows,
        output_filename=output_filename,
    )


def _get_google_credentials(credentials_path: str | None = None, credentials_json: str | None = None):
    if credentials_json:
        info = json.loads(credentials_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    configured_path = credentials_path or os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
        raise FileNotFoundError(f"No se encontró el archivo de credenciales: {configured_path}")

    raise FileNotFoundError(
        "No hay credenciales de Google configuradas. Define GOOGLE_SHEETS_CREDENTIALS_FILE o GOOGLE_APPLICATION_CREDENTIALS."
    )


def read_sheet_rows(sheet_id: str, sheet_name: str = "Hoja1", credentials_path: str | None = None, credentials_json: str | None = None):
    credentials = _get_google_credentials(credentials_path=credentials_path, credentials_json=credentials_json)
    service = build("sheets", "v4", credentials=credentials)
    result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=sheet_name).execute()
    rows = result.get("values", [])
    if not rows:
        return []

    headers = rows[0]
    data_rows = []
    for row in rows[1:]:
        if not row or all(not str(cell).strip() for cell in row):
            continue
        data_rows.append({headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))})

    return data_rows


def load_script_from_google_sheet(
    sheet_id: str,
    sheet_name: str = "Hoja1",
    *,
    title: str = "Guion importado desde Google Sheets",
    output_filename: str = "guion_importado.mp4",
    local_fallback: str | None = None,
    google_credentials_path: str | None = None,
    google_credentials_json: str | None = None,
) -> ScriptDefinition:
    if not sheet_id:
        raise ValueError("Debes indicar un Google Sheet id válido.")

    try:
        rows = read_sheet_rows(
            sheet_id=sheet_id,
            sheet_name=sheet_name,
            credentials_path=google_credentials_path,
            credentials_json=google_credentials_json,
        )
        return rows_to_script_definition(rows, title=title, output_filename=output_filename)
    except Exception as exc:
        fallback_path = local_fallback or os.getenv("LOCAL_FALLBACK_SCRIPT") or "examples/sample_script.yaml"
        fallback_file = Path(fallback_path)

        if not fallback_file.exists():
            raise RuntimeError(
                f"No se pudo leer la hoja de Google y no hay fallback local disponible: {exc}"
            ) from exc

        print(f"⚠️ Google Sheets no disponible ({exc}). Usando fallback local: {fallback_file}")
        return parse_script(str(fallback_file))
