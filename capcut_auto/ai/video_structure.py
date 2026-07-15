"""영상 구조 분석: 발화/타임스탬프를 구간별 역할(HOOK/PROBLEM/...)로 분류한다."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Sequence

import anthropic

from .client import AiModuleError, AiModuleRequest, call_ai_module
from .schemas import VIDEO_STRUCTURE_SCHEMA

SYSTEM_PROMPT = """당신은 한국어 인스타그램 릴스 영상의 구조 분석기다.

입력으로 제공된 발화, 타임스탬프와 실제 영상 분석 정보만 사용한다.

입력에 없는 영상 내용이나 화면을 추측하지 않는다.

각 구간을 HOOK, PROBLEM, CAUSE, SOLUTION, PROCESS,
PROOF, RESULT, CTA, TRANSITION, UNKNOWN 중 하나로 분류한다.

모든 시간은 숫자형 초 단위로 반환한다.

반드시 지정된 JSON Schema에 맞는 데이터만 반환한다."""


class VideoSectionRole(str, Enum):
    HOOK = "HOOK"
    PROBLEM = "PROBLEM"
    CAUSE = "CAUSE"
    SOLUTION = "SOLUTION"
    PROCESS = "PROCESS"
    PROOF = "PROOF"
    RESULT = "RESULT"
    CTA = "CTA"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class VideoSection:
    start: float
    end: float
    role: VideoSectionRole
    summary: str


@dataclass(frozen=True)
class TranscriptSegment:
    """분석 입력으로 넘길 발화 구간. id는 훅 생성 등 다른 모듈에서 근거로 참조된다."""

    id: str
    start: float
    end: float
    text: str


def _build_input(
    segments: Sequence[TranscriptSegment],
    total_duration: float,
    category_label: Optional[str],
) -> dict:
    return {
        "totalDuration": total_duration,
        "category": category_label,
        "segments": [
            {"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in segments
        ],
    }


def analyze_video_structure(
    segments: Sequence[TranscriptSegment],
    total_duration: float,
    category_label: Optional[str] = None,
    *,
    client: Optional[anthropic.Anthropic] = None,
    **call_kwargs: Any,
) -> List[VideoSection]:
    """AI로 영상을 구간별 역할로 분류한다.

    Raises:
        AiModuleError: AI 호출이 재시도/수정까지 실패한 경우. 호출자는 이 경우
            구조 분석 없이(빈 리스트 또는 UNKNOWN 단일 구간) 진행하도록 폴백해야 한다.
    """
    request = AiModuleRequest(
        module_name="video_structure",
        system_prompt=SYSTEM_PROMPT,
        input_data=_build_input(segments, total_duration, category_label),
        output_schema=VIDEO_STRUCTURE_SCHEMA,
    )
    result: Any = call_ai_module(request, client=client, **call_kwargs)

    sections: List[VideoSection] = []
    for item in result["sections"]:
        sections.append(
            VideoSection(
                start=float(item["start"]),
                end=float(item["end"]),
                role=VideoSectionRole(item["role"]),
                summary=item["summary"],
            )
        )
    return sections


def fallback_single_unknown_section(total_duration: float) -> List[VideoSection]:
    """구조 분석 AI 호출이 실패했을 때 쓰는 폴백: 전체를 UNKNOWN 구간 하나로 취급한다."""
    return [VideoSection(start=0.0, end=total_duration, role=VideoSectionRole.UNKNOWN, summary="")]
