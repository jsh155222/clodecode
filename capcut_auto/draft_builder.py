"""pycapcut을 사용해 컷 편집 + 자막이 반영된 CapCut 드래프트를 생성한다."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Optional, Sequence

from .subtitles import SubtitleLine
from .timeline import Interval

SEC = 1_000_000  # microseconds


def default_capcut_drafts_dir() -> Optional[str]:
    """OS별로 CapCut 드래프트 기본 경로를 추정한다 (설치 환경에 따라 다를 수 있음).

    CapCut 버전/지역(국제판 vs 剪映)에 따라 실제 경로가 다를 수 있으므로,
    가능하면 CLI에서 --capcut-drafts-dir로 명시하는 것을 권장한다.
    """
    system = platform.system()
    home = os.path.expanduser("~")
    if system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        return os.path.join(local_appdata, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    if system == "Darwin":
        return os.path.join(home, "Movies", "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return None  # Linux: CapCut 데스크톱 앱 미지원, 경로 없음


@dataclass
class SubtitleAppearance:
    size: float = 8.0
    color: tuple = (1.0, 1.0, 1.0)
    bold: bool = True
    align: int = 1  # 0=left, 1=center, 2=right


def build_draft(
    video_path: str,
    keep_intervals: Sequence[Interval],
    subtitle_lines: Sequence[SubtitleLine],
    draft_name: str,
    capcut_drafts_dir: str,
    width: int = 1920,
    height: int = 1080,
    subtitle_appearance: Optional[SubtitleAppearance] = None,
    video_track_name: str = "video",
    subtitle_track_name: str = "subtitle",
    hook_text: Optional[str] = None,
    hook_duration: float = 2.5,
    hook_appearance: Optional[SubtitleAppearance] = None,
    hook_track_name: str = "hook",
) -> str:
    """keep_intervals(남길 구간)만 이어붙인 영상 트랙과, 리타이밍된 자막 트랙을 가진
    CapCut 드래프트를 생성하고 저장한다.

    hook_text를 지정하면 영상 맨 앞(0초 ~ hook_duration초)에 별도의 "hook" 텍스트
    트랙을 추가한다. 자막 트랙과 별개 트랙이므로 자막과 겹쳐도 서로 간섭하지 않는다.

    Returns:
        생성된 드래프트 이름.
    """
    try:
        import pycapcut as cc
    except ImportError as exc:  # pragma: no cover - 환경 의존적
        raise RuntimeError("pycapcut이 설치되어 있지 않습니다. `pip install pycapcut`으로 설치하세요.") from exc

    appearance = subtitle_appearance or SubtitleAppearance()

    draft_folder = cc.DraftFolder(capcut_drafts_dir)
    script = draft_folder.create_draft(draft_name, width, height)

    script.add_track(cc.TrackType.video, track_name=video_track_name)
    script.add_track(cc.TrackType.text, track_name=subtitle_track_name)
    if hook_text:
        script.add_track(cc.TrackType.text, track_name=hook_track_name)

    cursor_us = 0
    for iv in keep_intervals:
        duration_us = int(round(iv.duration * SEC))
        if duration_us <= 0:
            continue
        source_start_us = int(round(iv.start * SEC))
        target_tr = cc.Timerange(cursor_us, duration_us)
        source_tr = cc.Timerange(source_start_us, duration_us)
        video_seg = cc.VideoSegment(video_path, target_tr, source_timerange=source_tr)
        script.add_segment(video_seg, video_track_name)
        cursor_us += duration_us

    style = cc.TextStyle(
        size=appearance.size,
        color=appearance.color,
        bold=appearance.bold,
        align=appearance.align,
    )
    for line in subtitle_lines:
        duration_us = int(round((line.end - line.start) * SEC))
        if duration_us <= 0:
            continue
        start_us = int(round(line.start * SEC))
        text_tr = cc.Timerange(start_us, duration_us)
        text_seg = cc.TextSegment(line.text, text_tr, style=style)
        script.add_segment(text_seg, subtitle_track_name)

    if hook_text:
        h_appearance = hook_appearance or SubtitleAppearance(size=appearance.size * 1.5, bold=True)
        hook_style = cc.TextStyle(
            size=h_appearance.size,
            color=h_appearance.color,
            bold=h_appearance.bold,
            align=h_appearance.align,
        )
        hook_duration_us = int(round(hook_duration * SEC))
        hook_tr = cc.Timerange(0, hook_duration_us)
        hook_seg = cc.TextSegment(hook_text, hook_tr, style=hook_style)
        script.add_segment(hook_seg, hook_track_name)

    script.save()
    return draft_name
