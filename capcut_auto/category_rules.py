"""카테고리별 규칙(CategoryRuleSet)을 category-rules/*.json에서 읽어와
공통 편집 엔진(capcut_auto/ai/*)에 전달할 수 있는 형태로 제공한다.

카테고리마다 별도의 앱/코드 분기를 두지 않고, 이 로더가 읽어온 데이터만 엔진에
넘겨서 동작을 바꾼다 - 새 카테고리를 추가하거나 규칙을 조정할 때 파이썬 코드를
건드릴 필요 없이 category-rules/ 아래 JSON 파일만 고치면 된다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .categories import ContentCategory

Pacing = str  # "SLOW" | "MEDIUM" | "FAST"
SubtitleDensity = str  # "LOW" | "MEDIUM" | "HIGH"

_VALID_PACING = {"SLOW", "MEDIUM", "FAST"}
_VALID_DENSITY = {"LOW", "MEDIUM", "HIGH"}

_REQUIRED_KEYS = (
    "category",
    "protectedMoments",
    "removableMoments",
    "preferredPacing",
    "subtitleDensity",
    "preserveNaturalAudio",
    "preferredShotTypes",
    "discouragedSoundEffects",
    "safetyChecks",
    "shootingGuideRules",
)


def _default_rules_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "category-rules"


@dataclass(frozen=True)
class CategoryRuleSet:
    """webapp/spec의 `interface CategoryRuleSet`과 1:1로 대응하는 파이썬 표현."""

    category: ContentCategory
    protected_moments: List[str] = field(default_factory=list)
    removable_moments: List[str] = field(default_factory=list)
    preferred_pacing: Pacing = "MEDIUM"
    subtitle_density: SubtitleDensity = "MEDIUM"
    preserve_natural_audio: bool = False
    preferred_shot_types: List[str] = field(default_factory=list)
    discouraged_sound_effects: List[str] = field(default_factory=list)
    safety_checks: List[str] = field(default_factory=list)
    shooting_guide_rules: List[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """AI 모듈 입력 등에 그대로 실어보낼 수 있는 camelCase 딕셔너리로 변환."""
        return {
            "category": self.category.value,
            "protectedMoments": list(self.protected_moments),
            "removableMoments": list(self.removable_moments),
            "preferredPacing": self.preferred_pacing,
            "subtitleDensity": self.subtitle_density,
            "preserveNaturalAudio": self.preserve_natural_audio,
            "preferredShotTypes": list(self.preferred_shot_types),
            "discouragedSoundEffects": list(self.discouraged_sound_effects),
            "safetyChecks": list(self.safety_checks),
            "shootingGuideRules": list(self.shooting_guide_rules),
        }


def _rule_file_path(category: ContentCategory, rules_dir: Path) -> Path:
    return rules_dir / f"{category.value.lower()}.json"


def _parse_rule_set(data: dict, source: str) -> CategoryRuleSet:
    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"{source}: 필수 필드 누락 - {missing}")

    pacing = data["preferredPacing"]
    if pacing not in _VALID_PACING:
        raise ValueError(f"{source}: preferredPacing 값이 올바르지 않음 - {pacing!r}")

    density = data["subtitleDensity"]
    if density not in _VALID_DENSITY:
        raise ValueError(f"{source}: subtitleDensity 값이 올바르지 않음 - {density!r}")

    try:
        category = ContentCategory(data["category"])
    except ValueError as exc:
        raise ValueError(f"{source}: 알 수 없는 category - {data['category']!r}") from exc

    return CategoryRuleSet(
        category=category,
        protected_moments=list(data["protectedMoments"]),
        removable_moments=list(data["removableMoments"]),
        preferred_pacing=pacing,
        subtitle_density=density,
        preserve_natural_audio=bool(data["preserveNaturalAudio"]),
        preferred_shot_types=list(data["preferredShotTypes"]),
        discouraged_sound_effects=list(data["discouragedSoundEffects"]),
        safety_checks=list(data["safetyChecks"]),
        shooting_guide_rules=list(data["shootingGuideRules"]),
    )


def load_category_rule_set(category: ContentCategory, rules_dir: Path = None) -> CategoryRuleSet:
    """category-rules/<카테고리>.json을 읽어 CategoryRuleSet으로 반환한다.

    파일이 없거나 형식이 잘못되면 조용히 기본값으로 넘어가지 않고 예외를 던진다 -
    이 데이터는 안전 규칙/보호 구간처럼 조용히 틀리면 안 되는 핵심 라우팅 정보이기
    때문이다.
    """
    directory = rules_dir or _default_rules_dir()
    path = _rule_file_path(category, directory)
    if not path.exists():
        raise FileNotFoundError(f"카테고리 규칙 파일을 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _parse_rule_set(data, source=str(path))


def load_common_rules(rules_dir: Path = None) -> List[str]:
    """모든 카테고리에 공통으로 적용되는 규칙(category-rules/common.json)을 읽는다."""
    directory = rules_dir or _default_rules_dir()
    path = directory / "common.json"
    if not path.exists():
        raise FileNotFoundError(f"공통 규칙 파일을 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "commonRules" not in data:
        raise ValueError(f"{path}: commonRules 필드 누락")

    return list(data["commonRules"])


def load_all_category_rule_sets(rules_dir: Path = None) -> Dict[ContentCategory, CategoryRuleSet]:
    """모든 카테고리의 규칙을 한 번에 로드한다 (검증/테스트용)."""
    return {category: load_category_rule_set(category, rules_dir) for category in ContentCategory}


def sfx_allowed(rule_set: CategoryRuleSet) -> bool:
    """이 카테고리에서 효과음(SFX)을 덧입혀도 되는지 판단한다.

    preserveNaturalAudio가 true인 카테고리(음식/청소/여행/캠핑/육아)는 실제 소리를
    보호해야 하므로 인공 효과음을 제한한다.
    """
    return not rule_set.preserve_natural_audio
