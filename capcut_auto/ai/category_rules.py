"""category-rules/*.json의 카테고리별 규칙(CategoryRuleSet)을 AI 모듈 입력으로 연결한다.

카테고리별로 다른 파이썬 코드 경로를 두지 않는다 - 이 파일은 항상 같은 로직으로
category-rules/에서 규칙을 읽어와 AI 모듈이 받는 파라미터 모양으로 바꿔줄 뿐이다.
"""

from __future__ import annotations

from typing import List, Optional

from ..categories import CATEGORY_LABELS, ContentCategory
from ..category_rules import CategoryRuleSet, load_category_rule_set, load_common_rules

_DENSITY_INSTRUCTIONS = {
    "LOW": "자막 노출을 최소화하고 꼭 필요한 문장만 남긴다",
    "MEDIUM": "일반적인 밀도로 자막을 유지한다",
    "HIGH": "정보 누락 없이 자막 밀도를 높게(빠짐없이) 유지한다",
}


def category_label(category: Optional[ContentCategory]) -> Optional[str]:
    return CATEGORY_LABELS.get(category) if category else None


def get_rule_set(category: Optional[ContentCategory]) -> Optional[CategoryRuleSet]:
    if category is None:
        return None
    return load_category_rule_set(category)


def build_cut_protection_rules(category: Optional[ContentCategory]) -> List[str]:
    """ai/cut_candidates.py에 넘길 카테고리별 보호 장면 설명 목록(protectedMoments)."""
    rule_set = get_rule_set(category)
    return list(rule_set.protected_moments) if rule_set else []


def build_removable_moment_hints(category: Optional[ContentCategory]) -> List[str]:
    """ai/cut_candidates.py에 넘길 카테고리별 삭제 후보 힌트(removableMoments)."""
    rule_set = get_rule_set(category)
    return list(rule_set.removable_moments) if rule_set else []


def build_preferred_pacing(category: Optional[ContentCategory]) -> Optional[str]:
    rule_set = get_rule_set(category)
    return rule_set.preferred_pacing if rule_set else None


def build_preserve_natural_audio(category: Optional[ContentCategory]) -> Optional[bool]:
    rule_set = get_rule_set(category)
    return rule_set.preserve_natural_audio if rule_set else None


def build_subtitle_density_rule(category: Optional[ContentCategory]) -> Optional[str]:
    """ai/subtitle_optimizer.py에 넘길 카테고리별 자막 밀도 가이드(subtitleDensity)."""
    rule_set = get_rule_set(category)
    if rule_set is None:
        return None
    return _DENSITY_INSTRUCTIONS.get(rule_set.subtitle_density, rule_set.subtitle_density)


def build_safety_checks(category: Optional[ContentCategory], *, include_common: bool = True) -> List[str]:
    """ai/cut_candidates.py, ai/hook_ai.py 등에 넘길 안전 규칙 목록.

    include_common=True면 모든 카테고리에 공통으로 적용되는 규칙(category-rules/common.json)도
    함께 포함한다 - 카테고리별 규칙과 공통 규칙이 섞이지 않도록 항상 카테고리 규칙을 먼저,
    공통 규칙을 뒤에 붙인다.
    """
    checks: List[str] = []
    rule_set = get_rule_set(category)
    if rule_set is not None:
        checks.extend(rule_set.safety_checks)
    if include_common:
        checks.extend(load_common_rules())
    return checks


def build_discouraged_sound_effects(category: Optional[ContentCategory]) -> List[str]:
    rule_set = get_rule_set(category)
    return list(rule_set.discouraged_sound_effects) if rule_set else []


def build_preferred_shot_types(category: Optional[ContentCategory]) -> List[str]:
    rule_set = get_rule_set(category)
    return list(rule_set.preferred_shot_types) if rule_set else []


def build_shooting_guide_rules(category: Optional[ContentCategory]) -> List[str]:
    rule_set = get_rule_set(category)
    return list(rule_set.shooting_guide_rules) if rule_set else []
