"""컷 편집 후 타임라인에 맞춘 자막 재정렬 및 SRT 생성."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from .timeline import Interval, map_time_to_new_timeline
from .transcribe import Word


@dataclass(frozen=True)
class SubtitleLine:
    start: float
    end: float
    text: str


def remap_words_to_new_timeline(words: Sequence[Word], keep_intervals: Sequence[Interval]) -> List[Word]:
    """컷된 구간에 걸린 단어는 버리고, 남은 단어는 새 타임라인 시각으로 이동시킨다.

    단어의 중간 지점(midpoint)이 컷 구간 안에 있으면 그 단어는 완전히
    잘려나간 것으로 보고 제외한다. 그렇지 않으면 원래 길이를 유지한 채
    새 타임라인 위치로 옮긴다.
    """
    remapped: List[Word] = []
    for w in words:
        midpoint = (w.start + w.end) / 2
        new_mid = map_time_to_new_timeline(midpoint, keep_intervals)
        if new_mid is None:
            continue
        duration = w.end - w.start
        remapped.append(Word(new_mid - duration / 2, new_mid + duration / 2, w.text))
    return remapped


def group_words_into_lines(
    words: Sequence[Word],
    max_chars: int = 24,
    max_duration: float = 5.0,
    max_gap: float = 0.6,
) -> List[SubtitleLine]:
    """연속된 단어들을 자막 한 줄 단위로 묶는다.

    다음 조건 중 하나라도 만족하면 새 줄을 시작한다:
    - 글자 수가 max_chars를 넘어감
    - 줄 전체 길이가 max_duration을 넘어감
    - 이전 단어와의 간격이 max_gap보다 김(자연스러운 끊어읽기)
    """
    lines: List[SubtitleLine] = []
    current: List[Word] = []

    def flush() -> None:
        if current:
            text = " ".join(w.text for w in current)
            lines.append(SubtitleLine(current[0].start, current[-1].end, text))

    for w in words:
        if current:
            prev = current[-1]
            joined_text = " ".join(w2.text for w2 in current) + " " + w.text
            would_exceed_chars = len(joined_text) > max_chars
            would_exceed_duration = (w.end - current[0].start) > max_duration
            gap_too_large = (w.start - prev.end) > max_gap
            if would_exceed_chars or would_exceed_duration or gap_too_large:
                flush()
                current = []
        current.append(w)
    flush()
    return lines


def _format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(lines: Sequence[SubtitleLine], path: str) -> str:
    """자막 줄 리스트를 표준 SRT 파일로 저장한다."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, line in enumerate(lines, start=1):
        start_ts = _format_srt_timestamp(line.start)
        end_ts = _format_srt_timestamp(line.end)
        blocks.append(f"{i}\n{start_ts} --> {end_ts}\n{line.text}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    return str(out)
