"""버벅임(간투사/필러워드, 즉시 반복) 탐지.

두 가지 휴리스틱으로 '버벅거리는 구간'을 찾는다:

1. 필러워드: "어", "음", "그..." 같은 순수 추임새가 단독 단어로 등장하고
   발화 길이가 짧을 때 (의미 있는 단어와의 오탐을 줄이기 위한 길이 제한).
2. 즉시 반복: "그 그 그거는" 처럼 같은 단어가 짧은 간격으로 연달아
   반복될 때, 마지막 발화를 제외한 앞선 반복들을 컷 대상으로 삼는다.

두 휴리스틱 모두 완벽하지 않으므로 CLI에서 필러워드 목록과 임계값을
조정할 수 있게 설계한다.
"""

from __future__ import annotations

import re
from typing import List, Sequence

from .timeline import Interval
from .transcribe import Word

# 표준 한국어 추임새(간투사). 단독으로 나올 때만 필러로 간주한다.
DEFAULT_FILLER_WORDS = frozenset(
    {
        "어", "어어", "어어어",
        "음", "음음", "음..", "으음",
        "으", "으으",
        "아", "아아",
        "에", "에에",
        "저", "저기", "저기요",
        "그", "그니까", "그러니까", "그게",
        "인제", "이제",
        "막",
        "뭐", "뭐지", "뭐랄까",
        "그래서", "그래가지고",
    }
)

_PUNCT_RE = re.compile(r"[.,!?~…\"'\-\s]+")


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", text).strip()


def detect_filler_words(
    words: Sequence[Word],
    filler_words: Sequence[str] = DEFAULT_FILLER_WORDS,
    max_filler_duration: float = 0.6,
) -> List[Interval]:
    """필러워드로만 이루어진 짧은 발화 구간을 찾는다."""
    filler_set = {_normalize(w) for w in filler_words}
    intervals: List[Interval] = []
    for w in words:
        norm = _normalize(w.text)
        duration = w.end - w.start
        if norm in filler_set and duration <= max_filler_duration:
            intervals.append(Interval(w.start, w.end))
    return intervals


def detect_repetitions(
    words: Sequence[Word], max_gap: float = 0.3, min_repeats: int = 2
) -> List[Interval]:
    """짧은 간격으로 동일 단어가 반복되는 구간(말더듬)을 찾는다.

    반복 구간에서는 마지막 발화만 남기고 그 앞의 반복들을 컷 대상으로 삼는다.
    """
    intervals: List[Interval] = []
    n = len(words)
    i = 0
    while i < n:
        run = [words[i]]
        j = i + 1
        while j < n:
            prev, cur = run[-1], words[j]
            if _normalize(cur.text) == _normalize(prev.text) and (cur.start - prev.end) <= max_gap:
                run.append(cur)
                j += 1
            else:
                break
        if len(run) >= min_repeats:
            intervals.append(Interval(run[0].start, run[-2].end))
        i = j if j > i + 1 else i + 1
    return intervals
