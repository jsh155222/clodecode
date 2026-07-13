"""CLI: 무음/버벅임 자동 컷 + 자막 생성 CapCut 드래프트 파이프라인.

사용 예:
    python -m capcut_auto.cli \\
        --video input.mp4 \\
        --draft-name my_project \\
        --capcut-drafts-dir "/path/to/CapCut/User Data/Projects/com.lveditor.draft"
"""

from __future__ import annotations

import argparse
import sys

from .pipeline import PipelineError, PipelineOptions, run_pipeline


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


def _options_from_args(args: argparse.Namespace) -> PipelineOptions:
    return PipelineOptions(
        video=args.video,
        draft_name=args.draft_name,
        capcut_drafts_dir=args.capcut_drafts_dir,
        workdir=args.workdir,
        width=args.width,
        height=args.height,
        whisper_model=args.whisper_model,
        language=args.language,
        silence_db=args.silence_db,
        min_silence=args.min_silence,
        silence_edge_padding=args.silence_edge_padding,
        max_filler_duration=args.max_filler_duration,
        repeat_max_gap=args.repeat_max_gap,
        repeat_min_count=args.repeat_min_count,
        filler_edge_expand=args.filler_edge_expand,
        min_keep_duration=args.min_keep_duration,
        min_cut_duration=args.min_cut_duration,
        subtitle_max_chars=args.subtitle_max_chars,
        subtitle_max_duration=args.subtitle_max_duration,
        subtitle_max_gap=args.subtitle_max_gap,
        subtitle_size=args.subtitle_size,
        disable_silence_cut=args.disable_silence_cut,
        disable_filler_cut=args.disable_filler_cut,
        disable_repetition_cut=args.disable_repetition_cut,
        disable_subtitles=args.disable_subtitles,
        dry_run=args.dry_run,
    )


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    opts = _options_from_args(args)
    try:
        run_pipeline(opts, log=print)
    except PipelineError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
