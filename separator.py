from __future__ import annotations

import json
import importlib
import os
import subprocess
import sys
import tempfile
import traceback as traceback_module
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ffmpeg_utils import (
    ensure_unique_output_path,
    extract_audio_to_wav,
    is_supported_video_file,
    mux_audio_with_video,
    scan_video_files,
    subtract_bgm_from_audio,
)


DEFAULT_MODEL = "UVR-MDX-NET-Inst_HQ_3.onnx"
AVAILABLE_MODELS = [
    "UVR-MDX-NET-Inst_HQ_3.onnx",
    "UVR-MDX-NET-Inst_Main.onnx",
    "UVR_MDXNET_Main.onnx",
    "UVR_MDXNET_KARA_2.onnx",
    "Kim_Inst.onnx",
]

ProgressCallback = Callable[[Path, float, str], None]
LogCallback = Callable[[str], None]


@dataclass(slots=True)
class FileProcessResult:
    source_path: Path
    output_path: Path | None
    success: bool
    message: str


class AudioSeparatorRunner:
    def __init__(self, model_cache_dir: Path):
        self.model_cache_dir = model_cache_dir
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)

    def separate_instrumental(
        self,
        input_wav: Path,
        working_dir: Path,
        model_filename: str,
        device_mode: str,
        log_callback: LogCallback,
    ) -> Path:
        stem_name = f"{input_wav.stem}_instrumental"

        if device_mode.lower() == "gpu":
            gpu_ready, reason = self.check_gpu_readiness(model_filename)
            if not gpu_ready:
                raise RuntimeError(f"GPU mode selected but GPU runtime is unavailable: {reason}")

            self._run_cli(
                input_wav=input_wav,
                working_dir=working_dir,
                model_filename=model_filename,
                stem_name=stem_name,
                use_gpu=True,
                log_callback=log_callback,
            )
        else:
            self._run_cli(
                input_wav=input_wav,
                working_dir=working_dir,
                model_filename=model_filename,
                stem_name=stem_name,
                use_gpu=False,
                log_callback=log_callback,
            )

        instrumental_file = self._find_instrumental_output(
            working_dir=working_dir,
            input_wav=input_wav,
            preferred_stem_name=stem_name,
        )
        if instrumental_file is not None:
            return instrumental_file

        produced_files = sorted(str(path.name) for path in working_dir.iterdir())
        raise RuntimeError(
            "audio-separator finished without creating an instrumental file. "
            f"working_dir={working_dir} files={produced_files}"
        )

    def check_gpu_readiness(self, model_filename: str) -> tuple[bool, str]:
        model_suffix = Path(model_filename).suffix.lower()

        if model_suffix == ".onnx":
            try:
                ort = importlib.import_module("onnxruntime")
            except Exception as exc:
                return False, f"onnxruntime import failed: {exc}"

            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" not in providers:
                return False, f"CUDAExecutionProvider not available (providers={providers})"
            return True, "onnxruntime CUDA provider is available"

        try:
            torch = importlib.import_module("torch")
        except Exception as exc:
            return False, f"torch import failed: {exc}"

        if not torch.cuda.is_available():
            return False, "torch.cuda.is_available() is False"
        return True, "torch CUDA runtime is available"

    def _find_instrumental_output(self, working_dir: Path, input_wav: Path, preferred_stem_name: str) -> Path | None:
        candidates = [
            path
            for path in working_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".wav", ".flac", ".mp3", ".m4a"}
        ]

        if not candidates:
            return None

        source_name_lower = input_wav.name.lower()
        filtered = [path for path in candidates if path.name.lower() != source_name_lower]
        if not filtered:
            return None

        preferred_name_lower = f"{preferred_stem_name}.wav".lower()
        for path in filtered:
            if path.name.lower() == preferred_name_lower:
                return path

        for path in filtered:
            if "instrumental" in path.name.lower():
                return path

        filtered.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return filtered[0]

    def _run_cli(
        self,
        input_wav: Path,
        working_dir: Path,
        model_filename: str,
        stem_name: str,
        use_gpu: bool,
        log_callback: LogCallback,
    ) -> None:
        command = [
            sys.executable,
            "-c",
            "from audio_separator.utils.cli import main; main()",
            str(input_wav),
            "--model_filename",
            model_filename,
            "--model_file_dir",
            str(self.model_cache_dir),
            "--output_dir",
            str(working_dir),
            "--output_format",
            "WAV",
            "--single_stem",
            "Instrumental",
            "--custom_output_names",
            json.dumps({"Instrumental": stem_name}),
        ]
        if use_gpu:
            command.append("--use_autocast")

        env = os.environ.copy()
        if not use_gpu:
            env["CUDA_VISIBLE_DEVICES"] = "-1"

        mode_label = "GPU" if use_gpu else "CPU"
        log_callback(f"audio-separator start ({mode_label}): {input_wav.name}")
        log_callback(f"model={model_filename}")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        output_lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            message = line.strip()
            if message:
                output_lines.append(message)
                log_callback(message)

        return_code = process.wait()
        if return_code != 0:
            error_summary = " | ".join(output_lines[-6:]) if output_lines else "audio-separator command failed"
            raise RuntimeError(error_summary)

        if use_gpu:
            merged_log = "\n".join(output_lines).lower()
            if "running in cpu mode" in merged_log or "cpuexecutionprovider" in merged_log:
                raise RuntimeError("GPU mode selected, but audio-separator reported CPU execution")


class VideoBgmRemover:
    def __init__(self, model_cache_dir: Path):
        self.separator_runner = AudioSeparatorRunner(model_cache_dir)

    def validate_device_mode(self, model_filename: str, device_mode: str) -> tuple[bool, str]:
        if device_mode.lower() != "gpu":
            return True, "CPU mode selected"
        return self.separator_runner.check_gpu_readiness(model_filename)

    def process_batch(
        self,
        video_files: list[Path],
        output_dir: Path | None,
        model_filename: str,
        device_mode: str,
        progress_callback: ProgressCallback,
        log_callback: LogCallback,
    ) -> list[FileProcessResult]:
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
        results: list[FileProcessResult] = []

        for index, video_path in enumerate(video_files, start=1):
            progress_callback(video_path, 0.0, "Waiting")
            log_callback(f"[{index}/{len(video_files)}] Start: {video_path}")
            try:
                output_path = self.process_single_file(
                    video_path=video_path,
                    output_dir=output_dir,
                    model_filename=model_filename,
                    device_mode=device_mode,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                )
                results.append(
                    FileProcessResult(
                        source_path=video_path,
                        output_path=output_path,
                        success=True,
                        message=f"Done: {output_path.name}",
                    )
                )
                log_callback(f"Completed: {output_path}")
            except Exception as exc:
                progress_callback(video_path, 0.0, "Error")
                message = f"Skipped due to error: {exc}"
                results.append(
                    FileProcessResult(
                        source_path=video_path,
                        output_path=None,
                        success=False,
                        message=message,
                    )
                )
                log_callback(f"Error: {video_path.name} -> {exc}")
                log_callback(traceback_module.format_exc().strip())

        return results

    def process_single_file(
        self,
        video_path: Path,
        output_dir: Path | None,
        model_filename: str,
        device_mode: str,
        progress_callback: ProgressCallback,
        log_callback: LogCallback,
    ) -> Path:
        if not is_supported_video_file(video_path):
            raise ValueError("unsupported video format")

        target_output_dir = output_dir if output_dir is not None else video_path.parent
        target_output_dir.mkdir(parents=True, exist_ok=True)
        output_path = ensure_unique_output_path(target_output_dir, f"{video_path.stem}_nobgm")

        with tempfile.TemporaryDirectory(prefix="bgm_remover_", dir=str(target_output_dir)) as temp_dir:
            working_dir = Path(temp_dir)
            extracted_wav = working_dir / "source_audio.wav"
            nobgm_wav = working_dir / "nobgm_audio.wav"

            progress_callback(video_path, 0.05, "Extracting audio")
            extract_audio_to_wav(video_path, extracted_wav)

            progress_callback(video_path, 0.25, "Separating BGM")
            instrumental_wav = self.separator_runner.separate_instrumental(
                input_wav=extracted_wav,
                working_dir=working_dir,
                model_filename=model_filename,
                device_mode=device_mode,
                log_callback=log_callback,
            )

            progress_callback(video_path, 0.75, "Building clean audio")
            subtract_bgm_from_audio(extracted_wav, instrumental_wav, nobgm_wav)

            progress_callback(video_path, 0.9, "Muxing video")
            mux_audio_with_video(video_path, nobgm_wav, output_path)

            progress_callback(video_path, 1.0, "Completed")
            return output_path


def normalize_video_selection(paths: list[Path]) -> list[Path]:
    unique_paths: dict[str, Path] = {}
    for path in paths:
        resolved = path.resolve()
        if is_supported_video_file(resolved):
            unique_paths[str(resolved).lower()] = resolved
    return sorted(unique_paths.values(), key=lambda item: str(item).lower())


def collect_videos_from_folder(folder_path: Path) -> list[Path]:
    return scan_video_files(folder_path.resolve())
