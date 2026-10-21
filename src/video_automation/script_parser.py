"""
Módulo de parseo y conversión de guiones para el Video Automation Pipeline.

Permite:
- Parsear archivos YAML existentes a objetos ScriptDefinition validados con Pydantic.
- Extraer escenas y diálogos estructurados por personaje (DETECTIVE, AGENTE CERO, ANA) desde documentos DOCX.
- Convertir guiones DOCX a especificaciones YAML compatibles con el pipeline de narración y TTS multi-voz.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

from .models import ScriptDefinition

VOICE_MAPPING_DEFAULT = {
    "DETECTIVE": {"character": "Detective", "voice_model": "DrSimi"},
    "AGENTE CERO": {"character": "AgenteCero", "voice_model": "PersonajeVaronil2"},
    "ANA": {"character": "Ana", "voice_model": "PersonajeFemenino"},
}


class IndentedDumper(yaml.SafeDumper):
    """Dumper de PyYAML que asegura sangría uniforme en listas anidadas."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        return super().increase_indent(flow, False)


def iter_document_texts(docx_path: str | Path) -> Iterator[str]:
    """
    Itera sobre todos los párrafos de un documento DOCX en orden de lectura secuencial,
    incluyendo párrafos del cuerpo principal y celdas de tablas.
    
    Utiliza python-docx cuando está disponible, o un fallback nativo a zipfile + XML.
    """
    docx_file = Path(docx_path)
    if not docx_file.exists():
        raise FileNotFoundError(f"Error: El archivo DOCX {docx_file} no existe.")

    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(str(docx_file))
        for child in doc.element.body:
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, doc).text.strip()
                if text:
                    yield text
            elif tag == "tbl":
                tbl = Table(child, doc)
                for row in tbl.rows:
                    seen_tc = set()
                    for cell in row.cells:
                        if cell._tc in seen_tc:
                            continue
                        seen_tc.add(cell._tc)
                        for cp in cell.paragraphs:
                            ct = cp.text.strip()
                            if ct:
                                yield ct
        return
    except Exception:
        # Fallback de lectura nativa de word/document.xml
        with zipfile.ZipFile(docx_file) as z:
            xml_content = z.read("word/document.xml")

        root = ET.fromstring(xml_content)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = root.find("w:body", ns)
        if body is None:
            return

        def get_para_text(p_elem: ET.Element) -> str:
            t_nodes = p_elem.findall(".//w:t", ns)
            return "".join(n.text for n in t_nodes if n.text).strip()

        for elem in body:
            tag = elem.tag.split("}")[-1]
            if tag == "p":
                t = get_para_text(elem)
                if t:
                    yield t
            elif tag == "tbl":
                for row in elem.findall("w:tr", ns):
                    seen_cells = set()
                    for cell in row.findall("w:tc", ns):
                        if cell in seen_cells:
                            continue
                        seen_cells.add(cell)
                        for p in cell.findall("w:p", ns):
                            t = get_para_text(p)
                            if t:
                                yield t


def extract_docx_scenes(
    docx_path: str | Path,
    voice_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Agrupa por escena y diálogo las intervenciones de los personajes
    (DETECTIVE, AGENTE CERO, ANA) a lo largo del documento DOCX.
    """
    mapping = voice_mapping or VOICE_MAPPING_DEFAULT
    scenes: List[Dict[str, Any]] = []
    current_scene: Optional[Dict[str, Any]] = None
    scene_counter = 0
    scene_dialogues: List[Dict[str, str]] = []

    for text in iter_document_texts(docx_path):
        if not text:
            continue

        # Detectar el inicio de una de las 12 escenas principales
        if text.startswith("Escena ") and "." in text[:12]:
            if current_scene:
                scenes.append(current_scene)

            scene_counter += 1
            scene_dialogues = []

            # Asegúrate de que cada escena devuelva tanto el texto unificado como los diálogos multivoz:
            current_scene = {
                "id": f"escena_{scene_counter:02d}",
                "title": text,
                "narration": " ".join([d["text"] for d in scene_dialogues]), # Satisface al narrador base
                "dialogue": scene_dialogues                                  # Alimenta los modelos de Applio
            }
            continue

        # Detectar quién habla
        for prefix, info in mapping.items():
            if text.startswith(prefix + ":") or text.startswith(prefix + " :"):
                dialogue_text = text.split(":", 1)[1].strip()
                if current_scene is not None:
                    scene_dialogues.append(
                        {
                            "character": info["character"],
                            "voice_model": info["voice_model"],
                            "text": dialogue_text,
                        }
                    )
                    current_scene["narration"] = " ".join([d["text"] for d in scene_dialogues])
                break

    if current_scene:
        scenes.append(current_scene)

    return scenes


parse_docx_dialogues = extract_docx_scenes


def docx_to_yaml_data(
    docx_path: str | Path,
    voice_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Retorna los datos del guion DOCX en formato diccionario."""
    return {"scenes": extract_docx_scenes(docx_path, voice_mapping=voice_mapping)}


def docx_to_yaml(
    docx_path: str | Path,
    output_path: str | Path,
    voice_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> Path:
    """
    Convierte un guion DOCX en un YAML limpio agrupado por escena y diálogos de personajes.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    scenes = extract_docx_scenes(docx_path, voice_mapping=voice_mapping)

    yaml_data = {"scenes": scenes}

    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump(
            yaml_data,
            f,
            Dumper=IndentedDumper,
            allow_unicode=True,
            sort_keys=False,
        )

    return out_file


def parse_script(file_path: str) -> ScriptDefinition:
    """
    Parsea un archivo de guión (YAML o DOCX) y devuelve un objeto ScriptDefinition validado.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Error: El archivo {file_path} no existe.")

    if path.suffix.lower() == ".docx":
        scenes = extract_docx_scenes(path)
        data = {"scenes": scenes}
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

    return ScriptDefinition(**data)
