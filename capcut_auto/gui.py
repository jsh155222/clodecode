"""데스크톱 GUI: 무음/버벅임 자동 컷 + 자막 생성 CapCut 드래프트 파이프라인.

파이썬 표준 라이브러리(Tkinter)만으로 동작하므로 GUI 자체를 위한 별도
설치가 필요 없다 (ffmpeg / faster-whisper / pycapcut은 여전히 필요).

실행:
    python -m capcut_auto.gui
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .draft_builder import default_capcut_drafts_dir
from .pipeline import PipelineError, PipelineOptions, PipelineResult, run_pipeline

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]


class CapCutAutoApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CapCut 자동 컷/자막 편집기")
        self.root.geometry("720x640")
        self.root.minsize(640, 560)

        self._msg_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_vars()
        self._build_widgets()
        self.root.after(100, self._poll_queue)

    # ---------------------------------------------------------------- vars
    def _build_vars(self) -> None:
        self.video_var = tk.StringVar()
        self.draft_name_var = tk.StringVar()
        self.drafts_dir_var = tk.StringVar(value=default_capcut_drafts_dir() or "")

        self.whisper_model_var = tk.StringVar(value="medium")
        self.language_var = tk.StringVar(value="ko")

        self.silence_db_var = tk.DoubleVar(value=-30.0)
        self.min_silence_var = tk.DoubleVar(value=0.6)
        self.silence_edge_padding_var = tk.DoubleVar(value=0.12)

        self.max_filler_duration_var = tk.DoubleVar(value=0.6)
        self.repeat_max_gap_var = tk.DoubleVar(value=0.3)
        self.repeat_min_count_var = tk.IntVar(value=2)
        self.filler_edge_expand_var = tk.DoubleVar(value=0.05)

        self.min_keep_duration_var = tk.DoubleVar(value=0.12)
        self.min_cut_duration_var = tk.DoubleVar(value=0.15)

        self.subtitle_max_chars_var = tk.IntVar(value=24)
        self.subtitle_max_duration_var = tk.DoubleVar(value=5.0)
        self.subtitle_max_gap_var = tk.DoubleVar(value=0.6)
        self.subtitle_size_var = tk.DoubleVar(value=8.0)

        self.enable_silence_cut_var = tk.BooleanVar(value=True)
        self.enable_filler_cut_var = tk.BooleanVar(value=True)
        self.enable_repetition_cut_var = tk.BooleanVar(value=True)
        self.enable_subtitles_var = tk.BooleanVar(value=True)
        self.dry_run_var = tk.BooleanVar(value=True)

    # ------------------------------------------------------------ widgets
    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.X)

        basic = ttk.Frame(notebook, padding=10)
        advanced = ttk.Frame(notebook, padding=10)
        notebook.add(basic, text="기본 설정")
        notebook.add(advanced, text="고급 설정")

        self._build_basic_tab(basic)
        self._build_advanced_tab(advanced)

        run_row = ttk.Frame(outer, padding=(0, 10))
        run_row.pack(fill=tk.X)
        self.run_button = ttk.Button(run_row, text="실행", command=self._on_run)
        self.run_button.pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(run_row, mode="indeterminate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        log_frame = ttk.LabelFrame(outer, text="진행 로그", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=14, state=tk.DISABLED, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_basic_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(parent, text="영상 파일").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self.video_var).grid(row=row, column=1, sticky=tk.EW, padx=5)
        ttk.Button(parent, text="찾아보기", command=self._pick_video).grid(row=row, column=2)
        row += 1

        ttk.Label(parent, text="드래프트 이름").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self.draft_name_var).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, padx=5
        )
        row += 1

        ttk.Label(parent, text="CapCut 드래프트 폴더").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self.drafts_dir_var).grid(row=row, column=1, sticky=tk.EW, padx=5)
        ttk.Button(parent, text="찾아보기", command=self._pick_drafts_dir).grid(row=row, column=2)
        row += 1

        ttk.Button(parent, text="기본 경로 자동 감지", command=self._detect_drafts_dir).grid(
            row=row, column=1, sticky=tk.W, padx=5, pady=(0, 8)
        )
        row += 1

        ttk.Label(parent, text="음성 인식 모델").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            parent, textvariable=self.whisper_model_var, values=WHISPER_MODELS, state="readonly", width=12
        ).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1

        ttk.Label(parent, text="언어 코드").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self.language_var, width=12).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=8)
        row += 1

        ttk.Checkbutton(parent, text="무음 구간 자동 컷", variable=self.enable_silence_cut_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W
        )
        row += 1
        ttk.Checkbutton(parent, text="필러워드(어/음/그...) 자동 컷", variable=self.enable_filler_cut_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W
        )
        row += 1
        ttk.Checkbutton(parent, text="반복(말더듬) 자동 컷", variable=self.enable_repetition_cut_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W
        )
        row += 1
        ttk.Checkbutton(parent, text="자막 자동 생성", variable=self.enable_subtitles_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W
        )
        row += 1
        ttk.Checkbutton(
            parent,
            text="미리보기만 실행 (CapCut 드래프트를 만들지 않고 컷/자막 리포트만 생성)",
            variable=self.dry_run_var,
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

    def _build_advanced_tab(self, parent: ttk.Frame) -> None:
        fields = [
            ("무음 판정 기준(dB)", self.silence_db_var),
            ("최소 무음 길이(초)", self.min_silence_var),
            ("무음 컷 경계 여유(초)", self.silence_edge_padding_var),
            ("필러워드 최대 길이(초)", self.max_filler_duration_var),
            ("반복 판정 최대 간격(초)", self.repeat_max_gap_var),
            ("반복 판정 최소 횟수", self.repeat_min_count_var),
            ("필러/반복 컷 경계 확장(초)", self.filler_edge_expand_var),
            ("컷 사이 최소 유지 길이(초)", self.min_keep_duration_var),
            ("최소 컷 길이(초)", self.min_cut_duration_var),
            ("자막 한 줄 최대 글자 수", self.subtitle_max_chars_var),
            ("자막 한 줄 최대 길이(초)", self.subtitle_max_duration_var),
            ("자막 줄바꿈 간격(초)", self.subtitle_max_gap_var),
            ("자막 크기", self.subtitle_size_var),
        ]
        parent.columnconfigure(1, weight=1)
        for i, (label, var) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(parent, textvariable=var, width=12).grid(row=i, column=1, sticky=tk.W, padx=5)

    # ---------------------------------------------------------------- ops
    def _pick_video(self) -> None:
        path = filedialog.askopenfilename(
            title="영상 파일 선택",
            filetypes=[("영상 파일", "*.mp4 *.mov *.mkv *.avi"), ("모든 파일", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def _pick_drafts_dir(self) -> None:
        path = filedialog.askdirectory(title="CapCut 드래프트 폴더 선택")
        if path:
            self.drafts_dir_var.set(path)

    def _detect_drafts_dir(self) -> None:
        detected = default_capcut_drafts_dir()
        if detected:
            self.drafts_dir_var.set(detected)
        else:
            messagebox.showwarning(
                "자동 감지 실패", "이 OS에서는 기본 경로를 추정할 수 없습니다. 직접 선택해 주세요."
            )

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _collect_options(self) -> PipelineOptions:
        return PipelineOptions(
            video=self.video_var.get().strip(),
            draft_name=self.draft_name_var.get().strip(),
            capcut_drafts_dir=self.drafts_dir_var.get().strip() or None,
            whisper_model=self.whisper_model_var.get(),
            language=self.language_var.get().strip() or "ko",
            silence_db=self.silence_db_var.get(),
            min_silence=self.min_silence_var.get(),
            silence_edge_padding=self.silence_edge_padding_var.get(),
            max_filler_duration=self.max_filler_duration_var.get(),
            repeat_max_gap=self.repeat_max_gap_var.get(),
            repeat_min_count=self.repeat_min_count_var.get(),
            filler_edge_expand=self.filler_edge_expand_var.get(),
            min_keep_duration=self.min_keep_duration_var.get(),
            min_cut_duration=self.min_cut_duration_var.get(),
            subtitle_max_chars=self.subtitle_max_chars_var.get(),
            subtitle_max_duration=self.subtitle_max_duration_var.get(),
            subtitle_max_gap=self.subtitle_max_gap_var.get(),
            subtitle_size=self.subtitle_size_var.get(),
            disable_silence_cut=not self.enable_silence_cut_var.get(),
            disable_filler_cut=not self.enable_filler_cut_var.get(),
            disable_repetition_cut=not self.enable_repetition_cut_var.get(),
            disable_subtitles=not self.enable_subtitles_var.get(),
            dry_run=self.dry_run_var.get(),
        )

    def _on_run(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        if not self.video_var.get().strip():
            messagebox.showerror("입력 오류", "영상 파일을 선택해 주세요.")
            return
        if not self.draft_name_var.get().strip():
            messagebox.showerror("입력 오류", "드래프트 이름을 입력해 주세요.")
            return
        if not self.dry_run_var.get() and not self.drafts_dir_var.get().strip():
            messagebox.showerror(
                "입력 오류", "CapCut 드래프트 폴더를 지정하거나 '미리보기만 실행'을 체크해 주세요."
            )
            return

        try:
            opts = self._collect_options()
        except tk.TclError as exc:
            messagebox.showerror("입력 오류", f"숫자 입력값을 확인해 주세요: {exc}")
            return

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

        self.run_button.configure(state=tk.DISABLED)
        self.progress.start(12)

        self._worker = threading.Thread(target=self._run_worker, args=(opts,), daemon=True)
        self._worker.start()

    def _run_worker(self, opts: PipelineOptions) -> None:
        def log(message: str) -> None:
            self._msg_queue.put(("log", message))

        try:
            result = run_pipeline(opts, log=log)
            self._msg_queue.put(("done", result))
        except PipelineError as exc:
            self._msg_queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 - GUI 오류는 원인 그대로 사용자에게 노출
            self._msg_queue.put(("error", f"예상치 못한 오류: {exc}"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    self._on_finished(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._on_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_finished(self, result: PipelineResult) -> None:
        self.progress.stop()
        self.run_button.configure(state=tk.NORMAL)
        summary = (
            f"원본 {result.total_duration:.1f}s -> 편집 후 {result.kept_duration:.1f}s "
            f"({result.removed_pct:.1f}% 제거, 컷 {result.num_cuts}개, 자막 {result.num_subtitle_lines}줄)"
        )
        self._append_log(f"\n완료: {summary}")
        messagebox.showinfo("완료", summary)

    def _on_error(self, message: str) -> None:
        self.progress.stop()
        self.run_button.configure(state=tk.NORMAL)
        self._append_log(f"\n오류: {message}")
        messagebox.showerror("오류", message)


def main() -> None:
    root = tk.Tk()
    CapCutAutoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
