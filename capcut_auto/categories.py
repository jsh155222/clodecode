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
    # ai/cut_candidates.py가 AI에게 "이 카테고리에서는 이런 장면을 보수적으로 판단하라"고
    # 알려줄 때 쓰는 카테고리별 보호 장면 설명
    protected_scene_keywords: List[str] = field(default_factory=list)
    # ai/subtitle_optimizer.py가 AI에게 전달하는 카테고리별 자막 밀도 가이드
    subtitle_density_label: str = "일반적인 밀도로 작성"


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
        protected_scene_keywords=["정리 완료 결과물", "수납 전후 비교"],
        subtitle_density_label="핵심 팁 위주로 간결하게, 정리 단계는 순서를 놓치지 않게 유지",
    ),
    ContentCategory.CLEANING: CategoryRule(
        category=ContentCategory.CLEANING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.10, filler_edge_expand=0.06, min_keep_duration=0.10, min_cut_duration=0.12
        ),
        hook_keywords=["청소 전후 비교", "이 방법 실화입니다", "5분만에 끝내는"],
        default_bgm_mood="upbeat",
        protected_scene_keywords=["청소 전후 비교", "얼룩/오염 제거 결과"],
        subtitle_density_label="정보 전달 속도가 빠르므로 짧고 간결하게",
    ),
    ContentCategory.FOOD: CategoryRule(
        category=ContentCategory.FOOD,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.16, filler_edge_expand=0.05, min_keep_duration=0.14, min_cut_duration=0.15
        ),
        hook_keywords=["이 조합 미쳤어요", "레시피 저장 필수", "집에서 이렇게 쉽게"],
        default_bgm_mood="warm",
        protected_scene_keywords=["레시피 계량/순서", "시식 반응", "완성 결과물"],
        subtitle_density_label="레시피 순서와 계량은 놓치지 않도록 명확하게 유지",
    ),
    ContentCategory.PARENTING: CategoryRule(
        category=ContentCategory.PARENTING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.18, filler_edge_expand=0.04, min_keep_duration=0.16, min_cut_duration=0.15
        ),
        hook_keywords=["육아 선배들이 알려주는", "이거 몰랐으면 손해", "우리 아이가 달라졌어요"],
        default_bgm_mood="gentle",
        protected_scene_keywords=["아이 안전 관련 장면", "사용 방법/주의사항"],
        subtitle_density_label="천천히 읽을 수 있도록 여유 있는 밀도로 작성",
    ),
    ContentCategory.BEAUTY: CategoryRule(
        category=ContentCategory.BEAUTY,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.10, filler_edge_expand=0.05, min_keep_duration=0.10, min_cut_duration=0.12
        ),
        hook_keywords=["이 제품 실화냐", "발색 미쳤다", "1분 만에 되는"],
        default_bgm_mood="upbeat",
        protected_scene_keywords=["발색/피부 결과 비교", "제품 사용법"],
        subtitle_density_label="제품명과 사용 단계는 명확하게, 나머지는 간결하게",
    ),
    ContentCategory.TRAVEL: CategoryRule(
        category=ContentCategory.TRAVEL,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.20, filler_edge_expand=0.05, min_keep_duration=0.18, min_cut_duration=0.18
        ),
        hook_keywords=["숨겨진 여행지", "여기 안 가면 후회함", "이번 여행 코스 정리"],
        default_bgm_mood="cinematic",
        protected_scene_keywords=["절경/풍경 장면", "감정 반응"],
        subtitle_density_label="풍경/감성 장면은 자막을 최소화하고 여백을 살림",
    ),
    ContentCategory.CAMPING: CategoryRule(
        category=ContentCategory.CAMPING,
        cutlist_config=CutlistConfig(
            silence_edge_padding=0.20, filler_edge_expand=0.05, min_keep_duration=0.18, min_cut_duration=0.18
        ),
        hook_keywords=["이 장비 하나로 끝", "캠핑 초보 필수 코스", "불멍 각 나오는"],
        default_bgm_mood="cinematic",
        protected_scene_keywords=["불멍/자연음 장면", "장비 설치 핵심 절차"],
        subtitle_density_label="자연음/ASMR 구간은 자막을 최소화",
    ),
}


def get_rule(category: ContentCategory) -> CategoryRule:
    return CATEGORY_RULES[category]
