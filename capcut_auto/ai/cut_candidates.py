"""컷 후보 분석: 삭제/검토/유지 후보를 confidence·contextRisk와 함께 판단한다.

초기 버전에서는 AUTO_CUT 기준을 만족하는 후보라도 실제로는 항상 사용자가 검토한 뒤
적용한다 (meets_auto_apply_criteria()는 UI에 "자동 적용 가능" 배지를 보여주는 용도일 뿐,
승인 없이 실제로 컷을 적용하는 데 쓰지 않는다).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Sequence

import anthropic

from ..timeline import Interval
from .client import AiModuleRequest, call_ai_module
from .schemas import CUT_CANDIDATES_SCHEMA
from .video_structure import TranscriptSegment

SYSTEM_PROMPT = """당신은 한국어 인스타그램 릴스의 컷 편집 판단 엔진이다.

목표는 영상을 무조건 짧게 만드는 것이 아니다.

영상의 의미, 정보와 자연스러움을 유지하면서
불필요한 구간만 찾아야 한다.

입력된 카테고리 보호 규칙을 우선 적용한다.

안전 정보, 사용 방법, 핵심 절차, 전후 비교, 결과,
증거, 자연음과 ASMR은 보수적으로 판단한다.

시각 정보가 없으면 화면 동작을 추측하지 않는다.

각 후보에 confidence와 contextRisk를 부여한다.

반드시 지정된 JSON Schema에 맞는 데이터만 반환한다."""

AUTO_APPLY_CONFIDENCE_MIN = 0.92
AUTO_APPLY_CONTEXT_RISK_MAX = 0.25

# 삭제 후보로 고려하는 사유들 (reasonCode에 자유 문자열이 오지만, 대표 사유는 문서화해둔다)
DELETE_CANDIDATE_REASONS = [
    "long_silence",
    "meaningless_filler",
    "misspeak",
    "same_sentence_retry",
    "repeated_utterance",
    "duplicate_explanation",
    "setup_motion",
    "technical_mistake",
    "uninformative_long_section",
]

# 보수적으로 판단해야 하는(=쉽게 자르면 안 되는) 보호 구간 사유들
PROTECTED_REASONS = [
    "safety_info",
    "usage_instructions",
    "key_procedure",
    "before_after",
    "actual_result",
    "evidence",
    "emotional_reaction",
    "natural_sound_or_asmr",
    "category_protected_scene",
]


class CutAction(str, Enum):
    AUTO_CUT = "AUTO_CUT"
    REVIEW = "REVIEW"
    KEEP = "KEEP"


@dataclass(frozen=True)
class ProtectedInterval:
    start: float
    end: float
    reason: str


@dataclass(frozen=True)
class CutCandidate:
    id: str
    start: float
    end: float
    action: CutAction
    reason_code: str
    reason: str
    confidence: float
    context_risk: float
    estimated_time_saved: float


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def meets_auto_apply_criteria(
    candidate: CutCandidate, protected_intervals: Sequence[ProtectedInterval]
) -> bool:
    """자동 적용 후보 기준: confidence>=0.92, contextRisk<=0.25, 보호 구간과 겹치지 않음.

    주의: 이 함수가 True를 반환해도 초기 버전에서는 실제로 자동 적용하지 않는다
    (모든 후보는 사용자 검토를 거친다). UI에서 "자동 적용 가능" 표시 용도로만 쓴다.
    """
    if candidate.confidence < AUTO_APPLY_CONFIDENCE_MIN:
        return False
    if candidate.context_risk > AUTO_APPLY_CONTEXT_RISK_MAX:
        return False
    for protected in protected_intervals:
        if _overlaps(candidate.start, candidate.end, protected.start, protected.end):
            return False
    return True


def _build_input(
    segments: Sequence[TranscriptSegment],
    total_duration: float,
    category_label: Optional[str],
    category_protection_rules: Sequence[str],
    protected_intervals: Sequence[ProtectedInterval],
    removable_moment_hints: Sequence[str] = (),
    preferred_pacing: Optional[str] = None,
    preserve_natural_audio: Optional[bool] = None,
    safety_checks: Sequence[str] = (),
) -> dict:
    return {
        "totalDuration": total_duration,
        "category": category_label,
        "categoryProtectionRules": list(category_protection_rules),
        "removableMomentHints": list(removable_moment_hints),
        "preferredPacing": preferred_pacing,
        "preserveNaturalAudio": preserve_natural_audio,
        "safetyChecks": list(safety_checks),
        "protectedIntervals": [
            {"start": p.start, "end": p.end, "reason": p.reason} for p in protected_intervals
        ],
        "segments": [
            {"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in segments
        ],
    }


def analyze_cut_candidates(
    segments: Sequence[TranscriptSegment],
    total_duration: float,
    category_label: Optional[str] = None,
    category_protection_rules: Sequence[str] = (),
    protected_intervals: Sequence[ProtectedInterval] = (),
    removable_moment_hints: Sequence[str] = (),
    preferred_pacing: Optional[str] = None,
    preserve_natural_audio: Optional[bool] = None,
    safety_checks: Sequence[str] = (),
    *,
    client: Optional[anthropic.Anthropic] = None,
    **call_kwargs,
) -> List[CutCandidate]:
    """AI로 컷 후보를 분석한다.

    removable_moment_hints/preferred_pacing/preserve_natural_audio/safety_checks는
    category_rules.CategoryRuleSet에서 뽑아 카테고리별로 다르게 채워 넣는 값들이다
    (ai/category_rules.py의 build_removable_moment_hints 등 참고).

    Raises:
        AiModuleError: 재시도/수정까지 실패. 호출자는 기존 규칙 기반 파이프라인
            (silence.py + stutter.py + cutlist.py)으로 폴백해야 한다
            (fallback_from_rule_based_intervals() 참고).
    """
    request = AiModuleRequest(
        module_name="cut_candidates",
        system_prompt=SYSTEM_PROMPT,
        input_data=_build_input(
            segments,
            total_duration,
            category_label,
            category_protection_rules,
            protected_intervals,
            removable_moment_hints=removable_moment_hints,
            preferred_pacing=preferred_pacing,
            preserve_natural_audio=preserve_natural_audio,
            safety_checks=safety_checks,
        ),
        output_schema=CUT_CANDIDATES_SCHEMA,
    )
    result = call_ai_module(request, client=client, **call_kwargs)

    candidates: List[CutCandidate] = []
    for item in result["candidates"]:
        start = float(item["start"])
        end = float(item["end"])
        candidates.append(
            CutCandidate(
                id=uuid.uuid4().hex[:8],
                start=start,
                end=end,
                action=CutAction(item["action"]),
                reason_code=item["reasonCode"],
                reason=item["reason"],
                confidence=float(item["confidence"]),
                context_risk=float(item["contextRisk"]),
                estimated_time_saved=max(0.0, end - start),
            )
        )
    return candidates


def fallback_from_rule_based_intervals(
    silence_intervals: Sequence, filler_intervals: Sequence, repetition_intervals: Sequence
) -> List[CutCandidate]:
    """AI 컷 분석 실패 시 폴백: 기존 규칙 기반(silence/filler/repetition) 탐지 결과를
    같은 CutCandidate 모양으로 변환한다. confidence/contextRisk는 "AI가 평가하지 않았다"는
    뜻의 중립값(0.5)을 부여해, 반드시 사용자 검토를 거치게 한다.
    """
    reason_map = {
        "silence": ("long_silence", "무음 구간"),
        "filler": ("meaningless_filler", "의미 없는 추임새"),
        "repetition": ("repeated_utterance", "반복 발화"),
    }
    candidates: List[CutCandidate] = []
    for source, intervals in (
        ("silence", silence_intervals),
        ("filler", filler_intervals),
        ("repetition", repetition_intervals),
    ):
        reason_code, reason = reason_map[source]
        for iv in intervals:
            candidates.append(
                CutCandidate(
                    id=uuid.uuid4().hex[:8],
                    start=iv.start,
                    end=iv.end,
                    action=CutAction.REVIEW,
                    reason_code=reason_code,
                    reason=reason,
                    confidence=0.5,
                    context_risk=0.5,
                    estimated_time_saved=max(0.0, iv.end - iv.start),
                )
            )
    candidates.sort(key=lambda c: c.start)
    return candidates


def review_candidates(
    candidates: Sequence[CutCandidate], decisions: Dict[str, CutAction]
) -> List[CutCandidate]:
    """사용자 컷 검토: 사용자가 후보별로 정한 액션(승인/검토중/유지)을 후보 목록에 반영한다.

    decisions에 없는 후보는 AI(또는 폴백)가 매긴 원래 action을 그대로 유지한다.
    """
    return [replace(c, action=decisions[c.id]) if c.id in decisions else c for c in candidates]


def approved_cut_intervals(
    candidates: Sequence[CutCandidate], decisions: Dict[str, CutAction]
) -> List[Interval]:
    """승인된 컷만 골라 ai/cut_apply.py의 apply_approved_cuts()에 넘길 Interval로 변환한다.

    초기 버전 정책(모든 후보는 사용자가 검토한 뒤에만 적용한다)을 지키기 위해, 후보의
    action 필드가 이미 AUTO_CUT이더라도 그것만으로는 적용하지 않는다 - decisions에
    사용자가 명시적으로 AUTO_CUT을 선택한 기록이 있는 후보만 적용 대상으로 삼는다.
    (decisions는 review_candidates()에 넘긴 것과 같은 딕셔너리를 그대로 재사용하면 된다.)
    """
    approved_ids = {cid for cid, action in decisions.items() if action == CutAction.AUTO_CUT}
    return [Interval(c.start, c.end) for c in candidates if c.id in approved_ids]
