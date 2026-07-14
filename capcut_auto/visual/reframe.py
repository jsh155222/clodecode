"""9:16 자동 리프레이밍 + 자연스러운 줌.

순수 기하 계산만 한다 (실제 렌더링은 export 단계에서 pycapcut의 키프레임으로 적용).
모든 화면 보정은 사용자 검토 후 적용한다 - apply_approved_reframe()이 그 게이트 역할을 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

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
