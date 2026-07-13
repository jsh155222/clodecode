"""CLI: 무음/버벅임 자동 컷 + 자막 생성 CapCut 드래프트 파이프라인.

사용 예:
    python -m capcut_auto.cli \\
        --video input.mp4 \\
        --draft-name my_project \\
        --capcut-drafts-dir "/path/to/CapCut/User Data/Projects/com.lveditor.draft"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cutlist as cutlist_mod
from . import silence as silence_mod
from . import stutter as stutter_mod
from . import subtitles as subtitles_mod
from .draft_builder import SubtitleAppearance, build_draft, default_capcut_drafts_dir
from .transcribe import transcribe as transcribe_audio


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="pycapcut 기반 CapCut 자동 컷/자막 편집기")
    p.add_argument("--video", required=True, help="입력 영상 파일 경로")
    p.add_argument("--draft-name", required=True, help="생성할 CapCut 드래프트 이름")
    p.add_argument(
        "--capcut-drafts-dir",
        default=None,
        help="CapCut 드래프트 폴더 경로 (미지정 시 OS별 기본 경로 추정, 실패 시 오류)",
    )
    p.add_argument("--workdir", default=None, help="임시 작업 폴더 (오디오/SRT/리포트 저장, 기본: ./capcut_auto_work/<draft-name>)")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)

    p.add_argument("--whisper-model", default="medium", help="faster-whisper 모델 크기 (tiny/base/small/medium/large-v3)")
    p.add_argument("--language", default="ko")

    p.add_argument("--silence-db", type=float, default=-30.0, help="이보다 조용하면 무음으로 간주(dB)")
    p.add_argument("--min-silence", type=float, default=0.6, help="이 시간(초) 이상 지속되어야 무음 구간 인정")
    p.add_argument("--silence-edge-padding", type=float, default=0.12, help="무음 컷 경계에 남길 정적 여유(초)")

    p.add_argument("--max-filler-duration", type=float, default=0.6, help="필러워드로 인정할 최대 발화 길이(초)")
    p.add_argument("--repeat-max-gap", type=float, default=0.3, help="반복(말더듬)으로 볼 단어 간 최대 간격(초)")
    p.add_argument("--repeat-min-count", type=int, default=2, help="반복으로 볼 최소 연속 횟수")
    p.add_argument("--filler-edge-expand", type=float, default=0.05, help="필러/반복 컷 경계 확장(초)")

    p.add_argument("--min-keep-duration", type=float, default=0.12, help="컷 사이 잔여 구간 최소 길이(초, 미만이면 흡수)")
    p.add_argument("--min-cut-duration", type=float, default=0.15, help="이보다 짧은 컷은 무시")

    p.add_argument("--subtitle-max-chars", type=int, default=24)
    p.add_argument("--subtitle-max-duration", type=float, default=5.0)
    p.add_argument("--subtitle-max-gap", type=float, default=0.6)
    p.add_argument("--subtitle-size", type=float, default=8.0)

    p.add_argument("--disable-silence-cut", action="store_true", help="무음 구간 자동 컷 비활성화")
    p.add_argument("--disable-filler-cut", action="store_true", help="필러워드 자동 컷 비활성화")
    p.add_argument("--disable-repetition-cut", action="store_true", help="반복(말더듬) 자동 컷 비활성화")
    p.add_argument("--disable-subtitles", action="store_true", help="자막 생성 비활성화")

    p.add_argument("--dry-run", action="store_true", help="CapCut 드래프트를 생성하지 않고 분석 리포트만 출력")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"오류: 영상 파일을 찾을 수 없습니다: {video_path}", file=sys.stderr)
        return 1

    workdir = Path(args.workdir) if args.workdir else Path("capcut_auto_work") / args.draft_name
    workdir.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] 길이 확인 및 오디오 추출: {video_path}")
    total_duration = silence_mod.get_duration(str(video_path))
    audio_path = silence_mod.extract_audio(str(video_path), str(workdir / "audio.wav"))

    silence_intervals = []
    if not args.disable_silence_cut:
        print("[2/6] 무음 구간 탐지 중...")
        silence_intervals = silence_mod.detect_silence(
            audio_path, noise_db=args.silence_db, min_silence_duration=args.min_silence
        )
        print(f"      무음 구간 {len(silence_intervals)}개 발견")

    print("[3/6] 음성 인식 중 (faster-whisper, 시간이 걸릴 수 있습니다)...")
    words = transcribe_audio(audio_path, model_size=args.whisper_model, language=args.language)
    print(f"      단어 {len(words)}개 인식")

    filler_intervals = []
    repetition_intervals = []
    if not args.disable_filler_cut:
        filler_intervals = stutter_mod.detect_filler_words(words, max_filler_duration=args.max_filler_duration)
    if not args.disable_repetition_cut:
        repetition_intervals = stutter_mod.detect_repetitions(
            words, max_gap=args.repeat_max_gap, min_repeats=args.repeat_min_count
        )
    print(f"[4/6] 필러워드 {len(filler_intervals)}개, 반복(말더듬) {len(repetition_intervals)}개 발견")

    config = cutlist_mod.CutlistConfig(
        silence_edge_padding=args.silence_edge_padding,
        filler_edge_expand=args.filler_edge_expand,
        min_keep_duration=args.min_keep_duration,
        min_cut_duration=args.min_cut_duration,
    )
    result = cutlist_mod.build_cutlist(
        total_duration, silence_intervals, filler_intervals, repetition_intervals, config
    )
    removed_pct = (result.removed_duration / total_duration * 100) if total_duration else 0.0
    print(
        f"[5/6] 컷 리스트 완료: 원본 {total_duration:.1f}s -> 편집 후 {result.kept_duration:.1f}s "
        f"({removed_pct:.1f}% 제거, 컷 {len(result.cut_intervals)}개)"
    )

    srt_lines = []
    srt_path = None
    if not args.disable_subtitles:
        remapped_words = subtitles_mod.remap_words_to_new_timeline(words, result.keep_intervals)
        srt_lines = subtitles_mod.group_words_into_lines(
            remapped_words,
            max_chars=args.subtitle_max_chars,
            max_duration=args.subtitle_max_duration,
            max_gap=args.subtitle_max_gap,
        )
        srt_path = subtitles_mod.write_srt(srt_lines, str(workdir / "subtitle.srt"))
        print(f"      자막 {len(srt_lines)}줄 생성 -> {srt_path}")

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
    print(f"      분석 리포트 저장 -> {report_path}")

    if args.dry_run:
        print("[6/6] --dry-run 지정됨: CapCut 드래프트 생성을 건너뜁니다.")
        return 0

    drafts_dir = args.capcut_drafts_dir or default_capcut_drafts_dir()
    if not drafts_dir:
        print(
            "오류: CapCut 드래프트 폴더 경로를 찾을 수 없습니다. "
            "--capcut-drafts-dir 로 직접 지정하세요.",
            file=sys.stderr,
        )
        return 1

    print(f"[6/6] CapCut 드래프트 생성 중: {drafts_dir}/{args.draft_name}")
    build_draft(
        video_path=str(video_path),
        keep_intervals=result.keep_intervals,
        subtitle_lines=srt_lines,
        draft_name=args.draft_name,
        capcut_drafts_dir=drafts_dir,
        width=args.width,
        height=args.height,
        subtitle_appearance=SubtitleAppearance(size=args.subtitle_size),
    )
    print("완료! CapCut에서 드래프트를 열어 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
