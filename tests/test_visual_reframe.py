"""9:16 리프레이밍(capcut_auto/visual/reframe.py) 테스트. (테스트 시나리오 12: 9:16 크롭)"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.visual.reframe import (
    align_before_after_crop,
    apply_approved_reframe,
    compute_crop_window,
    render_crop_preview_image,
    render_static_crop,
    smooth_crop_path,
    zoom_limit_for_resolution,
    ReframePlan,
)
from capcut_auto.visual.subject_detection import BoundingBox
from capcut_auto.silence import get_video_resolution

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class TestZoomLimitForResolution(unittest.TestCase):
    def test_hd_gets_default_max_zoom(self):
        self.assertEqual(zoom_limit_for_resolution(1920, 1080), 1.35)

    def test_low_res_gets_reduced_zoom(self):
        self.assertLess(zoom_limit_for_resolution(640, 480), 1.35)

    def test_very_low_res_gets_near_no_zoom(self):
        self.assertLessEqual(zoom_limit_for_resolution(320, 240), 1.05)


class TestComputeCropWindow(unittest.TestCase):
    def test_no_subject_defaults_to_centered_full_height_crop(self):
        crop = compute_crop_window(1920, 1080, None)
        self.assertEqual(crop.zoom, 1.0)
        self.assertAlmostEqual(crop.height, 1080)
        self.assertTrue(crop.subject_fully_contained)

    def test_small_subject_gets_zoomed_in_but_capped_at_max_zoom(self):
        crop = compute_crop_window(1920, 1080, BoundingBox(900, 400, 20, 20), max_zoom=1.35)
        self.assertLessEqual(crop.zoom, 1.35)
        self.assertTrue(crop.subject_fully_contained)

    def test_subject_stays_within_crop_bounds(self):
        bbox = BoundingBox(900, 400, 100, 100)
        crop = compute_crop_window(1920, 1080, bbox)
        self.assertLessEqual(crop.x, bbox.x)
        self.assertGreaterEqual(crop.x + crop.width, bbox.x + bbox.width)
        self.assertLessEqual(crop.y, bbox.y)
        self.assertGreaterEqual(crop.y + crop.height, bbox.y + bbox.height)

    def test_large_subject_that_cannot_fit_is_honestly_flagged(self):
        # 피사체가 base crop 폭보다 훨씬 큰 경우 - max_zoom을 어겨서까지 다 담지 않는다
        huge_bbox = BoundingBox(0, 0, 1900, 100)
        crop = compute_crop_window(1920, 1080, huge_bbox, max_zoom=1.35)
        self.assertLessEqual(crop.zoom, 1.35)
        self.assertFalse(crop.subject_fully_contained)

    def test_crop_never_exceeds_frame_bounds(self):
        crop = compute_crop_window(1920, 1080, BoundingBox(1850, 1000, 50, 50))
        self.assertGreaterEqual(crop.x, 0)
        self.assertGreaterEqual(crop.y, 0)
        self.assertLessEqual(crop.x + crop.width, 1920 + 1e-6)
        self.assertLessEqual(crop.y + crop.height, 1080 + 1e-6)

    def test_does_not_zoom_in_when_subject_already_wide_enough(self):
        # 피사체 폭이 이미 base crop 폭(9:16 기준 약 607px)만큼 넓으면 확대하지 않는다(zoom==1.0)
        crop = compute_crop_window(1920, 1080, BoundingBox(710, 440, 500, 200))
        self.assertEqual(crop.zoom, 1.0)


class TestSmoothCropPath(unittest.TestCase):
    def test_limits_center_jump_between_frames(self):
        far_apart = [
            compute_crop_window(1920, 1080, BoundingBox(50, 400, 60, 60)),
            compute_crop_window(1920, 1080, BoundingBox(1800, 400, 60, 60)),
        ]
        smoothed = smooth_crop_path(far_apart, max_center_shift_ratio=0.05)
        raw_shift = abs(far_apart[1].center[0] - far_apart[0].center[0])
        smoothed_shift = abs(smoothed[1].center[0] - smoothed[0].center[0])
        self.assertLess(smoothed_shift, raw_shift)

    def test_limits_zoom_change_between_frames(self):
        windows = [
            compute_crop_window(1920, 1080, BoundingBox(900, 400, 500, 500)),  # zoom ~1.0
            compute_crop_window(1920, 1080, BoundingBox(900, 400, 20, 20)),  # zoom ~1.35
        ]
        smoothed = smooth_crop_path(windows, max_zoom_delta_per_step=0.05)
        self.assertLessEqual(abs(smoothed[1].zoom - smoothed[0].zoom), 0.05 + 1e-9)

    def test_empty_input_returns_empty(self):
        self.assertEqual(smooth_crop_path([]), [])

    def test_single_window_passthrough(self):
        crop = compute_crop_window(1920, 1080, BoundingBox(900, 400, 100, 100))
        self.assertEqual(smooth_crop_path([crop]), [crop])


class TestBeforeAfterAlignment(unittest.TestCase):
    def test_after_reuses_before_crop(self):
        before = compute_crop_window(1920, 1080, BoundingBox(200, 200, 100, 100))
        after = compute_crop_window(1920, 1080, BoundingBox(1600, 800, 100, 100))
        aligned_before, aligned_after = align_before_after_crop(before, after)
        self.assertEqual(aligned_before, before)
        self.assertEqual(aligned_after, before)


class TestApplyApprovedReframe(unittest.TestCase):
    """모든 화면 보정은 사용자 검토 후 적용한다."""

    def test_unapproved_plan_is_rejected(self):
        plan = ReframePlan(frame_times=[0.0], windows=[compute_crop_window(1920, 1080, None)], approved=False)
        self.assertIsNone(apply_approved_reframe(plan))

    def test_approved_plan_passes_through(self):
        plan = ReframePlan(frame_times=[0.0], windows=[compute_crop_window(1920, 1080, None)], approved=True)
        self.assertEqual(apply_approved_reframe(plan), plan)


def _make_synthetic_video(path: str, width=640, height=360, duration=2) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=10:duration={duration}", path],
        capture_output=True,
        text=True,
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestRenderStaticCropIntegration(unittest.TestCase):
    def test_renders_real_9x16_video_matching_target_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            _make_synthetic_video(video_path, width=640, height=360)
            width, height = get_video_resolution(video_path)
            crop = compute_crop_window(width, height, None)

            out_path = str(Path(tmp) / "out.mp4")
            render_static_crop(video_path, crop, out_path, target_width=360, target_height=640)

            self.assertTrue(Path(out_path).exists())
            out_width, out_height = get_video_resolution(out_path)
            self.assertEqual((out_width, out_height), (360, 640))

    def test_renders_real_preview_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            _make_synthetic_video(video_path, width=640, height=360)
            width, height = get_video_resolution(video_path)
            crop = compute_crop_window(width, height, None)

            out_path = str(Path(tmp) / "preview.jpg")
            render_crop_preview_image(video_path, crop, out_path, sample_time=0.5)

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestGetVideoResolutionIntegration(unittest.TestCase):
    def test_returns_real_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            _make_synthetic_video(video_path, width=640, height=360)
            self.assertEqual(get_video_resolution(video_path), (640, 360))


if __name__ == "__main__":
    unittest.main()
