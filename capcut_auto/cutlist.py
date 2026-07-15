"""무음/필러/반복 구간을 합쳐 최종 컷 리스트(keep/cut 구간)를 계산한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .timeline import (
    Interval,
    build_keep_intervals,
    pad_intervals,
    shrink_intervals,
    total_kept_duration,
)


@dataclass
class CutlistConfig:
    # 무음 구간 경계에서 남겨둘 정적 여유(초). 클수록 덜 공격적으로 컷.
    silence_edge_padding: float = 0.12
    # 필러/반복 구간은 입 모양 소음까지 지우기 위해 약간 확장(초).
    filler_edge_expand: float = 0.05
    # 두 컷 사이에 남은 구간이 이보다 짧으면 그 구간도 컷에 흡수(깜빡임 방지).
    min_keep_duration: float = 0.12
    # 이보다 짧은 컷은 무시(효과가 거의 없는 미세 컷 방지).
    min_cut_duration: float = 0.15


@dataclass
class CutlistResult:
    total_duration: float
    keep_intervals: List[Interval]
    cut_intervals: List[Interval]

    @property
    def kept_duration(self) -> float:
        return total_kept_duration(self.keep_intervals)

    @property
    def removed_duration(self) -> float:
        return self.total_duration - self.kept_duration


def build_cutlist(
    total_duration: float,
    silence_intervals: Sequence[Interval] = (),
    filler_intervals: Sequence[Interval] = (),
    repetition_intervals: Sequence[Interval] = (),
    config: Optional[CutlistConfig] = None,
) -> CutlistResult:
    """모든 후보 컷 구간을 결합해 최종 keep/cut 타임라인을 만든다."""
    config = config or CutlistConfig()
    shrunk_silence = shrink_intervals(silence_intervals, config.silence_edge_padding)
    expanded_filler = pad_intervals(filler_intervals, config.filler_edge_expand, total_duration)
    expanded_repeat = pad_intervals(repetition_intervals, config.filler_edge_expand, total_duration)

    all_cuts = [*shrunk_silence, *expanded_filler, *expanded_repeat]
    all_cuts = [iv for iv in all_cuts if iv.duration >= config.min_cut_duration]

    keep, final_cuts = build_keep_intervals(all_cuts, total_duration, config.min_keep_duration)
    return CutlistResult(total_duration=total_duration, keep_intervals=keep, cut_intervals=final_cuts)
