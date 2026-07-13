"""시간 구간(Interval) 연산 유틸리티.

모든 시간 단위는 초(float)이며, 원본 영상 타임라인 기준이다.
ffmpeg/whisper 등 외부 도구에 의존하지 않는 순수 로직만 담아
독립적으로 유닛테스트할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass(frozen=True, order=True)
class Interval:
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"end({self.end}) < start({self.start})")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: "Interval", gap: float = 0.0) -> bool:
        return self.start <= other.end + gap and other.start <= self.end + gap

    def clamp(self, lo: float, hi: float) -> Optional["Interval"]:
        s, e = max(self.start, lo), min(self.end, hi)
        return Interval(s, e) if s < e else None


def merge_intervals(intervals: Sequence[Interval], gap: float = 0.0) -> List[Interval]:
    """겹치거나 `gap`(초) 이내로 인접한 구간을 하나로 합친다."""
    cleaned = [iv for iv in intervals if iv.duration > 0]
    if not cleaned:
        return []
    ordered = sorted(cleaned, key=lambda iv: iv.start)
    merged = [ordered[0]]
    for iv in ordered[1:]:
        last = merged[-1]
        if iv.start <= last.end + gap:
            merged[-1] = Interval(last.start, max(last.end, iv.end))
        else:
            merged.append(iv)
    return merged


def pad_intervals(
    intervals: Sequence[Interval], pad: float, total_duration: Optional[float] = None
) -> List[Interval]:
    """각 구간 양쪽에 `pad`초씩 여유를 준다 (자막/음절이 잘리지 않도록).

    결과는 병합되어 있지 않으므로 필요 시 merge_intervals를 다시 호출한다.
    """
    lo = 0.0
    hi = total_duration if total_duration is not None else float("inf")
    padded = []
    for iv in intervals:
        s = max(lo, iv.start - pad)
        e = min(hi, iv.end + pad)
        if e > s:
            padded.append(Interval(s, e))
    return padded


def shrink_intervals(intervals: Sequence[Interval], shrink: float) -> List[Interval]:
    """각 구간 양쪽을 `shrink`초씩 줄인다.

    무음 컷 경계에서 정적을 약간 남겨 편집점이 부자연스럽게 뚝 끊기지
    않도록 할 때 사용한다 (컷 구간 자체를 줄이는 것이므로 더 적게 잘라낸다).
    줄인 결과 길이가 0 이하가 되면 해당 구간은 버린다(너무 짧아 컷할 가치가 없음).
    """
    shrunk = []
    for iv in intervals:
        s, e = iv.start + shrink, iv.end - shrink
        if e > s:
            shrunk.append(Interval(s, e))
    return shrunk


def invert_intervals(cut_intervals: Sequence[Interval], total_duration: float) -> List[Interval]:
    """`cut_intervals`(병합되어 있어야 함)의 여집합, 즉 '남길 구간'을 반환한다."""
    keep: List[Interval] = []
    cursor = 0.0
    for iv in sorted(cut_intervals, key=lambda x: x.start):
        s = max(iv.start, 0.0)
        e = min(iv.end, total_duration)
        if s > cursor:
            keep.append(Interval(cursor, s))
        cursor = max(cursor, e)
    if cursor < total_duration:
        keep.append(Interval(cursor, total_duration))
    return [iv for iv in keep if iv.duration > 0]


def build_keep_intervals(
    cut_intervals: Sequence[Interval],
    total_duration: float,
    min_keep_duration: float = 0.0,
) -> "tuple[List[Interval], List[Interval]]":
    """컷 구간들로부터 최종 '남길 구간'과 '자를 구간'을 계산한다.

    두 컷 사이에 낀 구간이 `min_keep_duration`보다 짧으면(초미세 flicker 방지)
    그 구간도 컷에 흡수시켜 다시 계산한다.

    Returns:
        (keep_intervals, final_cut_intervals)
    """
    merged_cuts = merge_intervals(cut_intervals)
    keep = invert_intervals(merged_cuts, total_duration)

    tiny = [k for k in keep if k.duration < min_keep_duration]
    if tiny:
        merged_cuts = merge_intervals(list(merged_cuts) + tiny)
        keep = invert_intervals(merged_cuts, total_duration)

    return keep, merged_cuts


def map_time_to_new_timeline(t: float, keep_intervals: Sequence[Interval]) -> Optional[float]:
    """원본 타임라인의 시각 `t`를, 컷 편집 후 압축된 새 타임라인 시각으로 변환.

    `t`가 컷 구간(어느 keep_interval에도 속하지 않음) 안에 있으면 None을 반환한다.
    """
    cum = 0.0
    for iv in sorted(keep_intervals, key=lambda x: x.start):
        if iv.start <= t <= iv.end:
            return cum + (t - iv.start)
        cum += iv.duration
    return None


def total_kept_duration(keep_intervals: Sequence[Interval]) -> float:
    return sum(iv.duration for iv in keep_intervals)
