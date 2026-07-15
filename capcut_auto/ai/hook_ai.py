"""AI 훅(도입부 문구) 후보 생성: 실제 영상 근거(segment id)가 있는 훅만 신뢰한다.

각 훅의 evidenceSegmentIds가 실제로 존재하는 발화 segment를 가리키는지는
반드시 코드에서 다시 검증한다 - 존재하지 않는 id를 근거로 대는 훅은 버린다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Set

import anthropic

from .client import AiModuleRequest, call_ai_module
from .schemas import HOOK_CANDIDATES_SCHEMA
from .video_structure import TranscriptSegment

SYSTEM_PROMPT = """당신은 한국어 인스타그램 릴스의 초반 훅 작성기다.

영상에 실제 포함된 사실, 문제, 과정과 결과만 사용한다.

입력에 없는 비용, 통계, 확률, 위험 또는 전문가 의견을 만들지 않는다.

선택된 카테고리 특성을 반영한다.

각 훅에는 실제 근거 segment ID를 포함한다.

근거가 부족하면 과장 위험을 높이고 추천 후보에서 제외한다.

반드시 지정된 JSON Schema에 맞는 데이터만 반환한다."""


class HookType(str, Enum):
    PROBLEM = "PROBLEM"
    CURIOSITY = "CURIOSITY"
    BEFORE_AFTER = "BEFORE_AFTER"
    LOSS = "LOSS"
    EXPERIMENT = "EXPERIMENT"
    CONFESSION = "CONFESSION"
    RESULT_FIRST = "RESULT_FIRST"
    QUESTION = "QUESTION"


@dataclass(frozen=True)
class HookCandidate:
    text: str
    type: HookType
    evidence_segment_ids: List[str]
    exaggeration_risk: float


def validate_hook_grounding(hook: HookCandidate, valid_segment_ids: Set[str]) -> bool:
    """훅이 실제로 존재하는 segment만 근거로 대고 있는지 검증한다."""
    if not hook.evidence_segment_ids:
        return False
    return all(sid in valid_segment_ids for sid in hook.evidence_segment_ids)


def generate_ai_hooks(
    topic: str,
    segments: Sequence[TranscriptSegment],
    category_label: Optional[str] = None,
    safety_checks: Sequence[str] = (),
    *,
    client: Optional[anthropic.Anthropic] = None,
    **call_kwargs,
) -> List[HookCandidate]:
    """AI로 훅 후보 3~5개를 생성하고, 근거 segment id가 실재하는 후보만 남긴다.

    safety_checks는 category_rules.CategoryRuleSet에서 뽑은 카테고리별 안전 규칙이다
    (예: 뷰티의 "의학적 효능 생성 금지", 여행의 "장소명과 가격을 추측하지 않는다").

    Raises:
        AiModuleError: AI 호출이 재시도/수정까지 실패한 경우. 호출자는 기존
            템플릿 기반 hooks.py로 폴백해야 한다.
    """
    request = AiModuleRequest(
        module_name="hook_ai",
        system_prompt=SYSTEM_PROMPT,
        input_data={
            "topic": topic,
            "category": category_label,
            "safetyChecks": list(safety_checks),
            "segments": [{"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in segments],
        },
        output_schema=HOOK_CANDIDATES_SCHEMA,
    )
    result = call_ai_module(request, client=client, **call_kwargs)

    valid_ids = {s.id for s in segments}
    hooks: List[HookCandidate] = []
    for item in result["hooks"]:
        candidate = HookCandidate(
            text=item["text"],
            type=HookType(item["type"]),
            evidence_segment_ids=list(item["evidenceSegmentIds"]),
            exaggeration_risk=float(item["exaggerationRisk"]),
        )
        if validate_hook_grounding(candidate, valid_ids):
            hooks.append(candidate)

    return hooks
