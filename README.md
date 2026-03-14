# BGM Remover

A GUI tool that automatically removes background music from video files, leaving only vocals and sound effects.

## Features

- Remove BGM from video files using AI-based audio separation
- GPU / CPU toggle for faster processing when an NVIDIA GPU is available
- Batch processing — add individual files or entire folders (subfolders are scanned recursively)
- Five AI separation models to choose from
- Checks for `audio-separator` updates on launch and lets you update in-app
- **Auto-installs ffmpeg on first launch** if it is not found on your system

## Supported formats

`.mp4` / `.mkv` / `.avi` / `.mov`

## Available models

| Model | Notes |
|---|---|
| `UVR-MDX-NET-Inst_HQ_3.onnx` | Default — high quality |
| `UVR-MDX-NET-Inst_Main.onnx` | |
| `UVR_MDXNET_Main.onnx` | |
| `UVR_MDXNET_KARA_2.onnx` | Optimised for karaoke tracks |
| `Kim_Inst.onnx` | |

## Processing pipeline

1. Extract audio from video (WAV)
2. Separate BGM from audio using the selected AI model (audio-separator)
3. Subtract BGM via ffmpeg `amix` filter
4. Mux the cleaned audio back into the video (AAC 192 kbps)
5. Output filename: `{original_name}_nobgm.mp4`

## Getting started

Double-click `run_bgm_remover.bat` to launch.

On the first run it will automatically:

- Create a Python virtual environment (`venv`)
- Install all required libraries
- Detect your NVIDIA GPU and install the CUDA runtime if available
- Download and install ffmpeg if it is not already on your system

```
run_bgm_remover.bat
```

## Requirements

- Python 3.10 or later
- NVIDIA GPU (optional — CPU mode is also supported)

> **Note:** ffmpeg is installed automatically on first launch. You do not need to install it manually.

## File structure

```
BGM_Remover/
├── main.py               # Entry point — dependency check & setup window
├── gui.py                # Main GUI (customtkinter)
├── separator.py          # BGM separation logic
├── ffmpeg_utils.py       # ffmpeg utility functions
├── requirements.txt      # Python dependencies
└── run_bgm_remover.bat   # Fully automated launcher
```

## Dependencies

- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) — modern GUI framework
- [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) — Python bindings for ffmpeg
- [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) — AI-based audio source separation

## Manual installation

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

To use GPU (CUDA), also run:

```bash
pip install audio-separator[gpu]
```
