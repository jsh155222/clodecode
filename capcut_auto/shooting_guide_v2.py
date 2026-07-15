"""MODE 2 촬영 가이드 확장(Phase 4).

기존 capcut_auto/shooting_guide.py(웹앱 MODE 2에 이미 연결된 버전)는 그대로 두고,
이 모듈은 새로 요구된 입력/출력 스키마를 별도 구현으로 추가한다:

- 목표 길이(초) 기반 컷 개수 규칙 (15~30초: 6~12컷, 30~60초: 8~18컷)
- 샷마다 역할(초반 훅/전체 상황/핵심 대상 디테일/실제 과정/핵심 변화/결과), 카메라
  앵글/거리/높이/방향/움직임, 촬영 권장 시간, 자막 안전 영역 힌트, 필수 촬영 여부
- 촬영 체크리스트 + 진행률 추적

중요한 제약: 이 계획에 있는 장면이 실제 업로드 영상에 존재한다고 가정하지 않는다.
이 모듈은 MODE 1(capcut_auto/ai/video_structure.py 등)의 어떤 분석 함수도 호출하거나
그 입력으로 쓰이지 않는다 - MODE 1은 이 계획과 무관하게 업로드된 영상을 처음부터
다시 분석한다. generate_shooting_plan_v2()의 결과는 어디까지나 촬영 참고용 제안이며,
이 사실을 warnings에도 항상 명시한다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .categories import CATEGORY_LABELS, ContentCategory

MODE1_INDEPENDENCE_NOTICE = (
    "이 촬영 계획은 참고용 제안입니다. 실제 업로드한 영상은 MODE 1에서 이 계획과 무관하게 "
    "처음부터 다시 분석됩니다 - 계획에 있는 장면이 영상에 실제로 있다고 가정하지 않습니다."
)


class ShotRole(str, Enum):
    HOOK = "HOOK"  # 초반 훅 장면
    OVERVIEW = "OVERVIEW"  # 전체 상황
    SUBJECT_DETAIL = "SUBJECT_DETAIL"  # 핵심 대상 디테일
    PROCESS = "PROCESS"  # 실제 과정
    CHANGE = "CHANGE"  # 핵심 변화
    RESULT = "RESULT"  # 결과


ROLE_LABELS: Dict[ShotRole, str] = {
    ShotRole.HOOK: "초반 훅 장면",
    ShotRole.OVERVIEW: "전체 상황",
    ShotRole.SUBJECT_DETAIL: "핵심 대상 디테일",
    ShotRole.PROCESS: "실제 과정",
    ShotRole.CHANGE: "핵심 변화",
    ShotRole.RESULT: "결과",
}

_ROLE_DESCRIPTIONS: Dict[ShotRole, str] = {
    ShotRole.HOOK: "{subject}의 가장 흥미로운 순간을 3초 안에 보여주며 시작하세요.",
    ShotRole.OVERVIEW: "{subject}와 관련된 전체 상황이나 공간을 한눈에 보여주세요.",
    ShotRole.SUBJECT_DETAIL: "{subject}에서 핵심이 되는 부분을 가까이서 자세히 보여주세요.",
    ShotRole.PROCESS: "{subject}를 실제로 진행하는 과정을 있는 그대로 촬영하세요.",
    ShotRole.CHANGE: "{subject}에서 일어난 핵심 변화를 전/후 같은 구도로 비교해서 보여주세요.",
    ShotRole.RESULT: "{subject}의 최종 결과를 보여주며 마무리하세요.",
}

_ROLE_MANDATORY: Dict[ShotRole, bool] = {
    ShotRole.HOOK: True,
    ShotRole.OVERVIEW: False,
    ShotRole.SUBJECT_DETAIL: False,
    ShotRole.PROCESS: False,
    ShotRole.CHANGE: True,
    ShotRole.RESULT: True,
}

_ROLE_SAFE_ZONE_HINT: Dict[ShotRole, str] = {
    ShotRole.HOOK: "화면 하단 25%는 자막 영역으로 비워두세요.",
    ShotRole.OVERVIEW: "하단 자막 영역을 기본으로 비우고, 손이나 도구가 하단을 크게 가리지 않게 하세요.",
    ShotRole.SUBJECT_DETAIL: "피사체를 화면 중앙에 두고 하단 자막 영역은 비워두세요.",
    ShotRole.PROCESS: "손이 화면 하단을 자주 차지할 수 있으니 자막을 상단에 둘 가능성도 고려하세요.",
    ShotRole.CHANGE: "전/후 비교 구도를 유지하면서 하단 자막 영역은 비워두세요.",
    ShotRole.RESULT: "결과물이 화면 중앙~상단에 오도록 구도를 잡아 하단 자막 영역을 확보하세요.",
}

# 역할별 카메라 5요소(앵글/거리/높이/방향/움직임) 템플릿
_ROLE_CAMERA: Dict[ShotRole, "CameraSpec"] = {}  # 아래에서 CameraSpec 정의 후 채움

# 역할별 리테이크 배수 - "촬영 권장 시간"은 최종 컷 길이가 아니라 편집에서 고를 수 있게
# 여유 있게 촬영해둘 시간이므로, 최종 컷 길이보다 길게 잡는다.
_ROLE_RETAKE_MULTIPLIER: Dict[ShotRole, int] = {
    ShotRole.HOOK: 4,
    ShotRole.OVERVIEW: 3,
    ShotRole.SUBJECT_DETAIL: 3,
    ShotRole.PROCESS: 5,
    ShotRole.CHANGE: 3,
    ShotRole.RESULT: 4,
}

# 목표 길이(초) -> (최소 컷 수, 최대 컷 수). 스펙에 명시된 두 구간만 정확한 값이고,
# 그 밖의 길이는 가장 가까운 구간의 밀도를 그대로 연장한 추정치임을 문서화한다.
_DURATION_CUT_BANDS: List[Tuple[float, float, int, int]] = [
    (15.0, 30.0, 6, 12),
    (30.0, 60.0, 8, 18),
]


def cut_count_range_for_duration(duration_seconds: float) -> Tuple[int, int]:
    """목표 길이(초)에 맞는 (최소, 최대) 컷 개수를 반환한다.

    15~30초/30~60초는 스펙에 명시된 정확한 값이다. 그 범위를 벗어나면 가장 가까운
    구간의 초당 컷 밀도를 그대로 연장한 추정치를 반환한다(스펙에 없는 값이므로
    fabricated exact rule이 아니라 추정임을 함수 문서에 명시).
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds는 0보다 커야 합니다.")
    for lo, hi, min_cuts, max_cuts in _DURATION_CUT_BANDS:
        if lo <= duration_seconds <= hi:
            return (min_cuts, max_cuts)
    if duration_seconds < _DURATION_CUT_BANDS[0][0]:
        lo, _hi, min_cuts, max_cuts = _DURATION_CUT_BANDS[0]
        ratio = duration_seconds / lo
        return (max(2, round(min_cuts * ratio)), max(3, round(max_cuts * ratio)))
    _lo, hi, min_cuts, max_cuts = _DURATION_CUT_BANDS[-1]
    density_min = min_cuts / hi
    density_max = max_cuts / hi
    return (max(min_cuts, round(density_min * duration_seconds)), max(max_cuts, round(density_max * duration_seconds)))


def _role_sequence(shot_count: int) -> List[ShotRole]:
    """샷 개수에 맞는 역할 순서를 만든다. 항상 정확히 shot_count개를 반환한다."""
    if shot_count <= 0:
        raise ValueError("shot_count는 0보다 커야 합니다.")
    if shot_count == 1:
        return [ShotRole.RESULT]
    if shot_count == 2:
        return [ShotRole.HOOK, ShotRole.RESULT]
    if shot_count == 3:
        return [ShotRole.HOOK, ShotRole.PROCESS, ShotRole.RESULT]

    core = [ShotRole.HOOK, ShotRole.OVERVIEW, ShotRole.CHANGE, ShotRole.RESULT]
    remaining = shot_count - len(core)
    toggle = [ShotRole.PROCESS, ShotRole.SUBJECT_DETAIL]
    fillers = [toggle[i % 2] for i in range(remaining)]
    return [ShotRole.HOOK, ShotRole.OVERVIEW] + fillers + [ShotRole.CHANGE, ShotRole.RESULT]


@dataclass(frozen=True)
class CameraSpec:
    angle: str
    distance: str
    height: str
    direction: str
    movement: str


_ROLE_CAMERA.update(
    {
        ShotRole.HOOK: CameraSpec(angle="정면", distance="클로즈업", height="아이레벨", direction="피사체 정면", movement="고정"),
        ShotRole.OVERVIEW: CameraSpec(angle="사선", distance="와이드", height="아이레벨~하이앵글", direction="전체 공간", movement="고정 또는 느린 패닝"),
        ShotRole.SUBJECT_DETAIL: CameraSpec(angle="정면 또는 탑뷰", distance="클로즈업", height="피사체 높이에 맞춤", direction="피사체 정면", movement="고정"),
        ShotRole.PROCESS: CameraSpec(angle="사선", distance="미디엄~클로즈업", height="작업 높이", direction="작업자 시점", movement="고정 또는 느린 트래킹"),
        ShotRole.CHANGE: CameraSpec(angle="정면", distance="미디엄", height="아이레벨", direction="비교 대상 정면", movement="고정(전/후 동일 구도)"),
        ShotRole.RESULT: CameraSpec(angle="정면 또는 45도", distance="와이드~미디엄", height="아이레벨", direction="결과물 정면", movement="고정 또는 천천히 줌인"),
    }
)


@dataclass
class ShootingGuideInputV2:
    """webapp/spec의 `interface ShootingGuideInput`과 대응하는 파이썬 표현."""

    topic: str
    category: ContentCategory
    subject: str
    target_duration_seconds: int
    location: Optional[str] = None
    equipment: Optional[List[str]] = None
    show_face: Optional[bool] = None
    available_shooting_minutes: Optional[int] = None
    must_show_steps: Optional[List[str]] = None
    additional_notes: Optional[str] = None


@dataclass(frozen=True)
class ShotSpecV2:
    order: int
    role: str
    role_label: str
    description: str
    camera: CameraSpec
    recommended_shooting_seconds: int
    subtitle_safe_zone_hint: str
    mandatory: bool


@dataclass(frozen=True)
class ShootingChecklistItem:
    order: int
    role_label: str
    description: str
    mandatory: bool
    done: bool = False


@dataclass(frozen=True)
class ShootingPlanV2:
    topic: str
    category: ContentCategory
    category_label: str
    subject: str
    target_duration_seconds: int
    cut_count_range: Tuple[int, int]
    shot_count: int
    shots: List[ShotSpecV2]
    equipment: List[str]
    total_recommended_shooting_seconds: int
    warnings: List[str]


def _shot_from_role(order: int, role: ShotRole, subject: str, base_seconds: int, show_face: Optional[bool]) -> ShotSpecV2:
    description = _ROLE_DESCRIPTIONS[role].format(subject=subject)
    if show_face is False and role in (ShotRole.HOOK, ShotRole.RESULT):
        description += " 얼굴 대신 손이나 화면을 보여주고 음성 내레이션을 활용해도 좋아요."
    seconds = max(1, base_seconds * _ROLE_RETAKE_MULTIPLIER[role])
    return ShotSpecV2(
        order=order,
        role=role.value,
        role_label=ROLE_LABELS[role],
        description=description,
        camera=_ROLE_CAMERA[role],
        recommended_shooting_seconds=seconds,
        subtitle_safe_zone_hint=_ROLE_SAFE_ZONE_HINT[role],
        mandatory=_ROLE_MANDATORY[role],
    )


def generate_shooting_plan_v2(guide_input: ShootingGuideInputV2) -> ShootingPlanV2:
    """새 ShootingGuideInput 스키마로 촬영 계획을 생성한다."""
    topic = guide_input.topic.strip()
    subject = guide_input.subject.strip()
    if not topic:
        raise ValueError("topic은 비어 있을 수 없습니다.")
    if not subject:
        raise ValueError("subject는 비어 있을 수 없습니다.")

    cut_range = cut_count_range_for_duration(guide_input.target_duration_seconds)
    shot_count = round((cut_range[0] + cut_range[1]) / 2)

    base_seconds = max(1, guide_input.target_duration_seconds // shot_count)
    sequence = _role_sequence(shot_count)
    shots = [
        _shot_from_role(i + 1, role, subject, base_seconds, guide_input.show_face)
        for i, role in enumerate(sequence)
    ]

    warnings: List[str] = []
    must_show_steps = [s.strip() for s in (guide_input.must_show_steps or []) if s.strip()]
    if must_show_steps:
        avg_seconds = round(sum(s.recommended_shooting_seconds for s in shots) / len(shots)) if shots else base_seconds
        insert_at = len(shots) - 1 if len(shots) > 1 else len(shots)
        forced_shots = [
            ShotSpecV2(
                order=0,
                role=ShotRole.SUBJECT_DETAIL.value,
                role_label="꼭 담아야 할 장면",
                description=step,
                camera=_ROLE_CAMERA[ShotRole.SUBJECT_DETAIL],
                recommended_shooting_seconds=avg_seconds,
                subtitle_safe_zone_hint=_ROLE_SAFE_ZONE_HINT[ShotRole.SUBJECT_DETAIL],
                mandatory=True,
            )
            for step in must_show_steps
        ]
        shots = shots[:insert_at] + forced_shots + shots[insert_at:]
        shots = [replace(s, order=i + 1) for i, s in enumerate(shots)]

        if len(shots) > cut_range[1]:
            warnings.append(
                f"필수 촬영 장면이 많아 권장 컷 수 범위({cut_range[0]}~{cut_range[1]}개)를 넘었어요. "
                "편집 단계에서 일부를 합치거나 줄여야 할 수 있어요."
            )

    total_seconds = sum(s.recommended_shooting_seconds for s in shots)
    if guide_input.available_shooting_minutes is not None:
        available_seconds = guide_input.available_shooting_minutes * 60
        if available_seconds < total_seconds:
            warnings.append(
                f"촬영 가능 시간({guide_input.available_shooting_minutes}분)이 권장 촬영 시간"
                f"(약 {round(total_seconds / 60)}분)보다 짧아요. 일부 장면을 줄이거나 시간을 늘려주세요."
            )

    warnings.append(MODE1_INDEPENDENCE_NOTICE)

    return ShootingPlanV2(
        topic=topic,
        category=guide_input.category,
        category_label=CATEGORY_LABELS[guide_input.category],
        subject=subject,
        target_duration_seconds=guide_input.target_duration_seconds,
        cut_count_range=cut_range,
        shot_count=len(shots),
        shots=[replace(s, order=i + 1) for i, s in enumerate(shots)],
        equipment=list(guide_input.equipment or []),
        total_recommended_shooting_seconds=total_seconds,
        warnings=warnings,
    )


def build_shooting_checklist(plan: ShootingPlanV2) -> List[ShootingChecklistItem]:
    return [
        ShootingChecklistItem(
            order=shot.order,
            role_label=shot.role_label,
            description=shot.description,
            mandatory=shot.mandatory,
            done=False,
        )
        for shot in plan.shots
    ]


def mark_checklist_item_done(
    checklist: Sequence[ShootingChecklistItem], order: int, done: bool = True
) -> List[ShootingChecklistItem]:
    return [replace(item, done=done) if item.order == order else item for item in checklist]


def shooting_progress(checklist: Sequence[ShootingChecklistItem]) -> Dict[str, int]:
    total = len(checklist)
    done = sum(1 for item in checklist if item.done)
    mandatory_total = sum(1 for item in checklist if item.mandatory)
    mandatory_done = sum(1 for item in checklist if item.mandatory and item.done)
    return {
        "total": total,
        "done": done,
        "percent": round(done / total * 100) if total else 0,
        "mandatory_total": mandatory_total,
        "mandatory_done": mandatory_done,
        "mandatory_percent": round(mandatory_done / mandatory_total * 100) if mandatory_total else 0,
    }
