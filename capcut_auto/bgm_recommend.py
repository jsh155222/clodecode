"""BGM 추천 - 추상적인 메타데이터만 제공한다.

이 모듈은 절대 특정 상업 음원의 곡 제목/아티스트를 만들어내지 않고, 저작권 상태나
"요즘 유행" 여부를 추측하지도 않는다. 실제로 확인할 수 없는 정보이기 때문이다.
대신 사용자가 로열티프리 음원 라이브러리에서 직접 검색할 때 참고할 무드/템포/에너지/
검색 키워드와, 내레이션 위에서 자동으로 볼륨을 낮추는 규칙(덕킹)만 추천한다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import List, Optional, Tuple

from .audio_mix import MOOD_LABELS
from .categories import CATEGORY_LABELS, ContentCategory, get_rule
from .category_rules import CategoryRuleSet

DEFAULT_DUCK_VOLUME_RATIO = 0.35
NATURAL_AUDIO_DUCK_VOLUME_RATIO = 0.2  # 자연음을 우선하는 카테고리는 더 크게 낮춘다


class BgmEnergy(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def label(self) -> str:
        return {BgmEnergy.LOW: "차분함", BgmEnergy.MEDIUM: "보통", BgmEnergy.HIGH: "경쾌함"}[self]


# 무드별 템포 범위(BPM)와 기본 에너지 - audio_mix.MOOD_CHORDS의 무드 키와 대응한다.
_MOOD_TEMPO_RANGE_BPM: dict = {
    "cozy": (70, 95),
    "upbeat": (110, 135),
    "warm": (85, 105),
    "gentle": (60, 85),
    "cinematic": (75, 100),
    "neutral": (80, 110),
}

_MOOD_ENERGY: dict = {
    "cozy": BgmEnergy.LOW,
    "upbeat": BgmEnergy.HIGH,
    "warm": BgmEnergy.MEDIUM,
    "gentle": BgmEnergy.LOW,
    "cinematic": BgmEnergy.MEDIUM,
    "neutral": BgmEnergy.MEDIUM,
}

_ENERGY_ORDER = [BgmEnergy.LOW, BgmEnergy.MEDIUM, BgmEnergy.HIGH]


@dataclass(frozen=True)
class BgmMetadataRecommendation:
    """추상적 메타데이터만 담는다 - 곡 제목/아티스트/저작권 상태/트렌드 여부는 절대 포함하지 않는다."""

    mood: str
    mood_label: str
    tempo_range_bpm: Tuple[int, int]
    energy: BgmEnergy
    has_vocals: bool
    search_keywords: List[str]
    duck_during_voice: bool
    duck_volume_ratio: float


# 실제로 가짜 정보를 만들어내는 걸 막기 위한 하드 가드 - 아래 필드 이름이 데이터클래스에
# 추가되면 안 된다(테스트로 이 목록과 실제 필드셋의 교집합이 비어있는지 검증한다).
FORBIDDEN_FIELD_NAMES = {
    "track_title",
    "title",
    "artist",
    "track_name",
    "source_url",
    "download_url",
    "is_trending",
    "trending",
    "copyright_status",
    "license_status",
    "is_royalty_free",
}


def _cap_energy(energy: BgmEnergy, max_energy: BgmEnergy) -> BgmEnergy:
    if _ENERGY_ORDER.index(energy) > _ENERGY_ORDER.index(max_energy):
        return max_energy
    return energy


def _build_search_keywords(mood_label: str, category_label: Optional[str], energy: BgmEnergy) -> List[str]:
    keywords = [f"{mood_label} 무드 배경음악", f"{mood_label} 인스트루멘탈"]
    if category_label:
        keywords.append(f"{category_label} 브이로그 배경음악")
    keywords.append(f"{energy.label} 템포 bgm")
    return keywords


def recommend_bgm_metadata(
    category: Optional[ContentCategory] = None,
    category_rule_set: Optional[CategoryRuleSet] = None,
) -> BgmMetadataRecommendation:
    """카테고리 기본 무드를 바탕으로 추상적인 BGM 메타데이터를 추천한다.

    category_rule_set.preserve_natural_audio가 True면(예: 음식/캠핑/여행처럼 실제 소리를
    보존해야 하는 카테고리) 에너지를 낮게 제한하고 덕킹 비율을 더 크게(볼륨을 더 많이 낮춤)
    권장해 배경음이 현장음/내레이션을 방해하지 않게 한다.
    """
    mood = get_rule(category).default_bgm_mood if category else "neutral"
    mood_label = MOOD_LABELS.get(mood, mood)
    tempo_range = _MOOD_TEMPO_RANGE_BPM.get(mood, _MOOD_TEMPO_RANGE_BPM["neutral"])
    energy = _MOOD_ENERGY.get(mood, BgmEnergy.MEDIUM)

    preserve_natural_audio = category_rule_set.preserve_natural_audio if category_rule_set else False
    if preserve_natural_audio:
        energy = _cap_energy(energy, BgmEnergy.LOW)
    duck_volume_ratio = NATURAL_AUDIO_DUCK_VOLUME_RATIO if preserve_natural_audio else DEFAULT_DUCK_VOLUME_RATIO

    category_label = CATEGORY_LABELS.get(category) if category else None
    search_keywords = _build_search_keywords(mood_label, category_label, energy)

    return BgmMetadataRecommendation(
        mood=mood,
        mood_label=mood_label,
        tempo_range_bpm=tempo_range,
        energy=energy,
        has_vocals=False,  # 내레이션과 겹치지 않도록 항상 보컬 없는 트랙을 권장한다
        search_keywords=search_keywords,
        duck_during_voice=True,
        duck_volume_ratio=duck_volume_ratio,
    )


def assert_no_forbidden_fields() -> None:
    """BgmMetadataRecommendation에 상업 음원 정보를 지어낼 수 있는 필드가 없는지 확인한다."""
    field_names = {f.name for f in fields(BgmMetadataRecommendation)}
    overlap = field_names & FORBIDDEN_FIELD_NAMES
    if overlap:
        raise AssertionError(f"BgmMetadataRecommendation에 금지된 필드가 있습니다: {overlap}")
