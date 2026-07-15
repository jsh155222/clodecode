"""컷 적용 후 타임라인 재계산: 단어/문장(자막)/장면/훅의 시간을 새 타임라인 기준으로
다시 계산한다.

효과음/BGM/크롭/줌은 아직 구현된 기능이 아니므로(이번 단계 범위 밖), 입력이 있으면
그대로 통과시키기만 하고 실제 재계산 로직은 없다 - 해당 기능이 생기면 이 모듈에
같은 방식(순수 시간 매핑)으로 추가하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence

from ..subtitles import SubtitleLine, group_words_into_lines, remap_words_to_new_timeline
from ..timeline import Interval, map_time_to_new_timeline
from ..transcribe import Word
from .video_structure import VideoSection


@dataclass(frozen=True)
class RecalcResult:
    success: bool
    words: List[Word]
    subtitle_lines: List[SubtitleLine]
    sections: List[VideoSection]
    hook_range: Optional[Interval]
    error: Optional[str] = None


def _map_boundary(t: float, sorted_keep: Sequence[Interval]) -> Optional[float]:
    """시각 t를 새 타임라인으로 매핑한다. t가 컷 구간 한가운데 있으면(=경계가 컷당한
    경우) 가장 가까운 유효 경계로 스냅해서라도 값을 반환한다(장면/훅이 근거 없이
    통째로 사라지는 것을 방지).
    """
    direct = map_time_to_new_timeline(t, sorted_keep)
    if direct is not None:
        return direct

    best_dist: Optional[float] = None
    best_value: Optional[float] = None
    cum = 0.0
    for iv in sorted_keep:
        for candidate_t, candidate_new in ((iv.start, cum), (iv.end, cum + iv.duration)):
            dist = abs(candidate_t - t)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_value = candidate_new
        cum += iv.duration
    return best_value


def recalculate_words(words: Sequence[Word], keep_intervals: Sequence[Interval]) -> List[Word]:
    return remap_words_to_new_timeline(words, keep_intervals)


def recalculate_subtitle_lines(
    words: Sequence[Word], keep_intervals: Sequence[Interval], max_chars: int = 24
) -> List[SubtitleLine]:
    remapped_words = recalculate_words(words, keep_intervals)
    return group_words_into_lines(remapped_words, max_chars=max_chars)


def recalculate_sections(
    sections: Sequence[VideoSection], keep_intervals: Sequence[Interval]
) -> List[VideoSection]:
    sorted_keep = sorted(keep_intervals, key=lambda x: x.start)
    recalced: List[VideoSection] = []
    for sec in sections:
        new_start = _map_boundary(sec.start, sorted_keep)
        new_end = _map_boundary(sec.end, sorted_keep)
        if new_start is None or new_end is None or new_end <= new_start:
            continue
        recalced.append(replace(sec, start=new_start, end=new_end))
    return recalced


def recalculate_hook_range(hook_range: Optional[Interval], keep_intervals: Sequence[Interval]) -> Optional[Interval]:
    """훅은 보통 영상 맨 앞(0초부터)에 별도 트랙으로 얹히므로, 원본 타임라인 위치와
    무관하게 새 타임라인의 처음 위치를 기준으로 길이만 유지한다.
    """
    if hook_range is None:
        return None
    duration = hook_range.duration
    return Interval(0.0, duration)


def recalculate_timeline(
    words: Sequence[Word],
    keep_intervals: Sequence[Interval],
    sections: Sequence[VideoSection] = (),
    hook_range: Optional[Interval] = None,
    max_chars: int = 24,
) -> RecalcResult:
    """컷 적용 후 단어/자막/장면/훅 시간을 전부 재계산한다.

    재계산이 실패하면(예외 발생) success=False와 함께 원본 값을 그대로 담아 반환한다 -
    호출자는 success가 False면 내보내기를 막고 EditHistory로 원상복구해야 한다.
    """
    try:
        new_words = recalculate_words(words, keep_intervals)
        new_lines = recalculate_subtitle_lines(words, keep_intervals, max_chars=max_chars)
        new_sections = recalculate_sections(sections, keep_intervals) if sections else []
        new_hook = recalculate_hook_range(hook_range, keep_intervals)

        if _has_overlapping_lines(new_lines):
            raise ValueError("재계산된 자막 구간이 서로 겹칩니다")

        return RecalcResult(
            success=True,
            words=new_words,
            subtitle_lines=new_lines,
            sections=new_sections,
            hook_range=new_hook,
        )
    except Exception as exc:  # noqa: BLE001 - 재계산 실패는 항상 안전하게 폴백해야 함
        return RecalcResult(
            success=False,
            words=list(words),
            subtitle_lines=[],
            sections=list(sections),
            hook_range=hook_range,
            error=str(exc),
        )


def _has_overlapping_lines(lines: Sequence[SubtitleLine]) -> bool:
    ordered = sorted(lines, key=lambda l: l.start)
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.start < prev.end:
            return True
    return False
