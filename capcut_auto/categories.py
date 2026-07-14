"""콘텐츠 카테고리 정의와, 카테고리별 자동 편집 규칙.

프론트엔드(webapp/src/types.ts)의 ContentCategory와 값이 1:1로 대응해야 한다.
카테고리 규칙은 CutlistConfig를 만들어내는 팩토리 역할만 하며, cutlist.build_cutlist()
자체의 시그니처는 건드리지 않는다 (기존 분석 보고서 7번 항목의 설계를 그대로 따름).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from .cutlist import CutlistConfig


class ContentCategory(str, Enum):
    LIVING = "LIVING"
    CLEANING = "CLEANING"
    FOOD = "FOOD"
    PARENTING = "PARENTING"
    BEAUTY = "BEAUTY"
    TRAVEL = "TRAVEL"
    CAMPING = "CAMPING"


CATEGORY_LABELS: Dict[ContentCategory, str] = {
    ContentCategory.LIVING: "살림",
    ContentCategory.CLEANING: "청소",
    ContentCategory.FOOD: "음식",
    ContentCategory.PARENTING: "육아",
    ContentCategory.BEAUTY: "뷰티",
    ContentCategory.TRAVEL: "여행",
    ContentCategory.CAMPING: "캠핑",
}


@dataclass
class CategoryRule:
    category: ContentCategory
    cutlist_config: CutlistConfig
    # hooks.py가 훅 문구 템플릿을 고를 때 참고하는 어휘/톤 키워드
    hook_keywords: List[str] = field(default_factory=list)
    # audio_mix.py가 기본으로 추천할 배경음 무드
    default_bgm_mood: str = "neutral"


# 카테고리별로 컷 민감도를 다르게 둔다. 예: 여행/캠핑은 자연광/현장음이 있는 롱테이크가
# 많아 무음 판정을 더 보수적으로(min_silence를 올리는 효과와 유사하게 edge padding을 늘림),
# 청소/살림처럼 설명이 빠르게 이어지는 콘텐츠는 필러워드 컷을 더 적극적으로 적용한다.
CATEGORY_RULES: Dict[ContentCategory, CategoryRule] = {
    ContentCategory.LIVING: CategoryRule(
        category=ContentCategory.LIVING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.12, filler_edge_expand=0.05, min_keep_duration=0.12, min_cut_duration=0.15
        ),
        hook_keywords=["살림 꿀팁", "이렇게 하면 편해요", "당장 따라해보세요"],
        default_bgm_mood="cozy",
    ),
    ContentCategory.CLEANING: CategoryRule(
        category=ContentCategory.CLEANING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.10, filler_edge_expand=0.06, min_keep_duration=0.10, min_cut_duration=0.12
        ),
        hook_keywords=["청소 전후 비교", "이 방법 실화입니다", "5분만에 끝내는"],
        default_bgm_mood="upbeat",
    ),
    ContentCategory.FOOD: CategoryRule(
        category=ContentCategory.FOOD,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.16, filler_edge_expand=0.05, min_keep_duration=0.14, min_cut_duration=0.15
        ),
        hook_keywords=["이 조합 미쳤어요", "레시피 저장 필수", "집에서 이렇게 쉽게"],
        default_bgm_mood="warm",
    ),
    ContentCategory.PARENTING: CategoryRule(
        category=ContentCategory.PARENTING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.18, filler_edge_expand=0.04, min_keep_duration=0.16, min_cut_duration=0.15
        ),
        hook_keywords=["육아 선배들이 알려주는", "이거 몰랐으면 손해", "우리 아이가 달라졌어요"],
        default_bgm_mood="gentle",
    ),
    ContentCategory.BEAUTY: CategoryRule(
        category=ContentCategory.BEAUTY,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.10, filler_edge_expand=0.05, min_keep_duration=0.10, min_cut_duration=0.12
        ),
        hook_keywords=["이 제품 실화냐", "발색 미쳤다", "1분 만에 되는"],
        default_bgm_mood="upbeat",
    ),
    ContentCategory.TRAVEL: CategoryRule(
        category=ContentCategory.TRAVEL,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.20, filler_edge_expand=0.05, min_keep_duration=0.18, min_cut_duration=0.18
        ),
        hook_keywords=["숨겨진 여행지", "여기 안 가면 후회함", "이번 여행 코스 정리"],
        default_bgm_mood="cinematic",
    ),
    ContentCategory.CAMPING: CategoryRule(
        category=ContentCategory.CAMPING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.20, filler_edge_expand=0.05, min_keep_duration=0.18, min_cut_duration=0.18
        ),
        hook_keywords=["이 장비 하나로 끝", "캠핑 초보 필수 코스", "불멍 각 나오는"],
        default_bgm_mood="cinematic",
    ),
}


def get_rule(category: ContentCategory) -> CategoryRule:
    return CATEGORY_RULES[category]
