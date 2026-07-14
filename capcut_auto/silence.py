"""ffmpeg 기반 오디오 추출 및 무음 구간(silence) 탐지."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

from .timeline import Interval

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[0-9.]+)")


def _bundled_binary_dir() -> Path:
    """install.bat이 내려받아 놓는 ffmpeg 번들 위치 (<repo_root>/ffmpeg/bin)."""
    return Path(__file__).resolve().parent.parent / "ffmpeg" / "bin"


def _require_binary(name: str) -> str:
    """번들된 ffmpeg/ffprobe가 있으면 그 경로를, 없으면 PATH에 등록된 실행 파일명을 반환한다."""
    exe_name = f"{name}.exe" if platform.system() == "Windows" else name
    bundled = _bundled_binary_dir() / exe_name
    if bundled.exists():
        return str(bundled)
    if shutil.which(name) is None:
        raise RuntimeError(
            f"'{name}' 실행 파일을 찾을 수 없습니다. install.bat을 실행하거나 ffmpeg를 설치한 뒤 다시 시도하세요."
        )
    return name


def get_duration(media_path: str) -> float:
    """ffprobe로 미디어 길이(초)를 조회한다."""
    ffprobe_bin = _require_binary("ffprobe")
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(media_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_audio(video_path: str, out_path: str, sample_rate: int = 16000) -> str:
    """영상에서 모노 WAV 오디오를 추출한다 (whisper/무음 탐지 입력용)."""
    ffmpeg_bin = _require_binary("ffmpeg")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out_path


def detect_silence(
    audio_path: str, noise_db: float = -30.0, min_silence_duration: float = 0.5
) -> List[Interval]:
    """ffmpeg silencedetect 필터로 무음 구간을 찾는다.

    Args:
        audio_path: 오디오/영상 파일 경로.
        noise_db: 이 값(dB)보다 조용하면 무음으로 간주 (예: -30dB).
        min_silence_duration: 이 시간(초) 이상 지속되어야 무음 구간으로 인정.
    """
    ffmpeg_bin = _require_binary("ffmpeg")
    cmd = [
        ffmpeg_bin,
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return _parse_silencedetect_output(result.stderr)


def _parse_silencedetect_output(stderr_text: str) -> List[Interval]:
    intervals: List[Interval] = []
    pending_start = None
    for line in stderr_text.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and pending_start is not None:
            end = float(end_match.group(1))
            intervals.append(Interval(pending_start, end))
            pending_start = None
    return intervals
