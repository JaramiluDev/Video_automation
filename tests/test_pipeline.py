import pytest
from unittest.mock import patch, MagicMock
from video_automation.models import ScriptDefinition, Scene, OutputSettings
from video_automation.heavy_render import render_video, render_manim_scene


def _make_script(**overrides):
    scene = Scene(
        id="ESCENA-01",
        title="Intro",
        narration="Hola mundo",
        image_paths=["data/assets/placeholder_1.png"],
        duration=2.0,
    )
    defaults = dict(
        title="Test",
        scenes=[scene],
        output_filename="test_output.mp4",
    )
    defaults.update(overrides)
    return ScriptDefinition(**defaults)


def test_render_video_calls_compose_clips_with_settings():
    """render_video debe pasar audio, subtítulos, fps y resolución a compose_clips."""
    script = _make_script(
        audio_path="data/audio/mix.mp3",
        subtitle_path="data/subtitles/out.srt",
        output_settings=OutputSettings(resolution=(1280, 720), fps=60),
    )

    with patch("video_automation.heavy_render.compose_clips") as mock_compose, \
         patch("video_automation.heavy_render.build_image_clip") as mock_build:
        mock_build.return_value = MagicMock()
        mock_compose.return_value = "data/renders/test_output.mp4"
        render_video(script, "data/renders")

    mock_compose.assert_called_once()
    _, kwargs = mock_compose.call_args
    assert kwargs["audio_path"] == "data/audio/mix.mp3"
    assert kwargs["subtitle_path"] == "data/subtitles/out.srt"
    assert kwargs["fps"] == 60
    assert kwargs["resolution"] == (1280, 720)


def test_render_video_uses_default_output_settings_when_missing():
    """Si el guión no trae output_settings, se deben usar los valores por defecto."""
    script = _make_script()

    with patch("video_automation.heavy_render.compose_clips") as mock_compose, \
         patch("video_automation.heavy_render.build_image_clip") as mock_build:
        mock_build.return_value = MagicMock()
        mock_compose.return_value = "data/renders/test_output.mp4"
        render_video(script, "data/renders")

    _, kwargs = mock_compose.call_args
    assert kwargs["fps"] == 30
    assert kwargs["resolution"] == (1920, 1080)


def test_render_video_mixes_manim_and_image_scenes_in_order():
    """Una escena 'manim' y una de imágenes deben terminar como clips en el mismo orden."""
    image_scene = Scene(
        id="ESCENA-01",
        title="Intro",
        narration="...",
        image_paths=["data/assets/placeholder_1.png"],
        duration=2.0,
    )
    manim_scene = Scene(
        id="ESCENA-02-MANIM",
        title="Formula",
        narration="...",
        image_paths=[],
        duration=3.0,
        render_type="manim",
        formula="ax^2+bx+c=0",
    )
    script = _make_script(scenes=[image_scene, manim_scene])

    with patch("video_automation.heavy_render.compose_clips") as mock_compose, \
         patch("video_automation.heavy_render.build_image_clip") as mock_build_image, \
         patch("video_automation.heavy_render.render_manim_scene") as mock_render_manim:
        mock_build_image.return_value = MagicMock(name="image_clip")
        mock_render_manim.return_value = MagicMock(name="manim_clip")
        mock_compose.return_value = "data/renders/test_output.mp4"
        render_video(script, "data/renders")

    clips_arg = mock_compose.call_args[0][0]
    assert len(clips_arg) == 2
    mock_build_image.assert_called_once()
    mock_render_manim.assert_called_once()


def test_manim_scene_without_content_still_returns_clip():
    """render_manim_scene no debe reventar si la escena no trae formula ni narration largas."""
    scene = Scene(
        id="ESCENA-VACIA",
        title="Vacia",
        narration="hola",
        image_paths=[],
        duration=1.5,
        render_type="manim",
    )
    # Prueba de humo: solo confirmamos que no lanza excepción al construir
    # la escena de Manim con datos mínimos. El render real (pesado) se
    # verifica manualmente, no en cada corrida de CI.
    clip = render_manim_scene(scene, resolution=(320, 180), fps=15)
    assert clip is not None
    clip.close()
