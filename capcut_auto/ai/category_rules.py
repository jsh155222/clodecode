"""categories.py의 카테고리별 규칙을 AI 모듈 입력(카테고리 보호 규칙/자막 밀도)으로 연결한다."""

from __future__ import annotations

from typing import List, Optional

from ..categories import CATEGORY_LABELS, ContentCategory, get_rule


def category_label(category: Optional[ContentCategory]) -> Optional[str]:
    return CATEGORY_LABELS.get(category) if category else None


def build_cut_protection_rules(category: Optional[ContentCategory]) -> List[str]:
    """ai/cut_candidates.py에 넘길 카테고리별 보호 장면 설명 목록."""
    if category is None:
        return []
    return list(get_rule(category).protected_scene_keywords)


def build_subtitle_density_rule(category: Optional[ContentCategory]) -> Optional[str]:
    """ai/subtitle_optimizer.py에 넘길 카테고리별 자막 밀도 가이드."""
    if category is None:
        return None
    return get_rule(category).subtitle_density_label
