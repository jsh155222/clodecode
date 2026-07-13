"""무음/버벅임 자동 컷 + 자막 생성 파이프라인 (CLI와 GUI가 공유하는 핵심 로직).

CLI(`cli.py`)와 데스크톱 GUI(`gui.py`)가 동일한 오케스트레이션을 재사용하도록
옵션(PipelineOptions)과 결과(PipelineResult)를 데이터클래스로 분리하고,
진행 상황은 `log` 콜백을 통해 호출자에게 전달한다(CLI는 print, GUI는 위젯 갱신).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import cutlist as cutlist_mod
from . import silence as silence_mod
from . import stutter as stutter_mod
from . import subtitles as subtitles_mod
from .draft_builder import SubtitleAppearance, build_draft, default_capcut_drafts_dir
from .transcribe import transcribe as transcribe_audio

LogFn = Callable[[str], None]


@dataclass
class PipelineOptions:
    video: str
    draft_name: str
    capcut_drafts_dir: Optional[str] = None
    workdir: Optional[str] = None
    width: int = 1920
    height: int = 1080

    whisper_model: str = "medium"
    language: str = "ko"

    silence_db: float = -30.0
    min_silence: float = 0.6
    silence_edge_padding: float = 0.12

    max_filler_duration: float = 0.6
    repeat_max_gap: float = 0.3
    repeat_min_count: int = 2
    filler_edge_expand: float = 0.05

    min_keep_duration: float = 0.12
    min_cut_duration: float = 0.15

    subtitle_max_chars: int = 24
    subtitle_max_duration: float = 5.0
    subtitle_max_gap: float = 0.6
    subtitle_size: float = 8.0

    disable_silence_cut: bool = False
    disable_filler_cut: bool = False
    disable_repetition_cut: bool = False
    disable_subtitles: bool = False

    dry_run: bool = False


@dataclass
class PipelineResult:
    total_duration: float
    kept_duration: float
    removed_duration: float
    removed_pct: float
    num_cuts: int
    num_subtitle_lines: int
    report_path: str
    srt_path: Optional[str]
    draft_name: Optional[str]  # dry-run이면 None


class PipelineError(RuntimeError):
    """파이프라인 실행 중 발생한, 사용자에게 그대로 보여줄 수 있는 오류."""


def _noop_log(_msg: str) -> None:
    pass


def run_pipeline(opts: PipelineOptions, log: LogFn = _noop_log) -> PipelineResult:
    video_path = Path(opts.video)
    if not video_path.exists():
        raise PipelineError(f"영상 파일을 찾을 수 없습니다: {video_path}")

    workdir = Path(opts.workdir) if opts.workdir else Path("capcut_auto_work") / opts.draft_name
    workdir.mkdir(parents=True, exist_ok=True)

    log(f"[1/6] 길이 확인 및 오디오 추출: {video_path}")
    total_duration = silence_mod.get_duration(str(video_path))
    audio_path = silence_mod.extract_audio(str(video_path), str(workdir / "audio.wav"))

    silence_intervals = []
    if not opts.disable_silence_cut:
        log("[2/6] 무음 구간 탐지 중...")
        silence_intervals = silence_mod.detect_silence(
            audio_path, noise_db=opts.silence_db, min_silence_duration=opts.min_silence
        )
        log(f"      무음 구간 {len(silence_intervals)}개 발견")

    log("[3/6] 음성 인식 중 (faster-whisper, 시간이 걸릴 수 있습니다)...")
    words = transcribe_audio(audio_path, model_size=opts.whisper_model, language=opts.language)
    log(f"      단어 {len(words)}개 인식")

    filler_intervals = []
    repetition_intervals = []
    if not opts.disable_filler_cut:
        filler_intervals = stutter_mod.detect_filler_words(words, max_filler_duration=opts.max_filler_duration)
    if not opts.disable_repetition_cut:
        repetition_intervals = stutter_mod.detect_repetitions(
            words, max_gap=opts.repeat_max_gap, min_repeats=opts.repeat_min_count
        )
    log(f"[4/6] 필러워드 {len(filler_intervals)}개, 반복(말더듬) {len(repetition_intervals)}개 발견")

    config = cutlist_mod.CutlistConfig(
        silence_edge_padding=opts.silence_edge_padding,
        filler_edge_expand=opts.filler_edge_expand,
        min_keep_duration=opts.min_keep_duration,
        min_cut_duration=opts.min_cut_duration,
    )
    result = cutlist_mod.build_cutlist(
        total_duration, silence_intervals, filler_intervals, repetition_intervals, config
    )
    removed_pct = (result.removed_duration / total_duration * 100) if total_duration else 0.0
    log(
        f"[5/6] 컷 리스트 완료: 원본 {total_duration:.1f}s -> 편집 후 {result.kept_duration:.1f}s "
        f"({removed_pct:.1f}% 제거, 컷 {len(result.cut_intervals)}개)"
    )

    srt_lines = []
    srt_path = None
    if not opts.disable_subtitles:
        remapped_words = subtitles_mod.remap_words_to_new_timeline(words, result.keep_intervals)
        srt_lines = subtitles_mod.group_words_into_lines(
            remapped_words,
            max_chars=opts.subtitle_max_chars,
            max_duration=opts.subtitle_max_duration,
            max_gap=opts.subtitle_max_gap,
        )
        srt_path = subtitles_mod.write_srt(srt_lines, str(workdir / "subtitle.srt"))
        log(f"      자막 {len(srt_lines)}줄 생성 -> {srt_path}")

    report = {
        "video": str(video_path),
        "total_duration_sec": total_duration,
        "kept_duration_sec": result.kept_duration,
        "removed_duration_sec": result.removed_duration,
        "removed_pct": removed_pct,
        "cut_intervals": [[iv.start, iv.end] for iv in result.cut_intervals],
        "keep_intervals": [[iv.start, iv.end] for iv in result.keep_intervals],
        "subtitle_lines": [[l.start, l.end, l.text] for l in srt_lines],
        "srt_path": srt_path,
    }
    report_path = workdir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"      분석 리포트 저장 -> {report_path}")

    draft_name_out = None
    if opts.dry_run:
        log("[6/6] dry-run 지정됨: CapCut 드래프트 생성을 건너뜁니다.")
    else:
        drafts_dir = opts.capcut_drafts_dir or default_capcut_drafts_dir()
        if not drafts_dir:
            raise PipelineError(
                "CapCut 드래프트 폴더 경로를 찾을 수 없습니다. 직접 지정해 주세요."
            )
        log(f"[6/6] CapCut 드래프트 생성 중: {drafts_dir}/{opts.draft_name}")
        draft_name_out = build_draft(
            video_path=str(video_path),
            keep_intervals=result.keep_intervals,
            subtitle_lines=srt_lines,
            draft_name=opts.draft_name,
            capcut_drafts_dir=drafts_dir,
            width=opts.width,
            height=opts.height,
            subtitle_appearance=SubtitleAppearance(size=opts.subtitle_size),
        )
        log("완료! CapCut에서 드래프트를 열어 확인하세요.")

    return PipelineResult(
        total_duration=total_duration,
        kept_duration=result.kept_duration,
        removed_duration=result.removed_duration,
        removed_pct=removed_pct,
        num_cuts=len(result.cut_intervals),
        num_subtitle_lines=len(srt_lines),
        report_path=str(report_path),
        srt_path=srt_path,
        draft_name=draft_name_out,
    )
