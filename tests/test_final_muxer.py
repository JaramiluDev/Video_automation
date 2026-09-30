import subprocess
from pathlib import Path
import pytest

from scripts.final_muxer import (
    FFmpegExecutionError,
    FFmpegNotFoundError,
    InvalidMediaError,
    MediaNotFoundError,
    build_ffmpeg_command,
    format_file_size,
    mux_video_audio,
    parse_args,
    validate_inputs,
)


def test_format_file_size():
    assert format_file_size(500) == "500.00 B"
    assert format_file_size(1024) == "1.00 KB"
    assert format_file_size(1024 * 1024) == "1.00 MB"


def test_build_ffmpeg_command():
    video = Path("/tmp/video.mp4")
    audio = Path("/tmp/audio.mp3")
    output = Path("/tmp/final.mp4")

    cmd = build_ffmpeg_command(video, audio, output, overwrite=True)

    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-i" in cmd
    assert str(video) in cmd
    assert str(audio) in cmd
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-b:a" in cmd and cmd[cmd.index("-b:a") + 1] == "192k"
    assert "-shortest" in cmd
    assert "-map" in cmd
    assert "0:v:0" in cmd
    assert "1:a:0" in cmd
    assert cmd[-1] == str(output)


def test_build_ffmpeg_command_no_overwrite():
    video = Path("/tmp/video.mp4")
    audio = Path("/tmp/audio.mp3")
    output = Path("/tmp/final.mp4")

    cmd = build_ffmpeg_command(video, audio, output, overwrite=False)
    assert "-n" in cmd
    assert "-y" not in cmd


def test_validate_inputs_missing_video(tmp_path):
    video = tmp_path / "non_existent_video.mp4"
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"dummy audio content")
    output = tmp_path / "output.mp4"

    with pytest.raises(MediaNotFoundError, match="El video base especificado no existe"):
        validate_inputs(video, audio, output)


def test_validate_inputs_missing_audio(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy video content")
    audio = tmp_path / "non_existent_audio.mp3"
    output = tmp_path / "output.mp4"

    with pytest.raises(MediaNotFoundError, match="El archivo de audio especificado no existe"):
        validate_inputs(video, audio, output)


def test_validate_inputs_empty_files(tmp_path):
    video = tmp_path / "empty_video.mp4"
    video.touch()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"dummy")
    output = tmp_path / "output.mp4"

    with pytest.raises(InvalidMediaError, match="El video base está vacío"):
        validate_inputs(video, audio, output)


def test_validate_inputs_output_same_as_input(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video data")
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio data")

    with pytest.raises(InvalidMediaError, match="La ruta de salida no puede ser idéntica al video de entrada"):
        validate_inputs(video, audio, video)

    with pytest.raises(InvalidMediaError, match="La ruta de salida no puede ser idéntica al archivo de audio"):
        validate_inputs(video, audio, audio)


def test_parse_args_positional():
    args = parse_args(["base.mp4", "voice.mp3", "result.mp4"])
    assert args.video == Path("base.mp4")
    assert args.audio == Path("voice.mp3")
    assert args.output == Path("result.mp4")
    assert args.overwrite is True


def test_parse_args_flags():
    args = parse_args(["-v", "input.mp4", "-a", "track.wav", "-o", "muxed.mp4", "-n", "--timeout", "60.0"])
    assert args.video_flag == Path("input.mp4")
    assert args.audio_flag == Path("track.wav")
    assert args.output_flag == Path("muxed.mp4")
    assert args.overwrite is False
    assert args.timeout == 60.0


def test_mux_video_audio_integration(tmp_path):
    """
    Test de integración con FFmpeg real:
    Crea 2s de video y 4s de audio sintéticos y verifica que el archivo muxed
    se recorte a 2s exactos gracias a -shortest.
    """
    video_path = tmp_path / "synth_video.mp4"
    audio_path = tmp_path / "synth_audio.mp3"
    output_path = tmp_path / "final_result.mp4"

    # 1. Generar video sintético de 2 segundos (320x240, 25fps)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2:r=25",
            "-c:v", "libx264", str(video_path),
        ],
        check=True,
        capture_output=True,
    )

    # 2. Generar audio sintético de 4 segundos (tono seno de 440Hz)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:a", "libmp3lame", str(audio_path),
        ],
        check=True,
        capture_output=True,
    )

    # 3. Ejecutar mux_video_audio
    result_path = mux_video_audio(video_path, audio_path, output_path)

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    # 4. Verificar duración resultante con ffprobe
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(result_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    # El video duraba 2 segundos y el audio 4 segundos; -shortest debe recortar a ~2.0 segundos
    assert 1.9 <= duration <= 2.1
