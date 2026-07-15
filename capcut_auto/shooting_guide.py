"""MODE 2(AI 촬영 가이드): 카테고리별 앵글/촬영 순서 생성기.

주의: hooks.py와 마찬가지로 이것은 LLM이 아니라 규칙/템플릿 기반 휴리스틱이다.
숏폼 콘텐츠 제작에서 흔히 쓰이는 앵글 구성을 카테고리별로 미리 정의해두고,
사용자 입력(주제/제품/목표 길이 등)으로 채워 넣어 촬영 순서를 만든다.
LLM API 키 인프라가 생기면 이 모듈의 generate_shooting_plan() 시그니처만
유지한 채 내부 구현을 교체하면 된다.

MODE 1(자동 편집)과는 입출력이 완전히 다르므로(영상 파일 없음, 텍스트만 입출력)
파이프라인/서버 상태(project_store.Project)를 공유하지 않는 독립된 순수 함수로 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .categories import CATEGORY_LABELS, ContentCategory


class ShotAngle(str, Enum):
    WIDE = "WIDE"
    CLOSE_UP = "CLOSE_UP"
    TOP_VIEW = "TOP_VIEW"
    HANDS = "HANDS"
    FACE_TALK = "FACE_TALK"
    BEFORE_AFTER = "BEFORE_AFTER"
    DETAIL = "DETAIL"
    REACTION = "REACTION"
    TIMELAPSE = "TIMELAPSE"


ANGLE_LABELS = {
    ShotAngle.WIDE: "와이드샷",
    ShotAngle.CLOSE_UP: "클로즈업",
    ShotAngle.TOP_VIEW: "탑뷰",
    ShotAngle.HANDS: "손 클로즈업",
    ShotAngle.FACE_TALK: "정면 토크",
    ShotAngle.BEFORE_AFTER: "비포/애프터",
    ShotAngle.DETAIL: "디테일샷",
    ShotAngle.REACTION: "리액션샷",
    ShotAngle.TIMELAPSE: "타임랩스",
}


@dataclass(frozen=True)
class _ShotTemplate:
    angle: ShotAngle
    title: str
    description: str  # {product}/{topic}/{location} 플레이스홀더 사용 가능
    tip: Optional[str] = None


@dataclass(frozen=True)
class ShotPlan:
    order: int
    angle: str
    angle_label: str
    title: str
    description: str
    estimated_seconds: int
    tip: Optional[str] = None


@dataclass(frozen=True)
class ShootingPlan:
    topic: str
    category: ContentCategory
    category_label: str
    target_duration_label: str
    shots: List[ShotPlan]
    total_estimated_seconds: int
    equipment_tips: List[str]
    warnings: List[str]


@dataclass
class ShootingGuideInput:
    topic: str
    category: ContentCategory
    product_or_situation: str
    target_duration: str  # TARGET_DURATION_CONFIG의 키 중 하나
    location: str = ""
    equipment: str = ""
    face_on_camera: bool = False
    must_show_scenes: str = ""
    available_time: str = ""
    notes: str = ""


# 목표 영상 길이 -> (샷 개수, 전체 예상 촬영 분량 초)
TARGET_DURATION_CONFIG: dict = {
    "UNDER_1MIN": (4, 45),
    "1_TO_3MIN": (6, 120),
    "3_TO_5MIN": (8, 240),
    "OVER_5MIN": (10, 360),
}

_CATEGORY_TEMPLATES: dict = {
    ContentCategory.FOOD: [
        _ShotTemplate(ShotAngle.WIDE, "완성 요리 티저", "{product} 완성된 모습을 먼저 와이드샷으로 보여주며 시작하세요.", "완성 샷을 맨 처음에 보여주면 끝까지 볼 확률이 올라가요."),
        _ShotTemplate(ShotAngle.TOP_VIEW, "재료 준비", "{product}에 들어갈 재료들을 탑뷰로 가지런히 배치해 보여주세요."),
        _ShotTemplate(ShotAngle.HANDS, "손질/준비 과정", "재료를 손질하는 과정을 손 클로즈업으로 촬영하세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "조리 과정 1", "{product} 조리 중 가장 중요한 단계(불 조절, 재료 넣는 타이밍 등)를 클로즈업으로 담으세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "조리 과정 2", "소스가 끓거나 재료가 익어가는 디테일을 가까이서 담아주세요."),
        _ShotTemplate(ShotAngle.TOP_VIEW, "플레이팅", "완성된 {product}를 탑뷰 또는 45도 각도로 플레이팅하세요."),
        _ShotTemplate(ShotAngle.REACTION, "시식 리액션", "직접 먹는 모습과 표정을 정면에서 담아주세요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "한줄평", "{product}에 대한 솔직한 한줄평을 정면 토크로 마무리하세요."),
    ],
    ContentCategory.CLEANING: [
        _ShotTemplate(ShotAngle.WIDE, "청소 전(Before)", "{location} 전체를 와이드샷으로 담아 상태를 보여주세요.", "이 구도를 기억해뒀다가 청소 후에 똑같이 찍으세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "문제 구간 클로즈업", "가장 지저분하거나 신경 쓰이는 부분을 클로즈업으로 강조하세요."),
        _ShotTemplate(ShotAngle.HANDS, "청소 도구/제품 소개", "{product} 등 사용할 도구를 손에 들고 소개하세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "청소 과정", "실제로 닦고 정리하는 과정을 여러 각도에서 촬영하세요."),
        _ShotTemplate(ShotAngle.TIMELAPSE, "정리 타임랩스", "시간이 오래 걸리는 구간은 타임랩스로 빠르게 보여주면 지루하지 않아요."),
        _ShotTemplate(ShotAngle.BEFORE_AFTER, "청소 후(After) 비교", "1번과 똑같은 구도로 청소 후 모습을 촬영해 비교 효과를 극대화하세요."),
        _ShotTemplate(ShotAngle.REACTION, "완료 리액션", "달라진 공간을 보는 리액션을 담아주세요."),
    ],
    ContentCategory.LIVING: [
        _ShotTemplate(ShotAngle.WIDE, "문제 상황 소개", "{product} 관련해서 불편했던 상황을 와이드샷으로 보여주며 시작하세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "기존 상태 클로즈업", "정리 전 어수선한 부분을 클로즈업으로 담으세요."),
        _ShotTemplate(ShotAngle.HANDS, "정리 도구/아이템 소개", "사용할 정리 아이템을 손으로 들고 보여주세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "정리 과정 단계별", "정리하는 과정을 단계별로 나눠서 촬영하세요 (한 단계당 3~5초 컷).", "너무 길게 한 컷으로 찍지 말고 단계마다 끊어서 촬영하면 편집이 쉬워요."),
        _ShotTemplate(ShotAngle.BEFORE_AFTER, "정리 후 비교", "정리 전과 동일한 구도로 촬영해 극적인 비교를 보여주세요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "꿀팁 설명", "이 방법의 핵심 팁을 정면에서 짧게 설명하세요."),
    ],
    ContentCategory.PARENTING: [
        _ShotTemplate(ShotAngle.WIDE, "상황 소개", "{product} 관련 상황을 와이드샷으로 자연스럽게 시작하세요."),
        _ShotTemplate(ShotAngle.REACTION, "아이 반응", "아이의 자연스러운 표정과 반응을 클로즈업으로 담아주세요.", "연출하지 않은 자연스러운 순간이 가장 반응이 좋아요."),
        _ShotTemplate(ShotAngle.HANDS, "활동/도구 클로즈업", "사용하는 육아템이나 활동 도구를 클로즈업으로 담으세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "활동 과정", "아이와 함께하는 과정을 여러 각도에서 자연스럽게 담아주세요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "부모 설명/팁", "이 상황에서 도움이 됐던 팁을 정면에서 설명하세요."),
        _ShotTemplate(ShotAngle.REACTION, "마무리 리액션", "아이와 부모의 편안한 마무리 모습으로 끝내세요."),
    ],
    ContentCategory.BEAUTY: [
        _ShotTemplate(ShotAngle.CLOSE_UP, "비포(Before)", "제품과 사용 전 상태를 클로즈업으로 보여주세요."),
        _ShotTemplate(ShotAngle.HANDS, "제품 소개", "{product}의 텍스처와 패키지를 손 클로즈업으로 소개하세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "사용법 단계별", "바르는/사용하는 과정을 단계별로 클로즈업하세요."),
        _ShotTemplate(ShotAngle.DETAIL, "발색/효과 디테일", "발색이나 변화가 보이는 부분을 최대한 가까이서 촬영하세요."),
        _ShotTemplate(ShotAngle.BEFORE_AFTER, "애프터 비교", "비포와 동일한 각도·조명으로 애프터를 촬영해 비교하세요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "총평", "제품에 대한 솔직한 총평을 정면 토크로 마무리하세요."),
    ],
    ContentCategory.TRAVEL: [
        _ShotTemplate(ShotAngle.WIDE, "도착/이동 샷", "{location} 도착 장면을 와이드샷으로 시작하세요."),
        _ShotTemplate(ShotAngle.WIDE, "장소 전경", "장소 전체 풍경을 천천히 담아주세요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "활동 디테일", "{product} 관련 활동을 가까이서 디테일하게 촬영하세요."),
        _ShotTemplate(ShotAngle.DETAIL, "음식/소품 디테일", "여행 중 만나는 음식이나 소품을 클로즈업으로 담아주세요."),
        _ShotTemplate(ShotAngle.REACTION, "현장 리액션", "직접 경험하는 리액션을 자연스럽게 담아주세요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "소감 마무리", "여행 소감을 정면에서 짧게 말하며 마무리하세요."),
    ],
    ContentCategory.CAMPING: [
        _ShotTemplate(ShotAngle.WIDE, "도착/셋업 샷", "캠핑장 도착과 사이트 전체를 와이드샷으로 시작하세요."),
        _ShotTemplate(ShotAngle.HANDS, "장비 소개", "{product} 등 주요 장비를 손으로 들고 소개하세요."),
        _ShotTemplate(ShotAngle.TIMELAPSE, "텐트/타프 설치", "설치 과정은 타임랩스로 빠르게 보여주면 좋아요."),
        _ShotTemplate(ShotAngle.CLOSE_UP, "불멍/요리 과정", "불을 피우거나 요리하는 과정을 클로즈업으로 담으세요."),
        _ShotTemplate(ShotAngle.WIDE, "밤 풍경", "삼각대를 활용해 밤 캠핑장 풍경을 안정적으로 담아주세요.", "야간 촬영은 삼각대 없이는 흔들리기 쉬워요."),
        _ShotTemplate(ShotAngle.FACE_TALK, "마무리 소감", "하루를 마무리하며 소감을 정면에서 담아주세요."),
    ],
}

_EQUIPMENT_KEYWORD_TIPS = [
    ("삼각대", "삼각대를 고정 샷에 활용하면 흔들림 없이 안정적인 화면을 만들 수 있어요."),
    ("짐벌", "짐벌은 이동하며 촬영하는 워킹샷에 활용하면 부드러운 움직임을 담을 수 있어요."),
    ("조명", "조명은 얼굴 앞 45도 방향에 두면 자연스러운 인물 샷을 얻을 수 있어요."),
    ("마이크", "핀마이크나 샷건마이크를 쓰면 목소리가 훨씬 선명하게 녹음돼요."),
]

_DEFAULT_EQUIPMENT_TIP = "별도 장비가 없어도 괜찮아요. 스마트폰 하나로 창가의 자연광을 활용하면 화질이 좋아져요."

_TIME_PATTERN = re.compile(r"(?:(\d+)\s*시간)?\s*(?:(\d+)\s*분)?")


def _parse_available_minutes(text: str) -> Optional[int]:
    if not text.strip():
        return None
    match = _TIME_PATTERN.search(text)
    if not match or (not match.group(1) and not match.group(2)):
        return None
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    return hours * 60 + minutes


def _parse_must_show_scenes(text: str) -> List[str]:
    if not text.strip():
        return []
    parts = re.split(r"[,\n]", text)
    return [p.strip() for p in parts if p.strip()]


def _select_templates(templates: List[_ShotTemplate], count: int) -> List[_ShotTemplate]:
    n = len(templates)
    if count >= n:
        return list(templates)
    if count <= 1:
        return [templates[0]]
    step = (n - 1) / (count - 1)
    indices: List[int] = []
    for i in range(count):
        idx = round(i * step)
        while idx in indices and idx < n - 1:
            idx += 1
        indices.append(idx)
    ordered = sorted(dict.fromkeys(indices))
    return [templates[i] for i in ordered[:count]]


def _equipment_tips(equipment_text: str) -> List[str]:
    tips = [tip for keyword, tip in _EQUIPMENT_KEYWORD_TIPS if keyword in equipment_text]
    return tips or [_DEFAULT_EQUIPMENT_TIP]


def generate_shooting_plan(guide_input: ShootingGuideInput) -> ShootingPlan:
    """카테고리+주제+제품/상황+목표 길이 등으로 촬영 순서(앵글 리스트)를 생성한다."""
    topic = guide_input.topic.strip()
    if not topic:
        raise ValueError("topic은 비어 있을 수 없습니다.")

    shot_count, total_seconds = TARGET_DURATION_CONFIG.get(
        guide_input.target_duration, TARGET_DURATION_CONFIG["1_TO_3MIN"]
    )

    templates = _CATEGORY_TEMPLATES.get(guide_input.category)
    if not templates:
        raise ValueError(f"알 수 없는 카테고리: {guide_input.category}")

    selected = list(_select_templates(templates, shot_count))

    # 얼굴 출연을 원하지 않으면 정면 토크 샷을 손/화면 + 내레이션 제안으로 대체한다
    if not guide_input.face_on_camera:
        adjusted = []
        for t in selected:
            if t.angle == ShotAngle.FACE_TALK:
                adjusted.append(
                    _ShotTemplate(
                        angle=ShotAngle.HANDS,
                        title=f"{t.title} (내레이션)",
                        description=t.description + " 얼굴 대신 손이나 화면을 보여주고, 음성 내레이션으로 설명해도 좋아요.",
                        tip=t.tip,
                    )
                )
            else:
                adjusted.append(t)
        selected = adjusted

    # 반드시 보여줄 장면을 마지막 샷(보통 마무리) 앞에 끼워 넣는다
    custom_scenes = _parse_must_show_scenes(guide_input.must_show_scenes)
    if custom_scenes:
        outro = selected.pop() if len(selected) > 1 else None
        for scene in custom_scenes:
            selected.append(
                _ShotTemplate(
                    angle=ShotAngle.DETAIL,
                    title="꼭 담아야 할 장면",
                    description=scene,
                    tip="반드시 포함해달라고 표시하신 장면이에요.",
                )
            )
        if outro:
            selected.append(outro)

    location_text = guide_input.location.strip() or "촬영 장소"
    product_text = guide_input.product_or_situation.strip() or topic

    n = len(selected)
    base_seconds = total_seconds // n if n else 0
    remainder = total_seconds - base_seconds * n

    shots: List[ShotPlan] = []
    for i, t in enumerate(selected):
        try:
            description = t.description.format(product=product_text, topic=topic, location=location_text)
        except (KeyError, IndexError):
            description = t.description
        seconds = base_seconds + (remainder if i == n - 1 else 0)
        shots.append(
            ShotPlan(
                order=i + 1,
                angle=t.angle.value,
                angle_label=ANGLE_LABELS[t.angle],
                title=t.title,
                description=description,
                estimated_seconds=max(1, seconds),
                tip=t.tip,
            )
        )

    warnings: List[str] = []
    available_minutes = _parse_available_minutes(guide_input.available_time)
    if available_minutes is not None:
        recommended_minutes = round(total_seconds / 60 * 6)  # 리테이크 포함 경험칙: 결과물 길이의 약 6배
        if available_minutes < recommended_minutes:
            warnings.append(
                f"촬영 가능 시간({available_minutes}분)이 넉넉하지 않을 수 있어요. "
                f"리테이크를 고려하면 약 {recommended_minutes}분 정도를 권장해요."
            )

    return ShootingPlan(
        topic=topic,
        category=guide_input.category,
        category_label=CATEGORY_LABELS[guide_input.category],
        target_duration_label=guide_input.target_duration,
        shots=shots,
        total_estimated_seconds=total_seconds,
        equipment_tips=_equipment_tips(guide_input.equipment),
        warnings=warnings,
    )
