"""자막 안전 영역: 9:16 크롭 화면 안에서 자막이 핵심 피사체를 가리지 않고, 화면 밖으로
잘리지도 않는 영역을 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .reframe import CropWindow
from .subject_detection import BoundingBox, DetectedSubject, is_confident

DEFAULT_BAND_HEIGHT_RATIO = 0.18
DEFAULT_SIDE_MARGIN_RATIO = 0.06
DEFAULT_EDGE_MARGIN_RATIO = 0.04


@dataclass(frozen=True)
class SafeZone:
    x: float
    y: float
    width: float
    height: float
    band: str  # "bottom" | "top"
    overlaps_subject: bool


def bbox_relative_to_crop(bbox: BoundingBox, crop: CropWindow) -> Optional[BoundingBox]:
    """원본 프레임 좌표의 bbox를 크롭 윈도우 기준 상대 좌표로 바꾼다.
    크롭 영역과 전혀 겹치지 않으면 None.
    """
    x0 = max(bbox.x, crop.x)
    y0 = max(bbox.y, crop.y)
    x1 = min(bbox.x + bbox.width, crop.x + crop.width)
    y1 = min(bbox.y + bbox.height, crop.y + crop.height)
    if x1 <= x0 or y1 <= y0:
        return None
    return BoundingBox(x=round(x0 - crop.x), y=round(y0 - crop.y), width=round(x1 - x0), height=round(y1 - y0))


def _bands_overlap(zone_y: float, zone_height: float, bbox: BoundingBox) -> bool:
    return not (bbox.y + bbox.height <= zone_y or bbox.y >= zone_y + zone_height)


def compute_subtitle_safe_zone(
    crop: CropWindow,
    subjects_in_frame: Sequence[DetectedSubject] = (),
    band_height_ratio: float = DEFAULT_BAND_HEIGHT_RATIO,
    side_margin_ratio: float = DEFAULT_SIDE_MARGIN_RATIO,
    edge_margin_ratio: float = DEFAULT_EDGE_MARGIN_RATIO,
) -> SafeZone:
    """기본은 화면 하단 밴드. 신뢰도 있는 피사체(얼굴 등)와 겹치면 상단 밴드로 옮긴다.
    둘 다 겹치면 하단을 유지하되 overlaps_subject=True로 정직하게 표시한다.
    """
    width = crop.width * (1 - side_margin_ratio * 2)
    height = crop.height * band_height_ratio
    x = crop.width * side_margin_ratio

    relative_bboxes = [
        bbox_relative_to_crop(s.bbox, crop)
        for s in subjects_in_frame
        if is_confident(s) and s.bbox is not None
    ]
    relative_bboxes = [b for b in relative_bboxes if b is not None]

    bottom_y = crop.height * (1 - edge_margin_ratio) - height
    top_y = crop.height * edge_margin_ratio

    bottom_conflict = any(_bands_overlap(bottom_y, height, b) for b in relative_bboxes)
    if not bottom_conflict:
        return SafeZone(x=x, y=bottom_y, width=width, height=height, band="bottom", overlaps_subject=False)

    top_conflict = any(_bands_overlap(top_y, height, b) for b in relative_bboxes)
    if not top_conflict:
        return SafeZone(x=x, y=top_y, width=width, height=height, band="top", overlaps_subject=False)

    return SafeZone(x=x, y=bottom_y, width=width, height=height, band="bottom", overlaps_subject=True)
