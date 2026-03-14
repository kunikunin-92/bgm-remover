from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import cast

import customtkinter as ctk  # type: ignore[import-not-found]

from separator import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    FileProcessResult,
    VideoBgmRemover,
    collect_videos_from_folder,
    normalize_video_selection,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_BG = "#0b1220"
HEADER_BG = "#111a2e"
PANEL_BG = "#121b2f"
PANEL_ALT_BG = "#0f1728"
SURFACE_BG = "#0c1424"
TEXT_PRIMARY = "#f4f7fb"
TEXT_SECONDARY = "#90a0b7"
TEXT_MUTED = "#6f8098"
ACCENT = "#4da3ff"
ACCENT_HOVER = "#2f89e6"
SUCCESS = "#21c77a"
WARNING = "#f2b84b"
ERROR = "#ff6b6b"
LINE = "#22304a"


@dataclass(slots=True)
class ProgressRow:
    frame: ctk.CTkFrame
    name_label: ctk.CTkLabel
    status_label: ctk.CTkLabel
    progress_bar: ctk.CTkProgressBar


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw_part in version.replace("-", ".").split("."):
        digits = "".join(character for character in raw_part if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


class BgmRemoverApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BGM Remover")
        self.geometry("1360x880")
        self.minsize(1120, 760)
        self.configure(fg_color=APP_BG)

        self.workspace = Path(__file__).resolve().parent
        self.processor = VideoBgmRemover(self.workspace / "models")

        self.selected_files: list[Path] = []
        self.progress_rows: dict[Path, ProgressRow] = {}
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.update_thread: threading.Thread | None = None

        self.output_dir_var = ctk.StringVar(value="")
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.device_var = ctk.StringVar(value="GPU")
        self.selection_summary_var = ctk.StringVar(value="No videos selected")
        self.version_var = ctk.StringVar(value=self._get_installed_audio_separator_version())
        self.update_status_var = ctk.StringVar(value="audio-separator: checking for updates...")

        self._build_layout()
        self.after(100, self._poll_events)
        self._start_update_check()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=22, border_width=1, border_color=LINE)
        header.grid(row=0, column=0, sticky="nsew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="BGM Remover",
            font=ctk.CTkFont(family="Bahnschrift", size=30, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))

        version_label = ctk.CTkLabel(
            header,
            textvariable=self.version_var,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=TEXT_SECONDARY,
        )
        version_label.grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

        self.update_status_label = ctk.CTkLabel(
            header,
            textvariable=self.update_status_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        )
        self.update_status_label.grid(row=0, column=1, sticky="e", padx=(0, 14), pady=(18, 4))

        self.update_button = ctk.CTkButton(
            header,
            text="Update audio-separator",
            width=190,
            height=34,
            command=self._start_audio_separator_update,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            state="disabled",
        )
        self.update_button.grid(row=1, column=1, sticky="e", padx=(0, 22), pady=(0, 18))

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=1, column=0, sticky="nsew", padx=18, pady=10)
        top.grid_columnconfigure(0, weight=3)
        top.grid_columnconfigure(1, weight=2)
        top.grid_rowconfigure(0, weight=1)

        self._build_input_panel(top)
        self._build_control_panel(top)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        bottom.grid_columnconfigure(0, weight=2)
        bottom.grid_columnconfigure(1, weight=3)
        bottom.grid_rowconfigure(0, weight=1)

        self._build_progress_panel(bottom)
        self._build_log_panel(bottom)

    def _build_input_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=18, fg_color=PANEL_BG, border_width=1, border_color=LINE)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)

        title = ctk.CTkLabel(
            panel,
            text="Inputs",
            font=ctk.CTkFont(family="Bahnschrift", size=21, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))

        button_row = ctk.CTkFrame(panel, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        button_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.add_files_button = ctk.CTkButton(
            button_row,
            text="Add Files",
            command=self._add_files,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
        )
        self.add_files_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.add_folder_button = ctk.CTkButton(
            button_row,
            text="Add Folder",
            command=self._add_folder,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
        )
        self.add_folder_button.grid(row=0, column=1, sticky="ew", padx=4)

        self.clear_button = ctk.CTkButton(
            button_row,
            text="Clear",
            command=self._clear_selection,
            fg_color="#21314a",
            hover_color="#2a3b57",
            text_color=TEXT_PRIMARY,
        )
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.selection_summary_label = ctk.CTkLabel(
            panel,
            textvariable=self.selection_summary_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
        )
        self.selection_summary_label.grid(row=2, column=0, sticky="nw", padx=18, pady=(0, 8))

        self.selection_text = ctk.CTkTextbox(
            panel,
            corner_radius=14,
            border_width=1,
            border_color=LINE,
            fg_color=SURFACE_BG,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.selection_text.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.selection_text.configure(state="disabled")

    def _build_control_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=18, fg_color=PANEL_ALT_BG, border_width=1, border_color=LINE)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        panel.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            panel,
            text="Settings",
            font=ctk.CTkFont(family="Bahnschrift", size=21, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 14))

        output_label = ctk.CTkLabel(panel, text="Output Folder", anchor="w", text_color=TEXT_SECONDARY)
        output_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 6))

        output_row = ctk.CTkFrame(panel, fg_color="transparent")
        output_row.grid(row=2, column=0, sticky="ew", padx=18)
        output_row.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(
            output_row,
            textvariable=self.output_dir_var,
            fg_color=SURFACE_BG,
            border_color=LINE,
            text_color=TEXT_PRIMARY,
            placeholder_text="Leave empty to save beside each input file",
        )
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.output_browse_button = ctk.CTkButton(
            output_row,
            text="Browse",
            width=92,
            command=self._choose_output_dir,
            fg_color="#21314a",
            hover_color="#2a3b57",
            text_color=TEXT_PRIMARY,
        )
        self.output_browse_button.grid(row=0, column=1, sticky="e")

        model_label = ctk.CTkLabel(panel, text="Model", anchor="w", text_color=TEXT_SECONDARY)
        model_label.grid(row=3, column=0, sticky="ew", padx=18, pady=(16, 6))

        self.model_menu = ctk.CTkOptionMenu(
            panel,
            values=AVAILABLE_MODELS,
            variable=self.model_var,
            fg_color="#20314e",
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=PANEL_BG,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color="#1b2941",
        )
        self.model_menu.grid(row=4, column=0, sticky="ew", padx=18)

        device_label = ctk.CTkLabel(panel, text="Device", anchor="w", text_color=TEXT_SECONDARY)
        device_label.grid(row=5, column=0, sticky="ew", padx=18, pady=(16, 6))

        self.device_selector = ctk.CTkSegmentedButton(
            panel,
            values=["GPU", "CPU"],
            variable=self.device_var,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color="#21314a",
            unselected_hover_color="#2a3b57",
            text_color=TEXT_PRIMARY,
        )
        self.device_selector.grid(row=6, column=0, sticky="ew", padx=18)

        self.start_button = ctk.CTkButton(
            panel,
            text="Start Processing",
            height=46,
            command=self._start_processing,
            fg_color=SUCCESS,
            hover_color="#16a965",
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Bahnschrift", size=16, weight="bold"),
        )
        self.start_button.grid(row=7, column=0, sticky="ew", padx=18, pady=(20, 18))

    def _build_progress_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=18, fg_color=PANEL_BG, border_width=1, border_color=LINE)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            panel,
            text="File Progress",
            font=ctk.CTkFont(family="Bahnschrift", size=21, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.progress_frame = ctk.CTkScrollableFrame(
            panel,
            corner_radius=14,
            fg_color=SURFACE_BG,
            border_width=1,
            border_color=LINE,
        )
        self.progress_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.progress_frame.grid_columnconfigure(0, weight=1)

    def _build_log_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=18, fg_color=PANEL_ALT_BG, border_width=1, border_color=LINE)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            panel,
            text="Logs",
            font=ctk.CTkFont(family="Bahnschrift", size=21, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.log_text = ctk.CTkTextbox(
            panel,
            corner_radius=14,
            border_width=1,
            border_color=LINE,
            fg_color=SURFACE_BG,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.log_text.configure(state="disabled")

    def _add_files(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov")],
        )
        if not file_paths:
            return
        self.selected_files = normalize_video_selection(self.selected_files + [Path(path) for path in file_paths])
        self._refresh_selection_view()

    def _add_folder(self) -> None:
        folder_path = filedialog.askdirectory(title="Select folder")
        if not folder_path:
            return

        discovered_files = collect_videos_from_folder(Path(folder_path))
        if not discovered_files:
            messagebox.showinfo("No videos found", "No supported video files were found in the selected folder.")
            return

        self.selected_files = normalize_video_selection(self.selected_files + discovered_files)
        self._refresh_selection_view()

    def _clear_selection(self) -> None:
        self.selected_files = []
        self._refresh_selection_view()
        self._reset_progress_rows()

    def _choose_output_dir(self) -> None:
        folder_path = filedialog.askdirectory(title="Select output folder")
        if folder_path:
            self.output_dir_var.set(folder_path)

    def _refresh_selection_view(self) -> None:
        self.selection_text.configure(state="normal")
        self.selection_text.delete("1.0", "end")

        if not self.selected_files:
            self.selection_summary_var.set("No videos selected")
            self.selection_text.insert("end", "Add files or a folder.\n")
        else:
            self.selection_summary_var.set(f"{len(self.selected_files)} file(s) queued")
            for file_path in self.selected_files:
                self.selection_text.insert("end", f"{file_path}\n")

        self.selection_text.configure(state="disabled")

    def _start_processing(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return

        if not self.selected_files:
            messagebox.showwarning("No input", "Select at least one video file or folder.")
            return

        output_text = self.output_dir_var.get().strip()
        output_dir: Path | None
        if not output_text:
            output_dir = None
        else:
            output_dir = Path(output_text)
            output_dir.mkdir(parents=True, exist_ok=True)

        selected_model = self.model_var.get()
        selected_device = self.device_var.get()
        device_ready, device_reason = self.processor.validate_device_mode(selected_model, selected_device)
        if not device_ready:
            messagebox.showerror("GPU unavailable", f"{device_reason}\n\nSwitch to CPU mode or install GPU runtime.")
            self._append_log(f"Device validation failed: {device_reason}")
            return

        self._reset_progress_rows()
        for file_path in self.selected_files:
            self._create_progress_row(file_path)

        self._append_log("=== Processing started ===")
        self._set_controls_enabled(False)

        self.worker_thread = threading.Thread(
            target=self._run_processing_thread,
            args=(self.selected_files.copy(), output_dir, selected_model, selected_device),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_processing_thread(
        self,
        video_files: list[Path],
        output_dir: Path | None,
        model_filename: str,
        device_mode: str,
    ) -> None:
        results = self.processor.process_batch(
            video_files=video_files,
            output_dir=output_dir,
            model_filename=model_filename,
            device_mode=device_mode,
            progress_callback=lambda path, value, status: self.event_queue.put(("progress", (path, value, status))),
            log_callback=lambda message: self.event_queue.put(("log", message)),
        )
        self.event_queue.put(("done", results))

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.add_files_button.configure(state=state)
        self.add_folder_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.output_entry.configure(state=state)
        self.output_browse_button.configure(state=state)
        self.model_menu.configure(state=state)
        self.device_selector.configure(state=state)
        self.start_button.configure(state=state)

    def _create_progress_row(self, file_path: Path) -> None:
        row_frame = ctk.CTkFrame(self.progress_frame, fg_color=PANEL_BG, corner_radius=12, border_width=1, border_color=LINE)
        row_frame.grid(sticky="ew", padx=8, pady=6)
        row_frame.grid_columnconfigure(0, weight=1)

        name_label = ctk.CTkLabel(
            row_frame,
            text=file_path.name,
            anchor="w",
            font=ctk.CTkFont(family="Bahnschrift", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        name_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))

        status_label = ctk.CTkLabel(
            row_frame,
            text="Waiting",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        )
        status_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        progress_bar = ctk.CTkProgressBar(
            row_frame,
            height=14,
            corner_radius=8,
            progress_color=ACCENT,
            fg_color="#1d2940",
        )
        progress_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        progress_bar.set(0)

        self.progress_rows[file_path] = ProgressRow(
            frame=row_frame,
            name_label=name_label,
            status_label=status_label,
            progress_bar=progress_bar,
        )

    def _reset_progress_rows(self) -> None:
        for row in self.progress_rows.values():
            row.frame.destroy()
        self.progress_rows.clear()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _get_installed_audio_separator_version(self) -> str:
        try:
            current_version = metadata.version("audio-separator")
        except metadata.PackageNotFoundError:
            current_version = "not installed"
        return f"audio-separator {current_version}"

    def _start_update_check(self) -> None:
        if self.update_thread and self.update_thread.is_alive():
            return
        self.update_thread = threading.Thread(target=self._check_audio_separator_update, daemon=True)
        self.update_thread.start()

    def _check_audio_separator_update(self) -> None:
        try:
            current_version = metadata.version("audio-separator")
            with urllib.request.urlopen("https://pypi.org/pypi/audio-separator/json", timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            latest_version = str(payload["info"]["version"])

            update_available = _version_key(latest_version) > _version_key(current_version)
            self.event_queue.put(
                (
                    "update_status",
                    {
                        "current": current_version,
                        "latest": latest_version,
                        "available": update_available,
                    },
                )
            )
        except metadata.PackageNotFoundError:
            self.event_queue.put(("update_error", "audio-separator is not installed."))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            self.event_queue.put(("update_error", f"Update check failed: {exc}"))

    def _start_audio_separator_update(self) -> None:
        if self.update_thread and self.update_thread.is_alive():
            return

        self.update_button.configure(state="disabled", text="Updating...")
        self.update_status_var.set("audio-separator: updating...")
        self._append_log("=== Updating audio-separator ===")

        self.update_thread = threading.Thread(target=self._run_audio_separator_update, daemon=True)
        self.update_thread.start()

    def _run_audio_separator_update(self) -> None:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "audio-separator"]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert process.stdout is not None
        output_lines: list[str] = []
        for line in process.stdout:
            message = line.strip()
            if message:
                output_lines.append(message)
                self.event_queue.put(("log", message))

        return_code = process.wait()
        if return_code == 0:
            try:
                new_version = metadata.version("audio-separator")
            except metadata.PackageNotFoundError:
                new_version = "unknown"
            self.event_queue.put(("update_complete", new_version))
        else:
            error_message = output_lines[-1] if output_lines else "audio-separator update failed"
            self.event_queue.put(("update_failed", error_message))

    def _poll_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self._append_log(str(payload))
            elif event_type == "progress":
                path, value, status = cast(tuple[Path, float, str], payload)
                row = self.progress_rows.get(path)
                if row:
                    row.progress_bar.set(float(value))
                    row.status_label.configure(text=str(status))
            elif event_type == "done":
                results = cast(list[FileProcessResult], payload)
                success_count = sum(1 for item in results if item.success)
                error_count = len(results) - success_count
                self._append_log(f"=== Finished: success={success_count}, error={error_count} ===")
                for result in results:
                    if not result.success:
                        self._append_log(f"FAILED {result.source_path.name}: {result.message}")
                self._set_controls_enabled(True)
            elif event_type == "update_status":
                update_info = cast(dict[str, object], payload)
                current_version = str(update_info["current"])
                latest_version = str(update_info["latest"])
                update_available = bool(update_info["available"])

                self.version_var.set(f"audio-separator {current_version}")
                if update_available:
                    self.update_status_var.set(f"Update available: {current_version} -> {latest_version}")
                    self.update_status_label.configure(text_color=WARNING)
                    self.update_button.configure(state="normal", text="Update audio-separator")
                else:
                    self.update_status_var.set(f"audio-separator is up to date ({current_version})")
                    self.update_status_label.configure(text_color=SUCCESS)
                    self.update_button.configure(state="disabled", text="Up to date")
            elif event_type == "update_error":
                self.update_status_var.set(str(payload))
                self.update_status_label.configure(text_color=TEXT_MUTED)
                self.update_button.configure(state="disabled", text="Update unavailable")
            elif event_type == "update_complete":
                new_version = str(payload)
                self.version_var.set(f"audio-separator {new_version}")
                self.update_status_var.set(f"Updated to {new_version}. Restart the app to use the new version.")
                self.update_status_label.configure(text_color=SUCCESS)
                self.update_button.configure(state="disabled", text="Updated")
                self._append_log(f"=== audio-separator updated to {new_version} ===")
            elif event_type == "update_failed":
                self.update_status_var.set(f"Update failed: {payload}")
                self.update_status_label.configure(text_color=ERROR)
                self.update_button.configure(state="normal", text="Retry Update")
                self._append_log(f"=== audio-separator update failed: {payload} ===")

        self.after(100, self._poll_events)


def run_app() -> None:
    app = BgmRemoverApp()
    app.mainloop()
