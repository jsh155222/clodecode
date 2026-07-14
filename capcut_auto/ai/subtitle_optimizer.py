"""자막 최적화: 발화 의미를 유지하면서 모바일에서 빠르게 읽히는 자막으로 재구성한다.

AI가 규칙을 어긴 개별 줄은 그 줄만 원본으로 폴백하고, 최종 결과 전체가 여전히
겹치면(회복 불가능한 상태) 통째로 원본 자막으로 폴백한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import anthropic

from .client import AiModuleRequest, call_ai_module
from .schemas import SUBTITLE_OPTIMIZE_SCHEMA

SYSTEM_PROMPT = """당신은 한국어 인스타그램 릴스 자막 편집기다.

입력된 발화 의미를 유지하면서
모바일에서 빠르게 읽히는 자막으로 재구성한다.

선택된 카테고리의 자막 밀도 규칙을 적용한다.

입력에 없는 효능, 수치, 비용, 위험 또는 결과를 추가하지 않는다.

한 화면 최대 2줄, 한 줄 기본 14자 이하로 작성한다.

반드시 지정된 JSON Schema에 맞는 데이터만 반환한다."""

MAX_LINES_PER_SCREEN = 2
MAX_CHARS_PER_LINE = 14
MIN_EXPOSURE_SECONDS = 0.7

_UNIT_SUFFIXES = (
    "분", "초", "시간", "일", "개", "명", "원", "%", "kg", "g", "ml", "L",
    "cm", "m", "km", "회", "번", "인분",
)
_LONE_PARTICLES = {
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "와", "과",
    "도", "만", "까지", "부터", "로", "으로", "이나", "나",
}


@dataclass(frozen=True)
class SubtitleLineWithId:
    id: str
    start: float
    end: float
    text: str


def validate_optimized_line(line: SubtitleLineWithId) -> Optional[str]:
    """규칙 위반 시 위반 사유 문자열을, 통과하면 None을 반환한다."""
    parts = line.text.split("\n")
    if len(parts) > MAX_LINES_PER_SCREEN:
        return f"한 화면 최대 {MAX_LINES_PER_SCREEN}줄을 초과함"

    for part in parts:
        if len(part) > MAX_CHARS_PER_LINE:
            return f"한 줄 {MAX_CHARS_PER_LINE}자를 초과함: {part!r}"
        if part.strip() in _LONE_PARTICLES:
            return f"조사만 단독으로 분리됨: {part!r}"

    for i in range(len(parts) - 1):
        left = parts[i].rstrip()
        right = parts[i + 1].lstrip()
        if left and left[-1].isdigit() and right.startswith(_UNIT_SUFFIXES):
            return "숫자와 단위가 줄 경계에서 분리됨"

    if (line.end - line.start) < MIN_EXPOSURE_SECONDS:
        return f"노출 시간이 {MIN_EXPOSURE_SECONDS}초 미만임"

    return None


def _has_overlap(lines: Sequence[SubtitleLineWithId]) -> bool:
    ordered = sorted(lines, key=lambda l: l.start)
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.start < prev.end:
            return True
    return False


def optimize_subtitles(
    lines: Sequence[SubtitleLineWithId],
    category_label: Optional[str] = None,
    density_rule: Optional[str] = None,
    *,
    client: Optional[anthropic.Anthropic] = None,
    **call_kwargs,
) -> List[SubtitleLineWithId]:
    """AI로 자막을 최적화한다.

    Raises:
        AiModuleError: AI 호출이 재시도/수정까지 실패한 경우. 호출자는 원본
            자막 리스트를 그대로 사용하도록 폴백해야 한다.
    """
    request = AiModuleRequest(
        module_name="subtitle_optimizer",
        system_prompt=SYSTEM_PROMPT,
        input_data={
            "category": category_label,
            "densityRule": density_rule,
            "lines": [{"id": l.id, "start": l.start, "end": l.end, "text": l.text} for l in lines],
        },
        output_schema=SUBTITLE_OPTIMIZE_SCHEMA,
    )
    result = call_ai_module(request, client=client, **call_kwargs)

    by_id = {l.id: l for l in lines}
    output: List[SubtitleLineWithId] = []
    seen_ids = set()

    for item in result["lines"]:
        original = by_id.get(item["id"])
        if original is None:
            continue  # 존재하지 않는 id는 무시
        candidate = SubtitleLineWithId(
            id=item["id"], start=float(item["start"]), end=float(item["end"]), text=item["text"]
        )
        violation = validate_optimized_line(candidate)
        output.append(original if violation is not None else candidate)
        seen_ids.add(item["id"])

    # AI가 빠뜨린 줄은 원본을 그대로 채워 넣는다
    for l in lines:
        if l.id not in seen_ids:
            output.append(l)

    output.sort(key=lambda l: l.start)

    if _has_overlap(output):
        return list(lines)  # 최종 안전망: 회복 불가능하면 통째로 원본 폴백

    return output
