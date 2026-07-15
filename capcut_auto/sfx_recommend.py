"""장면에 맞는 효과음 추천.

사용자가 전문 효과음 이름을 직접 고르지 않는다 - 영상 장면을 분석해 앱이 후보를
추천하고, 사용자는 미리 듣고 승인만 한다.

처리 순서: 장면 분석 → 효과음 목적 분류 → 내부 에셋 검색 → 실제 오디오 충돌 확인 →
최대 3개 후보 → (미리듣기/승인은 UI 몫) → apply_approved_sfx()로 타임라인 적용.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .ai.video_structure import VideoSection, VideoSectionRole
from .categories import ContentCategory
from .category_rules import CategoryRuleSet
from .silence import require_binary
from .timeline import Interval
from .transcribe import Word

DEFAULT_MAX_PER_10S = 2
DEFAULT_WINDOW_SECONDS = 10.0
DEFAULT_SFX_DURATION = 0.35
MIN_SCENE_CONFIDENCE = 0.5


class SfxPurpose(str, Enum):
    RESULT_REVEAL = "RESULT_REVEAL"  # 완성/결과 공개
    TRANSITION = "TRANSITION"  # 장면 전환
    EMPHASIS = "EMPHASIS"  # 핵심 포인트 강조
    SUCCESS = "SUCCESS"  # 성공/완료
    BUILD_UP = "BUILD_UP"  # 궁금증을 유발하는 도입부

    @property
    def label(self) -> str:
        return {
            SfxPurpose.RESULT_REVEAL: "결과 공개",
            SfxPurpose.TRANSITION: "장면 전환",
            SfxPurpose.EMPHASIS: "포인트 강조",
            SfxPurpose.SUCCESS: "완료/성공",
            SfxPurpose.BUILD_UP: "궁금증 유발",
        }[self]


_ROLE_TO_PURPOSE: Dict[VideoSectionRole, SfxPurpose] = {
    VideoSectionRole.RESULT: SfxPurpose.RESULT_REVEAL,
    VideoSectionRole.PROOF: SfxPurpose.RESULT_REVEAL,
    VideoSectionRole.TRANSITION: SfxPurpose.TRANSITION,
    VideoSectionRole.CTA: SfxPurpose.SUCCESS,
    VideoSectionRole.HOOK: SfxPurpose.BUILD_UP,
}

# 카테고리별로 허용하지 않는 효과음 목적 (스펙에 명시된 것만 제한 - 지어내지 않음)
_CATEGORY_PURPOSE_RESTRICTIONS: Dict[ContentCategory, Set[SfxPurpose]] = {
    # 육아는 과도한 충격음/놀라게 하는 효과음을 제한한다 - 궁금증 유발형 riser는 제외
    ContentCategory.PARENTING: {SfxPurpose.RESULT_REVEAL, SfxPurpose.TRANSITION, SfxPurpose.SUCCESS},
}


@dataclass(frozen=True)
class SfxAsset:
    id: str
    purpose: SfxPurpose
    label: str
    path: str
    duration: float = DEFAULT_SFX_DURATION


@dataclass(frozen=True)
class SfxCandidate:
    asset: SfxAsset
    reason: str


@dataclass(frozen=True)
class SfxPlacement:
    time: float
    asset_id: str


@dataclass
class SfxRecommendation:
    time: float
    purpose: SfxPurpose
    candidates: List[SfxCandidate]
    selected_asset_id: Optional[str] = None
    approved: bool = False


# ---- 1. 장면 분석 -> 2. 효과음 목적 분류 --------------------------------------------


def classify_scene_purpose(section: VideoSection) -> Optional[SfxPurpose]:
    """VideoSection의 역할(이미 분석된 실제 데이터)만으로 효과음 목적을 정한다.
    매핑되지 않는 역할(PROBLEM/CAUSE/SOLUTION/PROCESS/UNKNOWN)은 효과음이 필요 없다고 보고
    None을 반환한다 - 영상에 없는 목적을 지어내지 않는다.
    """
    return _ROLE_TO_PURPOSE.get(section.role)


# ---- 3. 내부 에셋 검색(실제 ffmpeg로 절차적 생성, 라이선스 있는 음원은 구할 수 없음) ----


def _generate_tone_sequence_sfx(output_path: str, freqs: Sequence[float], note_duration: float, fade: float) -> str:
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_bin, "-y"]
    for freq in freqs:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={note_duration}"]
    n = len(freqs)
    concat_inputs = "".join(f"[{i}:a]" for i in range(n))
    filter_complex = (
        f"{concat_inputs}concat=n={n}:v=0:a=1,"
        f"afade=t=in:st=0:d={min(fade, note_duration/4)},"
        f"afade=t=out:st={max(0.0, n*note_duration-fade)}:d={fade},"
        f"volume=0.55[aout]"
    )
    cmd += ["-filter_complex", filter_complex, "-map", "[aout]", "-c:a", "aac", str(output_path)]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


# 목적별 절차적 SFX 정의 (실제 라이선스 음원 라이브러리가 없어 ffmpeg로 생성한 플레이스홀더 -
# audio_mix.py의 BGM/pop과 같은 이유·같은 방식)
_ASSET_DEFINITIONS: Dict[SfxPurpose, List["tuple[str, str, Sequence[float], float]"]] = {
    SfxPurpose.RESULT_REVEAL: [
        ("soft_reveal_1", "부드러운 결과 공개음 1", (523.25, 659.25, 783.99), 0.12),
        ("soft_reveal_2", "부드러운 결과 공개음 2", (440.00, 554.37, 659.25), 0.14),
        ("soft_reveal_3", "은은한 결과 공개음", (392.00, 523.25, 659.25), 0.16),
    ],
    SfxPurpose.TRANSITION: [
        ("soft_whoosh_1", "부드러운 전환음 1", (349.23, 293.66), 0.10),
        ("soft_whoosh_2", "부드러운 전환음 2", (392.00, 329.63), 0.10),
        ("soft_whoosh_3", "가벼운 전환음", (440.00, 349.23), 0.10),
    ],
    SfxPurpose.EMPHASIS: [
        ("emphasis_tap_1", "포인트 강조음 1", (880.00,), 0.05),
        ("emphasis_tap_2", "포인트 강조음 2", (987.77,), 0.05),
    ],
    SfxPurpose.SUCCESS: [
        ("success_chime_1", "완료 알림음 1", (523.25, 659.25, 783.99, 1046.50), 0.10),
        ("success_chime_2", "완료 알림음 2", (440.00, 554.37, 659.25, 880.00), 0.10),
    ],
    SfxPurpose.BUILD_UP: [
        ("build_up_1", "궁금증 유발음 1", (261.63, 329.63, 392.00, 523.25), 0.08),
        ("build_up_2", "궁금증 유발음 2", (293.66, 349.23, 440.00, 587.33), 0.08),
    ],
}


def ensure_sfx_asset_library(dir_path: str) -> Dict[SfxPurpose, List[SfxAsset]]:
    """목적별 SFX 후보 에셋을 실제로 생성(이미 있으면 재사용)하고 목록을 반환한다."""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    library: Dict[SfxPurpose, List[SfxAsset]] = {}
    for purpose, definitions in _ASSET_DEFINITIONS.items():
        assets: List[SfxAsset] = []
        for asset_id, label, freqs, fade in definitions:
            path = str(Path(dir_path) / f"{asset_id}.m4a")
            if not Path(path).exists():
                _generate_tone_sequence_sfx(path, freqs, note_duration=0.12, fade=fade)
            assets.append(SfxAsset(id=asset_id, purpose=purpose, label=label, path=path))
        library[purpose] = assets
    return library


_REASON_TEMPLATES: Dict[SfxPurpose, str] = {
    SfxPurpose.RESULT_REVEAL: "변화가 처음 보이는 순간을 자연스럽게 강조합니다.",
    SfxPurpose.TRANSITION: "장면이 바뀌는 흐름을 매끄럽게 이어줍니다.",
    SfxPurpose.EMPHASIS: "놓치기 쉬운 핵심 포인트를 짧게 강조합니다.",
    SfxPurpose.SUCCESS: "작업이 완료됐다는 느낌을 산뜻하게 전달합니다.",
    SfxPurpose.BUILD_UP: "다음 장면에 대한 궁금증을 살짝 끌어올립니다.",
}


def search_sfx_candidates(
    library: Dict[SfxPurpose, List[SfxAsset]], purpose: SfxPurpose, max_candidates: int = 3
) -> List[SfxCandidate]:
    """목적에 맞는 에셋을 최대 max_candidates개까지 후보로 만든다."""
    assets = library.get(purpose, [])[:max_candidates]
    reason = _REASON_TEMPLATES.get(purpose, "")
    return [SfxCandidate(asset=asset, reason=reason) for asset in assets]


# ---- 4. 실제 오디오 충돌 확인 --------------------------------------------------------


def exceeds_frequency_limit(
    existing_times: Sequence[float],
    new_time: float,
    window: float = DEFAULT_WINDOW_SECONDS,
    max_per_window: int = DEFAULT_MAX_PER_10S,
) -> bool:
    """10초당 기본 최대 2개 규칙."""
    count = sum(1 for t in existing_times if abs(t - new_time) < window / 2)
    return count >= max_per_window


def overlaps_voice(new_time: float, duration: float, words: Sequence[Word]) -> bool:
    """음성을 가리지 않음 - 발화 구간과 겹치면 배치하지 않는다."""
    end = new_time + duration
    return any(w.start < end and new_time < w.end for w in words)


def overlaps_protected_interval(new_time: float, duration: float, protected_intervals: Sequence[Interval]) -> bool:
    """실제 자연음/ASMR 등 보호 구간과 겹치면 배치하지 않는다."""
    end = new_time + duration
    return any(iv.start < end and new_time < iv.end for iv in protected_intervals)


def is_consecutive_repeat(existing_placements: Sequence[SfxPlacement], candidate_asset_id: str) -> bool:
    """같은 효과음 연속 반복 금지."""
    if not existing_placements:
        return False
    return existing_placements[-1].asset_id == candidate_asset_id


# ---- 5~8. 전체 추천 파이프라인 -------------------------------------------------------


def recommend_sfx_for_scenes(
    sections: Sequence[VideoSection],
    words: Sequence[Word],
    protected_intervals: Sequence[Interval],
    category: Optional[ContentCategory],
    category_rule_set: Optional[CategoryRuleSet],
    library: Dict[SfxPurpose, List[SfxAsset]],
    section_confidence: Optional[Dict[float, float]] = None,
    max_candidates: int = 3,
) -> List[SfxRecommendation]:
    """장면마다 효과음 후보를 추천한다. 규칙을 어기는 경우 효과음 없음(추천 자체를 만들지 않음).

    section_confidence: {section.start: 0~1} - 장면 분석 신뢰도. 낮으면(< MIN_SCENE_CONFIDENCE)
    효과음을 추천하지 않는다 ("신뢰도가 낮으면 효과음 없음").
    """
    restricted = _CATEGORY_PURPOSE_RESTRICTIONS.get(category, set()) if category else set()
    natural_audio_priority = category_rule_set.preserve_natural_audio if category_rule_set else False

    recommendations: List[SfxRecommendation] = []
    placed: List[SfxPlacement] = []
    placed_times: List[float] = []

    for section in sorted(sections, key=lambda s: s.start):
        purpose = classify_scene_purpose(section)
        if purpose is None:
            continue
        if restricted and purpose not in restricted:
            continue

        confidence = (section_confidence or {}).get(section.start, 1.0)
        if confidence < MIN_SCENE_CONFIDENCE:
            continue

        time = section.start
        # 음식/캠핑처럼 자연음을 우선하는 카테고리는 궁금증 유발형(BUILD_UP, 상대적으로
        # 더 튀는 소리)을 배제해 실제 소리를 방해하지 않게 한다
        if natural_audio_priority and purpose == SfxPurpose.BUILD_UP:
            continue
        if overlaps_protected_interval(time, DEFAULT_SFX_DURATION, protected_intervals):
            continue
        if overlaps_voice(time, DEFAULT_SFX_DURATION, words):
            continue
        if exceeds_frequency_limit(placed_times, time):
            continue

        candidates = search_sfx_candidates(library, purpose, max_candidates)
        candidates = [c for c in candidates if not is_consecutive_repeat(placed, c.asset.id)]
        if not candidates:
            continue

        recommendations.append(SfxRecommendation(time=time, purpose=purpose, candidates=candidates))
        # 추천 시점에는 아직 사용자가 승인 전이지만, 빈도/반복 규칙을 다음 장면에도
        # 일관되게 적용하기 위해 1순위 후보를 임시로 "예정된 배치"로 취급한다
        placed.append(SfxPlacement(time=time, asset_id=candidates[0].asset.id))
        placed_times.append(time)

    return recommendations


def apply_approved_sfx(recommendations: Sequence[SfxRecommendation]) -> List[SfxPlacement]:
    """사용자가 승인하고 소리를 고른 추천만 실제 타임라인 배치로 확정한다."""
    return [
        SfxPlacement(time=r.time, asset_id=r.selected_asset_id)
        for r in recommendations
        if r.approved and r.selected_asset_id is not None
    ]
