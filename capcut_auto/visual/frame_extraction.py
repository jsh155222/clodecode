"""대표 프레임 추출.

전체 영상을 통째로 AI에 보내지 않는다. 다음 시점에서만 대표 프레임을 뽑는다:
장면 전환, 문장 시작, 움직임 변화, 핵심 대상 등장, 전후 비교, 결과 공개, 그리고 그 사이를
채우는 기본 0.5~1초 간격.

장면 전환/움직임 변화는 ffmpeg의 실제 scene-change 신호(select='gt(scene,threshold)' +
showinfo)로 감지한다 - AI가 지어내지 않는다. 문장 시작/전후 비교/결과 공개처럼 의미가
필요한 트리거는 이미 분석된 실제 데이터(단어 타임스탬프, ai/video_structure.py의
VideoSection)에서만 끌어온다.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Sequence

from ..ai.video_structure import VideoSection, VideoSectionRole
from ..silence import require_binary
from ..subtitles import SubtitleLine

_PTS_TIME_RE = re.compile(r"pts_time:([\d.]+)")


class FrameTrigger(str, Enum):
    SCENE_CHANGE = "SCENE_CHANGE"
    SENTENCE_START = "SENTENCE_START"
    MOTION_CHANGE = "MOTION_CHANGE"
    KEY_SUBJECT_APPEARANCE = "KEY_SUBJECT_APPEARANCE"
    BEFORE_AFTER = "BEFORE_AFTER"
    RESULT_REVEAL = "RESULT_REVEAL"
    INTERVAL = "INTERVAL"


@dataclass(frozen=True)
class FrameCandidateTime:
    time: float
    trigger: FrameTrigger


@dataclass(frozen=True)
class ExtractedFrame:
    time: float
    trigger: FrameTrigger
    path: str


def _run_scene_detect(video_path: str, threshold: float) -> List[float]:
    """ffmpeg select='gt(scene,threshold)' + showinfo로 실제 장면전환 시각을 뽑는다."""
    ffmpeg = require_binary("ffmpeg")
    cmd = [
        ffmpeg,
        "-i",
        video_path,
        "-filter:v",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    times: List[float] = []
    for line in result.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        match = _PTS_TIME_RE.search(line)
        if match:
            times.append(float(match.group(1)))
    return times


def detect_scene_change_times(video_path: str, threshold: float = 0.35) -> List[float]:
    """하드컷 수준의 장면 전환 시각(초)을 실제 ffmpeg 장면감지로 찾는다."""
    return _run_scene_detect(video_path, threshold)


def detect_motion_change_times(video_path: str, threshold: float = 0.12) -> List[float]:
    """장면 전환보다 낮은 임계값으로 같은 감지기를 돌려, 컷은 아니지만 화면 변화가
    두드러지는 시점(움직임 변화)을 근사한다. ffmpeg에는 전용 "동작 변화" 필터가 없어
    같은 scene-change 신호를 더 민감한 임계값으로 재사용하는 것 - 별도 모션벡터
    추정 모델을 쓰는 게 아님을 명시해둔다.
    """
    return _run_scene_detect(video_path, threshold)


def sentence_start_times(lines: Sequence[SubtitleLine]) -> List[float]:
    """자막(문장) 줄의 시작 시각 = 문장 시작 트리거."""
    return [line.start for line in lines]


def derive_semantic_triggers_from_sections(
    sections: Sequence[VideoSection],
) -> Dict[FrameTrigger, List[float]]:
    """ai/video_structure.py가 실제로 분석한 VideoSection 목록에서 "전후 비교"/"결과 공개"
    트리거 시각을 규칙 기반으로 뽑는다 (여기서 새로 추측하지 않음 - 이미 분석된 역할만 사용).
    """
    result: Dict[FrameTrigger, List[float]] = {
        FrameTrigger.RESULT_REVEAL: [],
        FrameTrigger.BEFORE_AFTER: [],
    }
    ordered = sorted(sections, key=lambda s: s.start)
    for i, section in enumerate(ordered):
        if section.role in (VideoSectionRole.RESULT, VideoSectionRole.PROOF):
            result[FrameTrigger.RESULT_REVEAL].append(section.start)
        if i > 0 and ordered[i - 1].role == VideoSectionRole.PROCESS and section.role == VideoSectionRole.RESULT:
            result[FrameTrigger.BEFORE_AFTER].append(section.start)
    return result


def merge_and_space_trigger_times(
    trigger_times: Sequence[FrameCandidateTime],
    total_duration: float,
    min_gap: float = 0.5,
    max_gap: float = 1.0,
) -> List[FrameCandidateTime]:
    """트리거들을 시간순으로 합치고, min_gap보다 가까운 것들은 먼저 온 트리거만 남기고,
    max_gap보다 벌어진 구간은 INTERVAL 트리거로 채운다.
    """
    if min_gap <= 0 or max_gap < min_gap:
        raise ValueError("min_gap>0, max_gap>=min_gap 이어야 합니다")

    ordered = sorted(trigger_times, key=lambda t: t.time)
    spaced: List[FrameCandidateTime] = []
    for candidate in ordered:
        if spaced and candidate.time - spaced[-1].time < min_gap:
            continue
        if 0.0 <= candidate.time <= total_duration:
            spaced.append(candidate)

    filled: List[FrameCandidateTime] = []
    cursor = 0.0
    for candidate in spaced:
        while candidate.time - cursor > max_gap:
            cursor += max_gap
            filled.append(FrameCandidateTime(round(cursor, 3), FrameTrigger.INTERVAL))
        filled.append(candidate)
        cursor = candidate.time

    while total_duration - cursor > max_gap:
        cursor += max_gap
        filled.append(FrameCandidateTime(round(cursor, 3), FrameTrigger.INTERVAL))

    return sorted(filled, key=lambda t: t.time)


def _extract_frame_at(video_path: str, time: float, output_path: str) -> None:
    ffmpeg = require_binary("ffmpeg")
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(time),
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def extract_representative_frames(
    video_path: str,
    output_dir: str,
    total_duration: float,
    subtitle_lines: Sequence[SubtitleLine] = (),
    video_sections: Sequence[VideoSection] = (),
    key_subject_appearance_times: Sequence[float] = (),
    scene_threshold: float = 0.35,
    motion_threshold: float = 0.12,
    min_gap: float = 0.5,
    max_gap: float = 1.0,
) -> List[ExtractedFrame]:
    """대표 프레임을 실제로 추출해 output_dir에 저장하고 목록을 반환한다."""
    triggers: List[FrameCandidateTime] = []
    for t in detect_scene_change_times(video_path, scene_threshold):
        triggers.append(FrameCandidateTime(t, FrameTrigger.SCENE_CHANGE))
    for t in detect_motion_change_times(video_path, motion_threshold):
        triggers.append(FrameCandidateTime(t, FrameTrigger.MOTION_CHANGE))
    for t in sentence_start_times(subtitle_lines):
        triggers.append(FrameCandidateTime(t, FrameTrigger.SENTENCE_START))
    for t in key_subject_appearance_times:
        triggers.append(FrameCandidateTime(t, FrameTrigger.KEY_SUBJECT_APPEARANCE))

    semantic = derive_semantic_triggers_from_sections(video_sections)
    for trigger_type, times in semantic.items():
        for t in times:
            triggers.append(FrameCandidateTime(t, trigger_type))

    spaced = merge_and_space_trigger_times(triggers, total_duration, min_gap, max_gap)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    extracted: List[ExtractedFrame] = []
    for i, candidate in enumerate(spaced):
        frame_path = str(Path(output_dir) / f"frame_{i:04d}_{candidate.trigger.value.lower()}.jpg")
        _extract_frame_at(video_path, candidate.time, frame_path)
        extracted.append(ExtractedFrame(time=candidate.time, trigger=candidate.trigger, path=frame_path))

    return extracted
