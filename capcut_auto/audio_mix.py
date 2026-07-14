"""배경음(BGM)/효과음(SFX) 믹싱.

주의: 실제 라이선스가 있는 음원 라이브러리를 이 프로젝트가 구할 방법이 없어서,
배경음은 ffmpeg lavfi로 절차적으로 생성한 간단한 화음 루프(플레이스홀더)를 사용한다.
믹싱 파이프라인(ffmpeg amix/adelay/aloop) 자체는 실제 오디오 파일로 교체해도
그대로 동작하도록 설계했다 — BGM_MOODS에 매핑된 파일 경로만 실제 음원으로
바꾸면 된다.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

from .silence import require_binary
from .timeline import Interval

# 무드별 코드(주파수 Hz) - categories.py의 default_bgm_mood 값과 대응한다.
MOOD_CHORDS: Dict[str, list] = {
    "cozy": [261.63, 329.63, 392.00],  # C major
    "upbeat": [293.66, 369.99, 440.00],  # D major
    "warm": [220.00, 277.18, 329.63],  # A minor(warm)
    "gentle": [246.94, 311.13, 369.99],  # 부드러운 톤
    "cinematic": [130.81, 164.81, 196.00],  # 낮고 웅장한 톤
    "neutral": [220.00, 277.18, 329.63],
}

MOOD_LABELS: Dict[str, str] = {
    "cozy": "포근한",
    "upbeat": "경쾌한",
    "warm": "따뜻한",
    "gentle": "잔잔한",
    "cinematic": "웅장한",
    "neutral": "기본",
}


@dataclass(frozen=True)
class BgmTrack:
    mood: str
    label: str
    path: str


def _generate_bgm_track(mood: str, output_path: str, duration: int = 12) -> str:
    """무드에 맞는 화음을 sine 파형들로 합성해 짧은 루프 트랙을 만든다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    freqs = MOOD_CHORDS.get(mood, MOOD_CHORDS["neutral"])

    cmd = [ffmpeg_bin, "-y"]
    for freq in freqs:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}"]

    n = len(freqs)
    mix_inputs = "".join(f"[{i}:a]" for i in range(n))
    filter_complex = f"{mix_inputs}amix=inputs={n}:duration=longest:normalize=1,tremolo=f=0.15:d=0.25,volume=0.5[aout]"

    cmd += ["-filter_complex", filter_complex, "-map", "[aout]", "-c:a", "aac", str(output_path)]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def ensure_bgm_library(dir_path: str) -> Dict[str, BgmTrack]:
    """플레이스홀더 배경음 라이브러리를 dir_path에 생성(이미 있으면 재사용)하고 목록을 반환한다."""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    library: Dict[str, BgmTrack] = {}
    for mood in MOOD_CHORDS:
        track_path = str(Path(dir_path) / f"{mood}.m4a")
        if not Path(track_path).exists():
            _generate_bgm_track(mood, track_path)
        library[mood] = BgmTrack(mood=mood, label=MOOD_LABELS.get(mood, mood), path=track_path)
    return library


def _generate_pop_sfx(output_path: str) -> str:
    """컷 전환 지점에 쓸 짧은 팝/클릭 효과음을 생성한다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1200:duration=0.12",
        "-af",
        "afade=t=out:st=0.02:d=0.1,volume=0.6",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def ensure_sfx_library(dir_path: str) -> Dict[str, str]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    pop_path = str(Path(dir_path) / "pop.m4a")
    if not Path(pop_path).exists():
        _generate_pop_sfx(pop_path)
    return {"pop": pop_path}


def _bgm_volume_expression(bgm_volume: float, voice_intervals: Sequence[Interval], duck_volume_ratio: float) -> str:
    """발화 구간에서는 배경음을 duck_volume_ratio만큼 줄이는 ffmpeg volume 표현식을 만든다.

    between(t,start,end)는 구간 안이면 1, 아니면 0을 반환한다. 여러 구간의 합이 0보다 크면
    (=하나 이상의 발화 구간 안이면) ducked 볼륨을, 아니면 기본 볼륨을 쓴다.
    """
    duck_volume = bgm_volume * duck_volume_ratio
    if not voice_intervals:
        return f"volume={bgm_volume}"
    between_terms = "+".join(f"between(t,{iv.start},{iv.end})" for iv in voice_intervals)
    return f"volume=eval=frame:volume='if(gt({between_terms},0),{duck_volume},{bgm_volume})'"


def mix_bgm(
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float = 0.18,
    original_volume: float = 1.0,
    voice_intervals: Optional[Sequence[Interval]] = None,
    duck_volume_ratio: float = 0.35,
) -> str:
    """원본 오디오에 배경음을 합성한다. 배경음은 영상 길이에 맞춰 반복(loop)된다.

    voice_intervals를 넘기면 발화 구간에서 배경음 볼륨을 duck_volume_ratio만큼 자동으로
    줄인다("음성 중 자동 볼륨 감소"). 넘기지 않으면 기존과 동일한 고정 볼륨으로 믹싱한다.
    """
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    bgm_volume_expr = _bgm_volume_expression(bgm_volume, voice_intervals or [], duck_volume_ratio)
    filter_complex = (
        f"[0:a]volume={original_volume}[a0];"
        f"[1:a]aloop=loop=-1:size=2e9,{bgm_volume_expr}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(bgm_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def apply_sfx_at_cuts(
    video_path: str,
    output_path: str,
    cut_points: Sequence[float],
    sfx_path: str,
    sfx_volume: float = 0.5,
) -> str:
    """각 컷 전환 지점(cut_points, 초 단위)에 효과음을 자동으로 겹쳐 넣는다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if not cut_points:
        shutil.copy(video_path, output_path)
        return output_path

    filter_parts = []
    delayed_labels = []
    for i, t in enumerate(cut_points):
        delay_ms = max(0, int(round(t * 1000)))
        label = f"sfx{i}"
        filter_parts.append(f"[1:a]adelay={delay_ms}|{delay_ms},volume={sfx_volume}[{label}]")
        delayed_labels.append(f"[{label}]")

    mix_inputs = "[0:a]" + "".join(delayed_labels)
    filter_parts.append(f"{mix_inputs}amix=inputs={len(delayed_labels) + 1}:duration=first:dropout_transition=0[aout]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(sfx_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
