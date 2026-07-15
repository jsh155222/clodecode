"""피사체 감지.

Claude(LLM)가 텍스트만으로 좌표를 만들어내지 않는다. 좌표가 필요한 모든 감지는 실제
컴퓨터 비전 모델(OpenCV Haar Cascade, 오프라인/로컬 실행)로만 만든다.

**정직하게 밝혀두는 한계**: 이 샌드박스에서 실제로 오프라인으로 쓸 수 있는 사전학습
모델은 OpenCV에 번들된 정면/측면 얼굴(Haar Cascade)뿐이다. hand/product/tool/food/
child/beauty_area/travel_location/camping_equipment/work_area/problem_area/text
카테고리는 이 프로젝트에서 학습되거나 다운로드 가능한 전용 검출기가 없으므로, 좌표를
지어내는 대신 **정직하게 "감지 안 됨"(신뢰도 0)으로 보고한다** - "좌표 신뢰도가 낮으면
자동 크롭하지 않는다"는 규칙을 그대로 따른 결과다. face 카테고리만 실제 좌표+신뢰도를
반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import cv2
import numpy as np


class SubjectType(str, Enum):
    FACE = "face"
    HAND = "hand"
    PRODUCT = "product"
    TOOL = "tool"
    FOOD = "food"
    CHILD = "child"
    BEAUTY_AREA = "beauty_area"
    TRAVEL_LOCATION = "travel_location"
    CAMPING_EQUIPMENT = "camping_equipment"
    WORK_AREA = "work_area"
    PROBLEM_AREA = "problem_area"
    TEXT = "text"
    UNKNOWN = "unknown"


# 좌표 없이 앱이 텍스트로만 만들어낼 수 없는 카테고리 (현재 실제 검출기가 없음)
UNSUPPORTED_WITHOUT_REAL_MODEL = {
    SubjectType.HAND,
    SubjectType.PRODUCT,
    SubjectType.TOOL,
    SubjectType.FOOD,
    SubjectType.CHILD,
    SubjectType.BEAUTY_AREA,
    SubjectType.TRAVEL_LOCATION,
    SubjectType.CAMPING_EQUIPMENT,
    SubjectType.WORK_AREA,
    SubjectType.PROBLEM_AREA,
    SubjectType.TEXT,
}

DEFAULT_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> "tuple[float, float]":
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass(frozen=True)
class DetectedSubject:
    subject_type: SubjectType
    bbox: Optional[BoundingBox]
    confidence: float  # 0.0 ~ 1.0. 좌표가 없으면(감지 실패) 항상 0.0


def is_confident(subject: DetectedSubject, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
    return subject.bbox is not None and subject.confidence >= threshold


_FRONTAL_CASCADE = None
_PROFILE_CASCADE = None


def _get_cascade(kind: str) -> cv2.CascadeClassifier:
    global _FRONTAL_CASCADE, _PROFILE_CASCADE
    if kind == "frontal":
        if _FRONTAL_CASCADE is None:
            _FRONTAL_CASCADE = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        return _FRONTAL_CASCADE
    if _PROFILE_CASCADE is None:
        _PROFILE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    return _PROFILE_CASCADE


def _weight_to_confidence(level_weight: float) -> float:
    """Haar cascade의 levelWeight(단계별 누적 신뢰 점수)를 0~1 범위로 근사 변환한다.
    OpenCV는 정규화된 확률을 직접 주지 않으므로, 실무에서 흔히 쓰는 시그모이드 근사를 쓴다.
    """
    return float(1.0 / (1.0 + np.exp(-(level_weight - 5.0) / 3.0)))


def detect_faces(image_path: str) -> List[DetectedSubject]:
    """실제 OpenCV Haar Cascade로 이미지에서 얼굴을 찾는다 (정면 우선, 없으면 측면도 시도)."""
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detections: List[DetectedSubject] = []

    for kind in ("frontal", "profile"):
        cascade = _get_cascade(kind)
        boxes, _reject_levels, level_weights = cascade.detectMultiScale3(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            outputRejectLevels=True,
        )
        for (x, y, w, h), weight in zip(boxes, level_weights):
            detections.append(
                DetectedSubject(
                    subject_type=SubjectType.FACE,
                    bbox=BoundingBox(int(x), int(y), int(w), int(h)),
                    confidence=_weight_to_confidence(float(weight)),
                )
            )
        if detections:
            break  # 정면에서 찾았으면 측면 재시도로 중복 검출을 만들지 않는다

    return detections


def detect_subjects(image_path: str) -> List[DetectedSubject]:
    """이미지 한 장에서 감지 가능한 모든 피사체를 찾는다.

    현재는 face만 실제 좌표를 반환한다. 나머지 카테고리는 실제 검출기가 없으므로
    감지하지 않는다(빈 리스트) - 존재하지 않는 좌표를 만들어내지 않기 위함이다.
    """
    return detect_faces(image_path)


def find_first_appearance_times(
    detections_by_time: "dict[float, List[DetectedSubject]]",
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> "dict[SubjectType, float]":
    """시간순으로 프레임별 감지 결과를 훑어, 각 피사체 유형이 처음으로 신뢰도 있게
    등장한 시각을 찾는다 ("핵심 대상 등장" 트리거에 쓰인다).
    """
    first_seen: "dict[SubjectType, float]" = {}
    for time in sorted(detections_by_time.keys()):
        for subject in detections_by_time[time]:
            if not is_confident(subject, confidence_threshold):
                continue
            if subject.subject_type not in first_seen:
                first_seen[subject.subject_type] = time
    return first_seen
