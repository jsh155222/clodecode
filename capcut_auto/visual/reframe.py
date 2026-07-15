"""9:16 자동 리프레이밍 + 자연스러운 줌.

기하 계산(compute_crop_window/smooth_crop_path)은 순수 함수다. 실제 화면에 적용하는
render_static_crop()/render_crop_preview_image()는 real ffmpeg crop+scale로 렌더링한다.

pycapcut의 ClipSettings(scale_x/scale_y/transform_x/transform_y)로 CapCut 드래프트
안에 직접 크롭을 넣는 방법도 있었지만, 이 환경에는 실제 CapCut이 없어 그 변환 수식이
CapCut에서 실제로 어떻게 보이는지 검증할 방법이 없다(SKILL.md에 이미 기록된 한계와 같은
문제). 대신 ffmpeg로 실제 크롭된 mp4를 미리 렌더링해 그 결과를 육안/파일로 직접 검증할 수
있는 방식을 택했다 - visual_correction.py의 밝기/흔들림 보정과 같은 접근이다. 다만 이
방식은 영상 전체에 하나의 정적(static) 크롭만 적용하고, smooth_crop_path()가 계산하는
프레임별 동적 팬/줌까지 실제 렌더링에 반영하지는 않는다(문서화된 범위 축소).

모든 화면 보정은 사용자 검토 후 적용한다 - apply_approved_reframe()이 그 게이트 역할을 한다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..silence import require_binary
from .subject_detection import BoundingBox

DEFAULT_TARGET_ASPECT = 9 / 16
DEFAULT_MAX_ZOOM = 1.35
DEFAULT_MARGIN_RATIO = 0.15

# 저해상도 영상은 줌 한도를 낮춘다 (세로 해상도 기준, 큰 것부터 확인)
_RESOLUTION_ZOOM_LIMITS: List[Tuple[int, float]] = [
    (720, DEFAULT_MAX_ZOOM),
    (480, 1.15),
    (0, 1.05),
]


@dataclass(frozen=True)
class CropWindow:
    x: float
    y: float
    width: float
    height: float
    zoom: float
    subject_fully_contained: bool

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)


def zoom_limit_for_resolution(frame_width: int, frame_height: int) -> float:
    """해상도가 낮을수록 디지털 줌 한도를 낮춘다."""
    short_side = min(frame_width, frame_height)
    for threshold, limit in _RESOLUTION_ZOOM_LIMITS:
        if short_side >= threshold:
            return limit
    return _RESOLUTION_ZOOM_LIMITS[-1][1]


def _base_crop_dims(frame_width: int, frame_height: int, target_aspect: float) -> Tuple[float, float]:
    crop_height = float(frame_height)
    crop_width = crop_height * target_aspect
    if crop_width > frame_width:
        crop_width = float(frame_width)
        crop_height = crop_width / target_aspect
    return crop_width, crop_height


def compute_crop_window(
    frame_width: int,
    frame_height: int,
    subject_bbox: Optional[BoundingBox],
    target_aspect: float = DEFAULT_TARGET_ASPECT,
    max_zoom: Optional[float] = None,
    margin_ratio: float = DEFAULT_MARGIN_RATIO,
) -> CropWindow:
    """9:16 크롭 윈도우를 계산한다.

    - 핵심 피사체(subject_bbox)가 화면 밖으로 나가지 않도록 필요한 최소 줌만 적용한다
      (이미 충분히 크면 확대하지 않음 - zoom은 항상 1.0 이상).
    - subject_bbox가 없으면(감지 실패/저신뢰도) 화면 중앙을 기준으로 zoom=1.0 크롭한다.
    - max_zoom을 넘어서면서까지 피사체를 다 담을 수 없는 경우, subject_fully_contained=False로
      정직하게 표시한다(줌을 억지로 더 키우지 않음 - 과도한 크롭 방지 규칙).
    """
    effective_max_zoom = max_zoom if max_zoom is not None else zoom_limit_for_resolution(frame_width, frame_height)
    base_width, base_height = _base_crop_dims(frame_width, frame_height, target_aspect)

    if subject_bbox is None:
        cx, cy = frame_width / 2.0, frame_height / 2.0
        zoom = 1.0
    else:
        cx, cy = subject_bbox.center
        needed_width = subject_bbox.width * (1 + margin_ratio * 2)
        needed_height = subject_bbox.height * (1 + margin_ratio * 2)
        zoom_for_width = base_width / needed_width if needed_width > 0 else 1.0
        zoom_for_height = base_height / needed_height if needed_height > 0 else 1.0
        zoom = min(max(1.0, min(zoom_for_width, zoom_for_height)), effective_max_zoom)

    crop_width = base_width / zoom
    crop_height = base_height / zoom

    x = cx - crop_width / 2
    y = cy - crop_height / 2
    x = max(0.0, min(x, frame_width - crop_width))
    y = max(0.0, min(y, frame_height - crop_height))

    contained = True
    if subject_bbox is not None:
        contained = (
            x <= subject_bbox.x
            and subject_bbox.x + subject_bbox.width <= x + crop_width
            and y <= subject_bbox.y
            and subject_bbox.y + subject_bbox.height <= y + crop_height
        )

    return CropWindow(x=x, y=y, width=crop_width, height=crop_height, zoom=zoom, subject_fully_contained=contained)


def smooth_crop_path(
    windows: Sequence[CropWindow],
    max_center_shift_ratio: float = 0.06,
    max_zoom_delta_per_step: float = 0.08,
) -> List[CropWindow]:
    """크롭 좌표 급이동을 방지한다 ("자연스러운 줌"/부드러운 추적).

    연속된 프레임 사이 크롭 중심 이동을 크롭 너비의 max_center_shift_ratio 이내로,
    줌 변화를 max_zoom_delta_per_step 이내로 제한한다.
    """
    if not windows:
        return []

    smoothed: List[CropWindow] = [windows[0]]
    for target in windows[1:]:
        prev = smoothed[-1]
        prev_cx, prev_cy = prev.center
        target_cx, target_cy = target.center

        max_shift = prev.width * max_center_shift_ratio
        dx = _clamp(target_cx - prev_cx, -max_shift, max_shift)
        dy = _clamp(target_cy - prev_cy, -max_shift, max_shift)

        zoom = prev.zoom + _clamp(target.zoom - prev.zoom, -max_zoom_delta_per_step, max_zoom_delta_per_step)
        width = target.width  # 목표 프레임의 base 치수를 따르되 줌만 스무딩된 값을 반영
        height = target.height
        if target.zoom > 0:
            width = target.width * (target.zoom / zoom) if zoom > 0 else target.width
            height = target.height * (target.zoom / zoom) if zoom > 0 else target.height

        new_cx = prev_cx + dx
        new_cy = prev_cy + dy
        new_x = new_cx - width / 2
        new_y = new_cy - height / 2

        smoothed.append(
            replace(
                target,
                x=new_x,
                y=new_y,
                width=width,
                height=height,
                zoom=zoom,
            )
        )
    return smoothed


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def align_before_after_crop(before: CropWindow, after: CropWindow) -> Tuple[CropWindow, CropWindow]:
    """전후 비교 장면은 같은 구도를 우선한다 - after를 before와 동일한 크롭으로 맞춘다."""
    return before, before


@dataclass(frozen=True)
class ReframePlan:
    frame_times: List[float]
    windows: List[CropWindow]
    approved: bool = False


def apply_approved_reframe(plan: ReframePlan) -> Optional[ReframePlan]:
    """모든 화면 보정은 사용자 검토 후 적용한다 - approved=True인 계획만 실제로 통과시킨다."""
    if not plan.approved:
        return None
    return plan


def _crop_filter(crop: CropWindow, target_width: int, target_height: int) -> str:
    x, y = int(round(crop.x)), int(round(crop.y))
    w, h = int(round(crop.width)), int(round(crop.height))
    return f"crop={w}:{h}:{x}:{y},scale={target_width}:{target_height}"


def render_static_crop(
    video_path: str,
    crop: CropWindow,
    output_path: str,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """승인된 CropWindow 하나를 영상 전체에 실제로 적용해 9:16 mp4를 렌더링한다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        _crop_filter(crop, target_width, target_height),
        "-c:a",
        "copy",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def render_crop_preview_image(
    video_path: str,
    crop: CropWindow,
    output_path: str,
    sample_time: float,
    preview_width: int = 270,
    preview_height: int = 480,
) -> str:
    """사용자가 승인 전에 미리 볼 수 있는 크롭 결과 이미지 한 장을 실제로 렌더링한다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss",
        str(max(0.0, sample_time)),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        _crop_filter(crop, preview_width, preview_height),
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
