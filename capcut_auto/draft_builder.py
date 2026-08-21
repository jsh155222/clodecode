"""pycapcut을 사용해 컷 편집 + 자막이 반영된 CapCut 드래프트를 생성한다."""

from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

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
class TextBorderSpec:
    """pycapcut TextBorder에 그대로 대응 - build_draft에서만 cc.TextBorder로 변환한다
    (pycapcut이 설치되어 있지 않아도 이 모듈을 import/테스트할 수 있게 하기 위함)."""

    color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    width: float = 40.0
    alpha: float = 1.0


@dataclass
class TextBackgroundSpec:
    """pycapcut TextBackground에 그대로 대응. 같은 이유로 여기선 순수 데이터클래스로만 둔다."""

    color: str = "#000000"
    alpha: float = 0.65
    style: int = 1
    round_radius: float = 0.0
    height: float = 0.16
    width: float = 0.6
    horizontal_offset: float = 0.5
    vertical_offset: float = 0.5


@dataclass
class SubtitleAppearance:
    size: float = 8.0
    color: tuple = (1.0, 1.0, 1.0)
    bold: bool = True
    align: int = 1  # 0=left, 1=center, 2=right
    # pycapcut ClipSettings.transform_y와 동일한 단위(캔버스 절반 높이 = 1.0, 화면 중앙이 0,
    # 위가 양수/아래가 음수). CapCut이 자체적으로 자막을 넣을 때 쓰는 기본값은 -0.8(화면 맨
    # 아래쪽) - 여기서는 화면 중앙보다는 아래쪽이면서 조금 더 여유를 둔 -0.6을 기본값으로 쓴다.
    vertical_position: float = -0.6
    border: Optional[TextBorderSpec] = None
    background: Optional[TextBackgroundSpec] = None


# 사용자가 "2/3 위 / 중간 / 2/3 아래" 중 고를 수 있는 세로 위치 프리셋.
SUBTITLE_POSITION_PRESETS: Dict[str, float] = {
    "upper": 0.6,
    "middle": 0.0,
    "lower": -0.6,
}
SUBTITLE_POSITION_LABELS: Dict[str, str] = {
    "upper": "화면 위쪽 (2/3 지점)",
    "middle": "화면 중앙",
    "lower": "화면 아래쪽 (2/3 지점, 기본)",
}

# 자막 스타일 프리셋. GUI에서 이름으로 고르면 build_subtitle_appearance()가 실제
# SubtitleAppearance로 변환한다.
SUBTITLE_STYLE_PRESETS: Dict[str, dict] = {
    "default": {"color": (1.0, 1.0, 1.0), "bold": True, "border": None, "background": None},
    "yellow_outline": {
        "color": (1.0, 0.85, 0.0),
        "bold": True,
        "border": TextBorderSpec(color=(0.0, 0.0, 0.0), width=40.0),
        "background": None,
    },
    "white_outline": {
        "color": (1.0, 1.0, 1.0),
        "bold": True,
        "border": TextBorderSpec(color=(0.0, 0.0, 0.0), width=30.0),
        "background": None,
    },
    "black_box": {
        "color": (1.0, 1.0, 1.0),
        "bold": True,
        "border": None,
        "background": TextBackgroundSpec(color="#000000", alpha=0.65, width=0.6, height=0.16),
    },
}
SUBTITLE_STYLE_LABELS: Dict[str, str] = {
    "default": "기본 (흰 글씨)",
    "yellow_outline": "노란 글씨 + 검정 테두리",
    "white_outline": "흰 글씨 + 검정 테두리",
    "black_box": "흰 글씨 + 검정 배경 박스",
}


def build_subtitle_appearance(style: str = "default", position: str = "lower", size: float = 8.0) -> SubtitleAppearance:
    """스타일/위치 프리셋 이름으로 SubtitleAppearance를 만든다."""
    preset = SUBTITLE_STYLE_PRESETS.get(style, SUBTITLE_STYLE_PRESETS["default"])
    vertical_position = SUBTITLE_POSITION_PRESETS.get(position, SUBTITLE_POSITION_PRESETS["lower"])
    return SubtitleAppearance(
        size=size,
        color=preset["color"],
        bold=preset["bold"],
        vertical_position=vertical_position,
        border=preset["border"],
        background=preset["background"],
    )


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

    def _border_and_background(a: SubtitleAppearance):
        border_obj = None
        if a.border:
            border_obj = cc.TextBorder(color=a.border.color, width=a.border.width, alpha=a.border.alpha)
        background_obj = None
        if a.background:
            background_obj = cc.TextBackground(
                color=a.background.color,
                style=a.background.style,
                alpha=a.background.alpha,
                round_radius=a.background.round_radius,
                height=a.background.height,
                width=a.background.width,
                horizontal_offset=a.background.horizontal_offset,
                vertical_offset=a.background.vertical_offset,
            )
        return border_obj, background_obj

    style = cc.TextStyle(
        size=appearance.size,
        color=appearance.color,
        bold=appearance.bold,
        align=appearance.align,
    )
    clip_settings = cc.ClipSettings(transform_y=appearance.vertical_position)
    border, background = _border_and_background(appearance)
    for line in subtitle_lines:
        duration_us = int(round((line.end - line.start) * SEC))
        if duration_us <= 0:
            continue
        start_us = int(round(line.start * SEC))
        text_tr = cc.Timerange(start_us, duration_us)
        text_seg = cc.TextSegment(
            line.text, text_tr, style=style, clip_settings=clip_settings, border=border, background=background
        )
        script.add_segment(text_seg, subtitle_track_name)

    if hook_text:
        # 훅 텍스트는 자막과 같은 화면 구간(영상 맨 앞)에 동시에 뜰 수 있으므로, 자막과
        # 같은 하단 위치를 쓰면 서로 겹쳐 보인다 - 기본값은 화면 중앙으로 띄운다.
        h_appearance = hook_appearance or SubtitleAppearance(
            size=appearance.size * 1.5, bold=True, vertical_position=0.0
        )
        hook_style = cc.TextStyle(
            size=h_appearance.size,
            color=h_appearance.color,
            bold=h_appearance.bold,
            align=h_appearance.align,
        )
        hook_clip_settings = cc.ClipSettings(transform_y=h_appearance.vertical_position)
        hook_border, hook_background = _border_and_background(h_appearance)
        hook_duration_us = int(round(hook_duration * SEC))
        hook_tr = cc.Timerange(0, hook_duration_us)
        hook_seg = cc.TextSegment(
            hook_text,
            hook_tr,
            style=hook_style,
            clip_settings=hook_clip_settings,
            border=hook_border,
            background=hook_background,
        )
        script.add_segment(hook_seg, hook_track_name)

    script.save()
    _fix_draft_ids(capcut_drafts_dir, draft_name)
    return draft_name


def _fix_draft_ids(capcut_drafts_dir: str, draft_name: str) -> None:
    """pycapcut 0.0.3은 draft_content.json의 최상위 `id`와 draft_meta_info.json의
    `draft_id`를 매번 동일한 번들 템플릿 값으로 남겨둔다 (`DraftFolder.create_draft`가
    `draft_meta_info.json`을 그대로 복사만 하고, `ScriptFile.dumps()`도 `id`를 갱신하지
    않기 때문 - 실제 설치된 pycapcut 0.0.3 소스로 확인함). 이 프로젝트처럼 같은 CapCut
    드래프트 폴더에 여러 드래프트를 반복 생성하면 모든 드래프트가 동일한 id를 갖게 되어,
    CapCut이 내부적으로 id를 키로 쓰는 경우(썸네일/최근 항목 캐시 등) 서로 덮어쓸 위험이
    있다. 여기서 매 드래프트마다 새 UUID를 부여하고, 메타 정보의 이름/길이도 실제 값으로
    채워 최소한의 구조적 정합성을 맞춘다.
    """
    draft_dir = os.path.join(capcut_drafts_dir, draft_name)
    content_path = os.path.join(draft_dir, "draft_content.json")
    meta_path = os.path.join(draft_dir, "draft_meta_info.json")

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    content_id = str(uuid.uuid4()).upper()
    content["id"] = content_id
    duration_us = content.get("duration", 0)
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=4)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["draft_id"] = str(uuid.uuid4()).upper()
    meta["draft_name"] = draft_name
    meta["tm_duration"] = duration_us
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)
