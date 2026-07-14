"""ffmpeg 고전적 영상처리 기반 화면 자동 보정 (밝기/대비 + 흔들림 안정화).

주의: 이것은 딥러닝 기반 자동 색보정/피사체 인식 안정화가 아니라, ffmpeg의
signalstats(노출 측정) + eq(밝기/대비 조정) + vidstab(흔들림 안정화, libvidstab)
필터를 조합한 결정론적(deterministic) 고전 영상처리다. 입력이 같으면 항상
같은 보정값이 나온다.
"""

from __future__ import annotations

import re
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .silence import require_binary

_YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


@dataclass(frozen=True)
class BrightnessStats:
    mean_luma: float  # 0~255 (평균 휘도)
    stddev_luma: float  # 프레임 간 휘도 표준편차 (낮을수록 대비가 납작함)
    sample_count: int


@dataclass(frozen=True)
class CorrectionParams:
    brightness: float  # ffmpeg eq 필터 범위: -1.0 ~ 1.0
    contrast: float  # ffmpeg eq 필터 범위: 0.0 ~ 2.0 (1.0 = 변화 없음)


@dataclass(frozen=True)
class VisualCorrectionResult:
    output_path: str
    brightness_stats: BrightnessStats
    correction_params: CorrectionParams
    stabilized: bool


def analyze_brightness(video_path: str, sample_frames: Optional[int] = 60) -> BrightnessStats:
    """signalstats 필터로 평균/표준편차 휘도를 측정한다."""
    ffmpeg_bin = require_binary("ffmpeg")
    vf = "signalstats,metadata=print:file=-"
    cmd = [ffmpeg_bin, "-i", str(video_path), "-vf", vf]
    if sample_frames:
        cmd += ["-frames:v", str(sample_frames)]
    cmd += ["-f", "null", "-"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    values = [float(m) for m in _YAVG_RE.findall(result.stdout)]
    if not values:
        raise RuntimeError("밝기 분석에 실패했습니다 (signalstats 출력을 읽을 수 없습니다).")

    mean = statistics.fmean(values)
    stddev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return BrightnessStats(mean_luma=mean, stddev_luma=stddev, sample_count=len(values))


def compute_correction_params(
    stats: BrightnessStats,
    target_mean: float = 128.0,
    max_brightness_adjust: float = 0.15,
    target_stddev: float = 50.0,
) -> CorrectionParams:
    """측정된 밝기 통계로부터 ffmpeg eq 필터 파라미터를 계산한다 (순수 함수, ffmpeg 불필요)."""
    luma_diff = target_mean - stats.mean_luma  # 양수면 더 밝게 보정
    brightness = luma_diff / 255.0
    brightness = max(-max_brightness_adjust, min(max_brightness_adjust, brightness))

    if stats.stddev_luma > 0:
        contrast = min(1.3, max(0.85, target_stddev / stats.stddev_luma))
    else:
        contrast = 1.0

    return CorrectionParams(brightness=round(brightness, 4), contrast=round(contrast, 4))


def apply_brightness_correction(video_path: str, output_path: str, params: CorrectionParams) -> str:
    """eq 필터로 밝기/대비를 실제로 적용한 새 영상 파일을 만든다."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vf = f"eq=brightness={params.brightness}:contrast={params.contrast}"
    cmd = [ffmpeg_bin, "-y", "-i", str(video_path), "-vf", vf, "-c:a", "copy", str(output_path)]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def stabilize(video_path: str, output_path: str, workdir: str, smoothing: int = 10, shakiness: int = 5) -> str:
    """2-pass libvidstab로 흔들림을 안정화한다 (vidstabdetect -> vidstabtransform)."""
    ffmpeg_bin = require_binary("ffmpeg")
    Path(workdir).mkdir(parents=True, exist_ok=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    transforms_path = str(Path(workdir) / "transforms.trf")

    detect_cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"vidstabdetect=shakiness={shakiness}:result={transforms_path}",
        "-f",
        "null",
        "-",
    ]
    subprocess.run(detect_cmd, capture_output=True, text=True, check=True)

    transform_cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"vidstabtransform=input={transforms_path}:smoothing={smoothing}",
        "-c:a",
        "copy",
        str(output_path),
    ]
    subprocess.run(transform_cmd, capture_output=True, text=True, check=True)
    return output_path


def auto_correct(video_path: str, workdir: str, stabilize_enabled: bool = True) -> VisualCorrectionResult:
    """밝기/대비 자동 보정 후, 필요하면 흔들림 안정화까지 이어서 적용한다."""
    Path(workdir).mkdir(parents=True, exist_ok=True)

    stats = analyze_brightness(video_path)
    params = compute_correction_params(stats)

    brightness_out = str(Path(workdir) / "brightness_corrected.mp4")
    apply_brightness_correction(video_path, brightness_out, params)

    final_out = brightness_out
    if stabilize_enabled:
        stabilized_out = str(Path(workdir) / "stabilized.mp4")
        stabilize(brightness_out, stabilized_out, workdir)
        final_out = stabilized_out

    return VisualCorrectionResult(
        output_path=final_out,
        brightness_stats=stats,
        correction_params=params,
        stabilized=stabilize_enabled,
    )
