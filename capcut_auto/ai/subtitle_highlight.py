"""자막 강조: 각 자막 줄에서 숫자/가격/위험/결과 등 핵심 단어를 최대 2개까지 강조한다.

강조 단어가 실제 자막 텍스트에 포함돼 있는지는 반드시 코드에서 검증한다 - AI가
자막에 없는 단어를 강조로 만들어내면(hallucination) 그 강조만 버린다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

import anthropic

from .client import AiModuleRequest, call_ai_module
from .schemas import SUBTITLE_HIGHLIGHT_SCHEMA
from .subtitle_optimizer import SubtitleLineWithId

SYSTEM_PROMPT = """당신은 한국어 인스타그램 릴스 자막의 강조 단어 선택기다.

각 자막 줄에서 시청자의 시선을 붙잡을 핵심 단어를 기본 1개, 최대 2개까지 고른다.

강조 단어는 반드시 해당 자막 줄의 실제 텍스트에 그대로 포함된 단어여야 한다.
자막에 없는 단어를 만들어내지 않는다.

각 단어에 NUMBER, PRICE, DURATION, PROBLEM, RISK, RESULT, ACTION, PRODUCT,
COMPARISON 중 하나의 유형을 부여한다.

반드시 지정된 JSON Schema에 맞는 데이터만 반환한다."""

MAX_HIGHLIGHTS_PER_LINE = 2


class SubtitleHighlightType(str, Enum):
    NUMBER = "NUMBER"
    PRICE = "PRICE"
    DURATION = "DURATION"
    PROBLEM = "PROBLEM"
    RISK = "RISK"
    RESULT = "RESULT"
    ACTION = "ACTION"
    PRODUCT = "PRODUCT"
    COMPARISON = "COMPARISON"


@dataclass(frozen=True)
class SubtitleHighlight:
    word: str
    type: SubtitleHighlightType


def validate_highlight(word: str, line_text: str) -> bool:
    """강조 단어가 실제 자막 텍스트에 포함되어 있는지 검증한다."""
    return bool(word) and word in line_text


def generate_highlights(
    lines: Sequence[SubtitleLineWithId],
    category_label: Optional[str] = None,
    *,
    client: Optional[anthropic.Anthropic] = None,
    **call_kwargs,
) -> Dict[str, List[SubtitleHighlight]]:
    """AI로 자막별 강조 단어를 생성하고, 자막에 실제로 없는 단어는 코드에서 걸러낸다.

    Raises:
        AiModuleError: AI 호출이 재시도/수정까지 실패한 경우. 호출자는 강조 없이
            (빈 딕셔너리) 진행하도록 폴백해야 한다.
    """
    request = AiModuleRequest(
        module_name="subtitle_highlight",
        system_prompt=SYSTEM_PROMPT,
        input_data={
            "category": category_label,
            "lines": [{"id": l.id, "text": l.text} for l in lines],
        },
        output_schema=SUBTITLE_HIGHLIGHT_SCHEMA,
    )
    result = call_ai_module(request, client=client, **call_kwargs)

    text_by_id = {l.id: l.text for l in lines}
    highlights_by_id: Dict[str, List[SubtitleHighlight]] = {}

    for item in result["lines"]:
        line_id = item["id"]
        line_text = text_by_id.get(line_id)
        if line_text is None:
            continue

        valid: List[SubtitleHighlight] = []
        for h in item["highlights"]:
            word = h["word"]
            if not validate_highlight(word, line_text):
                continue
            valid.append(SubtitleHighlight(word=word, type=SubtitleHighlightType(h["type"])))
            if len(valid) >= MAX_HIGHLIGHTS_PER_LINE:
                break

        highlights_by_id[line_id] = valid

    return highlights_by_id
