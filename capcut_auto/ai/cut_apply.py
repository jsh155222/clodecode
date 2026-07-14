"""승인된 컷 적용 엔진 (AI 아님, 순수 로직 + ffmpeg 미리보기 렌더링).

- 원본 영상 파일은 절대 덮어쓰지 않는다 (모든 연산은 Interval 리스트 위에서만 일어나고,
  draft_builder는 항상 원본 video_path 전체 길이를 참조한다).
- 겹치는 컷 병합/범위 초과 제거/음절 절단 방지는 승인된 컷 구간에 적용한 뒤
  keep_intervals(남길 구간)를 다시 계산한다.
- EditHistory가 실행 취소/다시 실행/전체 원상복구를 위한 스냅샷 스택을 관리한다.
- render_crossfade_preview()는 실제 ffmpeg로 컷이 적용된 미리보기 영상을 만든다.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from ..silence import require_binary
from ..timeline import Interval, build_keep_intervals, merge_intervals
from ..transcribe import Word


@dataclass(frozen=True)
class ApplyResult:
    """전후 비교(미리보기)에 필요한 정보를 함께 담은 컷 적용 결과."""

    keep_intervals: List[Interval]
    previous_keep_intervals: List[Interval]
    kept_duration: float
    previous_kept_duration: float
    total_duration: float


def clip_to_video_range(intervals: Sequence[Interval], total_duration: float) -> List[Interval]:
    """영상 범위를 벗어난 시간을 제거(클램프)한다."""
    clipped: List[Interval] = []
    for iv in intervals:
        start = max(0.0, min(iv.start, total_duration))
        end = max(0.0, min(iv.end, total_duration))
        if end > start:
            clipped.append(Interval(start, end))
    return clipped


def snap_to_word_boundaries(intervals: Sequence[Interval], words: Sequence[Word]) -> List[Interval]:
    """컷 구간의 시작/끝이 단어(음절) 중간에 걸치면, 더 가까운 단어 경계로 스냅해
    단어가 반토막 나지 않게 한다.
    """

    def snap(t: float) -> float:
        for w in words:
            if w.start < t < w.end:
                return w.start if (t - w.start) <= (w.end - t) else w.end
        return t

    snapped: List[Interval] = []
    for iv in intervals:
        start = snap(iv.start)
        end = snap(iv.end)
        if end > start:
            snapped.append(Interval(start, end))
    return snapped


def apply_approved_cuts(
    total_duration: float,
    approved_cut_intervals: Sequence[Interval],
    words: Sequence[Word] = (),
    previous_keep_intervals: Optional[Sequence[Interval]] = None,
) -> ApplyResult:
    """승인된 컷 구간을 병합/범위클램프/단어경계스냅한 뒤 keep_intervals를 재계산한다.

    previous_keep_intervals를 주면 결과에 전후 비교 정보(kept_duration 등)가 함께 담긴다.
    """
    prev = list(previous_keep_intervals) if previous_keep_intervals is not None else [
        Interval(0.0, total_duration)
    ]
    prev_kept = sum(iv.duration for iv in prev)

    merged = merge_intervals(approved_cut_intervals)
    clipped = clip_to_video_range(merged, total_duration)
    snapped = snap_to_word_boundaries(clipped, words) if words else clipped
    # snap 이후 재병합(스냅으로 인접/겹침이 생길 수 있음) + 여집합 계산을 한 번에 처리
    keep, _final_cuts = build_keep_intervals(snapped, total_duration)
    kept = sum(iv.duration for iv in keep)

    return ApplyResult(
        keep_intervals=keep,
        previous_keep_intervals=prev,
        kept_duration=kept,
        previous_kept_duration=prev_kept,
        total_duration=total_duration,
    )


@dataclass
class EditSnapshot:
    keep_intervals: List[Interval]
    label: str


@dataclass
class EditHistory:
    """실행 취소(undo) / 다시 실행(redo) / 전체 원상복구(revert)를 지원하는 편집 기록."""

    original_keep_intervals: List[Interval]
    _stack: List[EditSnapshot] = field(init=False)
    _pointer: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._stack = [EditSnapshot(list(self.original_keep_intervals), "initial")]
        self._pointer = 0

    @property
    def current(self) -> List[Interval]:
        return list(self._stack[self._pointer].keep_intervals)

    @property
    def can_undo(self) -> bool:
        return self._pointer > 0

    @property
    def can_redo(self) -> bool:
        return self._pointer < len(self._stack) - 1

    def push(self, keep_intervals: Sequence[Interval], label: str) -> None:
        """새 편집을 기록한다. undo 이후에 새로 편집하면 이후의 redo 기록은 버려진다."""
        self._stack = self._stack[: self._pointer + 1]
        self._stack.append(EditSnapshot(list(keep_intervals), label))
        self._pointer += 1

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        self._pointer -= 1
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._pointer += 1
        return True

    def revert_to_original(self) -> None:
        self._stack = self._stack[:1]
        self._pointer = 0


def render_crossfade_preview(
    video_path: str,
    keep_intervals: Sequence[Interval],
    output_path: str,
    crossfade_seconds: float = 0.15,
) -> str:
    """keep_intervals만 이어붙인 실제 미리보기 영상을 ffmpeg로 렌더링한다.

    각 클립의 길이 자체는 바꾸지 않고(비디오/오디오 동기화 유지), 컷 경계에서 오디오만
    짧게 in/out 페이드를 걸어 팝 노이즈 없이 매끄럽게 이어지도록 한다(진짜 겹치는
    acrossfade를 쓰면 오디오만 살짝 짧아져 비디오와 어긋나므로 페이드 방식을 택함).
    """
    if not keep_intervals:
        raise ValueError("keep_intervals가 비어 있습니다")

    ffmpeg = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    n = len(keep_intervals)
    filter_parts = []
    v_labels = []
    a_labels = []
    for i, iv in enumerate(keep_intervals):
        duration = iv.duration
        cf = min(crossfade_seconds, duration / 2) if crossfade_seconds > 0 else 0.0

        filter_parts.append(
            f"[0:v]trim=start={iv.start}:end={iv.end},setpts=PTS-STARTPTS[v{i}]"
        )

        afade_ops = []
        if cf > 0 and i > 0:
            afade_ops.append(f"afade=t=in:st=0:d={cf}")
        if cf > 0 and i < n - 1:
            afade_ops.append(f"afade=t=out:st={max(0.0, duration - cf)}:d={cf}")
        afade_suffix = "," + ",".join(afade_ops) if afade_ops else ""
        filter_parts.append(
            f"[0:a]atrim=start={iv.start}:end={iv.end},asetpts=PTS-STARTPTS{afade_suffix}[a{i}]"
        )

        v_labels.append(f"[v{i}]")
        a_labels.append(f"[a{i}]")

    concat_inputs = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vout][aout]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
