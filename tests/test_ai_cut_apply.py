"""컷 적용 엔진(capcut_auto/ai/cut_apply.py) 테스트.

테스트 시나리오 7: 승인 컷 적용 / 8: 원상복구.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.ai.cut_apply import (
    EditHistory,
    apply_approved_cuts,
    clip_to_video_range,
    render_crossfade_preview,
    snap_to_word_boundaries,
)
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class TestClipToVideoRange(unittest.TestCase):
    def test_removes_out_of_range_time(self):
        result = clip_to_video_range([Interval(-2.0, 3.0), Interval(8.0, 20.0)], total_duration=10.0)
        self.assertEqual(result, [Interval(0.0, 3.0), Interval(8.0, 10.0)])

    def test_drops_interval_entirely_outside_range(self):
        result = clip_to_video_range([Interval(15.0, 20.0)], total_duration=10.0)
        self.assertEqual(result, [])


class TestSnapToWordBoundaries(unittest.TestCase):
    def test_snaps_cut_boundary_to_nearer_word_edge(self):
        words = [Word(2.0, 3.0, "안녕")]
        # 2.9는 단어 끝(3.0)에 더 가까움 -> 3.0으로 스냅
        result = snap_to_word_boundaries([Interval(2.9, 5.0)], words)
        self.assertEqual(result[0].start, 3.0)

    def test_snaps_to_word_start_when_closer(self):
        words = [Word(2.0, 3.0, "안녕")]
        # 2.1은 단어 시작(2.0)에 더 가까움 -> 2.0으로 스냅
        result = snap_to_word_boundaries([Interval(2.1, 5.0)], words)
        self.assertEqual(result[0].start, 2.0)

    def test_leaves_boundary_outside_any_word_unchanged(self):
        words = [Word(2.0, 3.0, "안녕")]
        result = snap_to_word_boundaries([Interval(5.0, 6.0)], words)
        self.assertEqual(result[0].start, 5.0)


class TestApplyApprovedCuts(unittest.TestCase):
    """7. 승인 컷 적용"""

    def test_merges_overlapping_cuts_and_computes_keep_intervals(self):
        result = apply_approved_cuts(
            total_duration=10.0,
            approved_cut_intervals=[Interval(1.0, 3.0), Interval(2.5, 4.0)],
        )
        # 겹치는 (1,3)과 (2.5,4)가 (1,4)로 병합되어야 함
        self.assertEqual(result.keep_intervals, [Interval(0.0, 1.0), Interval(4.0, 10.0)])
        self.assertAlmostEqual(result.kept_duration, 7.0)

    def test_before_after_preview_info_is_included(self):
        previous_keep = [Interval(0.0, 10.0)]
        result = apply_approved_cuts(
            total_duration=10.0,
            approved_cut_intervals=[Interval(1.0, 2.0)],
            previous_keep_intervals=previous_keep,
        )
        self.assertAlmostEqual(result.previous_kept_duration, 10.0)
        self.assertAlmostEqual(result.kept_duration, 9.0)

    def test_word_boundaries_are_respected_when_words_given(self):
        words = [Word(1.8, 2.2, "테스트")]
        result = apply_approved_cuts(
            total_duration=10.0,
            approved_cut_intervals=[Interval(2.0, 3.0)],  # 2.0은 단어 중간
            words=words,
        )
        # 컷 시작이 단어 시작(1.8)으로 스냅되어 keep_intervals 경계에도 반영됨
        self.assertNotIn(Interval(0.0, 2.0), result.keep_intervals)


class TestEditHistory(unittest.TestCase):
    """8. 원상복구"""

    def test_undo_restores_previous_state(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 10.0)])
        history.push([Interval(0.0, 5.0)], "cut 1")
        history.push([Interval(0.0, 3.0)], "cut 2")

        self.assertEqual(history.current, [Interval(0.0, 3.0)])
        self.assertTrue(history.undo())
        self.assertEqual(history.current, [Interval(0.0, 5.0)])
        self.assertTrue(history.undo())
        self.assertEqual(history.current, [Interval(0.0, 10.0)])
        self.assertFalse(history.undo())  # 더 이상 되돌릴 게 없음

    def test_redo_reapplies_undone_state(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 10.0)])
        history.push([Interval(0.0, 5.0)], "cut 1")
        history.undo()
        self.assertTrue(history.redo())
        self.assertEqual(history.current, [Interval(0.0, 5.0)])
        self.assertFalse(history.redo())

    def test_new_edit_after_undo_discards_redo_history(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 10.0)])
        history.push([Interval(0.0, 5.0)], "cut 1")
        history.undo()
        history.push([Interval(0.0, 7.0)], "different cut")
        self.assertFalse(history.can_redo)
        self.assertEqual(history.current, [Interval(0.0, 7.0)])

    def test_revert_to_original_clears_all_edits(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 10.0)])
        history.push([Interval(0.0, 5.0)], "cut 1")
        history.push([Interval(0.0, 3.0)], "cut 2")
        history.revert_to_original()
        self.assertEqual(history.current, [Interval(0.0, 10.0)])
        self.assertFalse(history.can_undo)
        self.assertFalse(history.can_redo)


def _make_synthetic_video(path: str, duration: int = 6) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=160x120:rate=10:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestRenderCrossfadePreviewIntegration(unittest.TestCase):
    """7. 승인 컷 적용 (실제 ffmpeg로 오디오 크로스페이드 미리보기 렌더링 검증)"""

    def test_renders_preview_with_correct_total_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            _make_synthetic_video(video_path, duration=6)
            output_path = str(Path(tmp) / "preview.mp4")

            keep_intervals = [Interval(0.0, 2.0), Interval(3.0, 6.0)]
            render_crossfade_preview(video_path, keep_intervals, output_path, crossfade_seconds=0.15)

            self.assertTrue(Path(output_path).exists())
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output_path],
                capture_output=True,
                text=True,
                check=True,
            )
            duration = float(probe.stdout.strip())
            # 크로스페이드는 각 클립 내부에서 페이드만 걸 뿐 길이를 바꾸지 않으므로
            # 총 길이는 keep 구간 합(5초)과 거의 같아야 한다 (인코딩 오차 허용)
            self.assertAlmostEqual(duration, 5.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
