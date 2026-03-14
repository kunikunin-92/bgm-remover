from __future__ import annotations

import io
import os
import queue
import shutil
import threading
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import customtkinter as ctk  # type: ignore[import-not-found]

from gui import run_app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
BIN_DIR = _SCRIPT_DIR / "bin"

FFMPEG_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

APP_BG = "#0b1220"
HEADER_BG = "#111a2e"
PANEL_BG = "#121b2f"
SURFACE_BG = "#0c1424"
TEXT_PRIMARY = "#f4f7fb"
TEXT_SECONDARY = "#90a0b7"
ACCENT = "#4da3ff"
ACCENT_HOVER = "#2f89e6"
LINE = "#22304a"


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _prepend_bin_to_path() -> None:
    """Add the app-local bin/ directory to PATH so subprocesses find ffmpeg."""
    if BIN_DIR.is_dir():
        current = os.environ.get("PATH", "")
        bin_str = str(BIN_DIR)
        if bin_str not in current.split(os.pathsep):
            os.environ["PATH"] = bin_str + os.pathsep + current


def _ffmpeg_available() -> bool:
    _prepend_bin_to_path()
    return shutil.which("ffmpeg") is not None


def _download_with_progress(url: str, progress_cb=None) -> bytes:
    req = Request(url, headers={"User-Agent": "bgm-remover/1.0"})
    with urlopen(req, timeout=180) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        chunk = 65536
        downloaded = 0
        while True:
            data = resp.read(chunk)
            if not data:
                break
            buf.write(data)
            downloaded += len(data)
            if progress_cb and total:
                progress_cb(min(99, int(downloaded * 100 / total)))
    if progress_cb:
        progress_cb(100)
    return buf.getvalue()


def install_ffmpeg(log_cb=None, progress_cb=None) -> bool:
    """Download ffmpeg ZIP and extract ffmpeg.exe + ffprobe.exe to BIN_DIR."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb("Downloading ffmpeg (this may take a moment — ~220 MB)...\n")
    try:
        data = _download_with_progress(FFMPEG_ZIP_URL, progress_cb)
    except Exception as exc:
        if log_cb:
            log_cb(f"Failed to download ffmpeg: {exc}\n")
        return False

    if log_cb:
        log_cb("Extracting ffmpeg.exe and ffprobe.exe...\n")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            extracted = 0
            for member in zf.namelist():
                basename = os.path.basename(member)
                if basename in ("ffmpeg.exe", "ffprobe.exe"):
                    dest = BIN_DIR / basename
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    if log_cb:
                        log_cb(f"  Extracted {basename}\n")
                    extracted += 1
            if extracted == 0:
                if log_cb:
                    log_cb("ffmpeg.exe not found inside the ZIP archive.\n")
                return False
        return True
    except Exception as exc:
        if log_cb:
            log_cb(f"Failed to extract ffmpeg: {exc}\n")
        return False


# ---------------------------------------------------------------------------
# Setup window
# ---------------------------------------------------------------------------

class SetupWindow(ctk.CTk):
    """Shown on first launch when ffmpeg is not found. Auto-installs it."""

    def __init__(self) -> None:
        super().__init__()
        self.title("BGM Remover — First Run Setup")
        self.geometry("780x500")
        self.resizable(False, False)
        self.configure(fg_color=APP_BG)

        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._launch_after_close = False

        self._build_ui()
        self.after(100, self._poll_queue)
        threading.Thread(target=self._run_install, daemon=True).start()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=18,
                              border_width=1, border_color=LINE)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="First Run Setup",
            font=ctk.CTkFont(family="Bahnschrift", size=26, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(16, 4))

        ctk.CTkLabel(
            header,
            text="ffmpeg was not found. Installing it now...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        self._progress_bar = ctk.CTkProgressBar(
            self,
            height=16,
            corner_radius=8,
            progress_color=ACCENT,
            fg_color="#1d2940",
        )
        self._progress_bar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        self._progress_bar.set(0)

        self._log_box = ctk.CTkTextbox(
            self,
            corner_radius=14,
            border_width=1,
            border_color=LINE,
            fg_color=SURFACE_BG,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled",
        )
        self._log_box.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        bottom.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            bottom,
            text="Installing...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        self._launch_btn = ctk.CTkButton(
            bottom,
            text="Launch BGM Remover",
            command=self._on_launch,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Bahnschrift", size=15, weight="bold"),
            state="disabled",
        )
        self._launch_btn.grid(row=1, column=0, sticky="ew", pady=(10, 0))

    def _append_log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _run_install(self) -> None:
        self._log_queue.put(("status", "Downloading ffmpeg..."))
        self._log_queue.put(("log", "--- Installing ffmpeg ---\n"))

        ok = install_ffmpeg(
            log_cb=lambda msg: self._log_queue.put(("log", msg)),
            progress_cb=lambda pct: self._log_queue.put(("progress", str(pct))),
        )
        _prepend_bin_to_path()

        if ok:
            self._log_queue.put(("log", "ffmpeg installed successfully.\n"))
            self._log_queue.put(("done", "ok"))
        else:
            self._log_queue.put(("log", "ERROR: Failed to install ffmpeg.\n"))
            self._log_queue.put(("done", "error"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    self._progress_bar.set(float(payload) / 100)
                elif kind == "status":
                    self._status_label.configure(text=payload)
                elif kind == "done":
                    if payload == "ok":
                        self._progress_bar.set(1.0)
                        self._status_label.configure(text="ffmpeg installed. Ready to launch.")
                        self._launch_btn.configure(state="normal")
                    else:
                        self._status_label.configure(
                            text="Installation failed. The app may not work without ffmpeg."
                        )
                        self._launch_btn.configure(
                            state="normal", text="Launch anyway"
                        )
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_queue)

    def _on_launch(self) -> None:
        self._launch_after_close = True
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    if not _ffmpeg_available():
        setup = SetupWindow()
        setup.mainloop()
        # Only proceed if the user clicked Launch
        if not setup._launch_after_close:
            raise SystemExit(0)

    run_app()
