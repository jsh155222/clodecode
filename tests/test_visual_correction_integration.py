"""실제 ffmpeg(+libvidstab)로 visual_correction 파이프라인을 검증하는 통합 테스트.

ffmpeg가 없는 환경에서는 자동으로 건너뛴다 (순수 로직 테스트는 test_visual_correction.py 참고).
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.visual_correction import analyze_brightness, apply_brightness_correction, auto_correct, compute_correction_params

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_synthetic_video(path: str, duration: int = 2) -> None:
    """어두운 단색 영상을 생성한다 (밝기 보정이 실제로 필요한 입력)."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x101010:s=160x120:d={duration}:r=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestVisualCorrectionIntegration(unittest.TestCase):
    def test_analyze_brightness_detects_dark_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "dark.mp4")
            _make_synthetic_video(video_path)

            stats = analyze_brightness(video_path)

            self.assertLess(stats.mean_luma, 100)
            self.assertGreater(stats.sample_count, 0)

    def test_apply_brightness_correction_produces_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "dark.mp4")
            _make_synthetic_video(video_path)

            stats = analyze_brightness(video_path)
            params = compute_correction_params(stats)
            self.assertGreater(params.brightness, 0)  # 어두운 영상이므로 밝게 보정되어야 함

            out_path = str(Path(tmp) / "corrected.mp4")
            apply_brightness_correction(video_path, out_path, params)

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)

    def test_auto_correct_full_pipeline_with_stabilization(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "dark.mp4")
            _make_synthetic_video(video_path)
            workdir = str(Path(tmp) / "work")

            result = auto_correct(video_path, workdir, stabilize_enabled=True)

            self.assertTrue(result.stabilized)
            self.assertTrue(Path(result.output_path).exists())
            self.assertGreater(Path(result.output_path).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
