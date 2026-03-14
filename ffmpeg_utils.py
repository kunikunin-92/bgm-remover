from __future__ import annotations

from pathlib import Path

import ffmpeg  # type: ignore[import-not-found]


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}


def is_supported_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def scan_video_files(folder_path: Path) -> list[Path]:
    return sorted(
        [path for path in folder_path.rglob("*") if is_supported_video_file(path)],
        key=lambda path: str(path).lower(),
    )


def ensure_unique_output_path(output_dir: Path, base_name: str, suffix: str = ".mp4") -> Path:
    candidate = output_dir / f"{base_name}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name}_{counter}{suffix}"
        counter += 1
    return candidate


def _run_stream(stream: ffmpeg.nodes.OutputStream) -> None:
    try:
        stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as exc:
        details = exc.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(details or "ffmpeg command failed") from exc


def extract_audio_to_wav(video_path: Path, wav_path: Path) -> None:
    stream = ffmpeg.output(
        ffmpeg.input(str(video_path)).audio,
        str(wav_path),
        acodec="pcm_s16le",
        ac=2,
        ar=44100,
    )
    _run_stream(stream)


def subtract_bgm_from_audio(source_wav: Path, bgm_wav: Path, output_wav: Path) -> None:
    source_stream = ffmpeg.input(str(source_wav)).audio
    bgm_stream = ffmpeg.input(str(bgm_wav)).audio.filter("volume", -1)
    mixed_stream = ffmpeg.filter(
        [source_stream, bgm_stream],
        "amix",
        inputs=2,
        duration="first",
        normalize=0,
        dropout_transition=0,
    )
    stream = ffmpeg.output(
        mixed_stream,
        str(output_wav),
        acodec="pcm_s16le",
        ac=2,
        ar=44100,
    )
    _run_stream(stream)


def mux_audio_with_video(video_path: Path, audio_path: Path, output_path: Path) -> None:
    video_input = ffmpeg.input(str(video_path))
    audio_input = ffmpeg.input(str(audio_path))

    copy_stream = ffmpeg.output(
        video_input.video,
        audio_input.audio,
        str(output_path),
        vcodec="copy",
        acodec="aac",
        audio_bitrate="192k",
        movflags="+faststart",
        shortest=None,
    )

    try:
        _run_stream(copy_stream)
        return
    except RuntimeError:
        transcode_stream = ffmpeg.output(
            video_input.video,
            audio_input.audio,
            str(output_path),
            vcodec="libx264",
            preset="medium",
            crf=18,
            pix_fmt="yuv420p",
            acodec="aac",
            audio_bitrate="192k",
            movflags="+faststart",
            shortest=None,
        )
        _run_stream(transcode_stream)
