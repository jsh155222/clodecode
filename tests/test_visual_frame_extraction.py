"""대표 프레임 추출(capcut_auto/visual/frame_extraction.py) 테스트.

merge_and_space_trigger_times는 순수 함수 - 곧바로 검증. 실제 프레임 추출은 real ffmpeg
통합 테스트(skipUnless)로 검증한다.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.ai.video_structure import VideoSection, VideoSectionRole
from capcut_auto.subtitles import SubtitleLine
from capcut_auto.visual.frame_extraction import (
    FrameCandidateTime,
    FrameTrigger,
    derive_semantic_triggers_from_sections,
    extract_representative_frames,
    merge_and_space_trigger_times,
    sentence_start_times,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class TestSentenceStartTimes(unittest.TestCase):
    def test_extracts_line_start_times(self):
        lines = [SubtitleLine(0.0, 1.0, "안녕"), SubtitleLine(2.0, 3.0, "하세요")]
        self.assertEqual(sentence_start_times(lines), [0.0, 2.0])


class TestDeriveSemanticTriggersFromSections(unittest.TestCase):
    def test_result_section_becomes_result_reveal_trigger(self):
        sections = [VideoSection(0.0, 5.0, VideoSectionRole.PROCESS, ""), VideoSection(5.0, 8.0, VideoSectionRole.RESULT, "")]
        triggers = derive_semantic_triggers_from_sections(sections)
        self.assertIn(5.0, triggers[FrameTrigger.RESULT_REVEAL])

    def test_process_to_result_transition_becomes_before_after_trigger(self):
        sections = [VideoSection(0.0, 5.0, VideoSectionRole.PROCESS, ""), VideoSection(5.0, 8.0, VideoSectionRole.RESULT, "")]
        triggers = derive_semantic_triggers_from_sections(sections)
        self.assertIn(5.0, triggers[FrameTrigger.BEFORE_AFTER])

    def test_unrelated_role_transition_has_no_semantic_trigger(self):
        sections = [VideoSection(0.0, 5.0, VideoSectionRole.HOOK, ""), VideoSection(5.0, 8.0, VideoSectionRole.PROBLEM, "")]
        triggers = derive_semantic_triggers_from_sections(sections)
        self.assertEqual(triggers[FrameTrigger.RESULT_REVEAL], [])
        self.assertEqual(triggers[FrameTrigger.BEFORE_AFTER], [])


class TestMergeAndSpaceTriggerTimes(unittest.TestCase):
    def test_close_triggers_within_min_gap_are_deduplicated(self):
        triggers = [
            FrameCandidateTime(1.0, FrameTrigger.SCENE_CHANGE),
            FrameCandidateTime(1.2, FrameTrigger.SENTENCE_START),  # min_gap=0.5보다 가까움
        ]
        result = merge_and_space_trigger_times(triggers, total_duration=5.0, min_gap=0.5, max_gap=1.0)
        self.assertEqual([round(t.time, 3) for t in result], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result[0].trigger, FrameTrigger.SCENE_CHANGE)
        self.assertTrue(all(t.trigger == FrameTrigger.INTERVAL for t in result[1:]))

    def test_gaps_larger_than_max_gap_get_filled_with_interval(self):
        triggers = [FrameCandidateTime(0.0, FrameTrigger.SCENE_CHANGE)]
        result = merge_and_space_trigger_times(triggers, total_duration=3.0, min_gap=0.5, max_gap=1.0)
        interval_times = [t.time for t in result if t.trigger == FrameTrigger.INTERVAL]
        self.assertEqual(interval_times, [1.0, 2.0])

    def test_no_triggers_still_fills_with_interval(self):
        result = merge_and_space_trigger_times([], total_duration=2.5, min_gap=0.5, max_gap=1.0)
        self.assertTrue(all(t.trigger == FrameTrigger.INTERVAL for t in result))
        self.assertEqual([t.time for t in result], [1.0, 2.0])

    def test_out_of_range_times_are_dropped(self):
        triggers = [FrameCandidateTime(-1.0, FrameTrigger.SCENE_CHANGE), FrameCandidateTime(99.0, FrameTrigger.SCENE_CHANGE)]
        result = merge_and_space_trigger_times(triggers, total_duration=5.0, min_gap=0.5, max_gap=1.0)
        self.assertTrue(all(0.0 <= t.time <= 5.0 for t in result))

    def test_invalid_gap_arguments_raise(self):
        with self.assertRaises(ValueError):
            merge_and_space_trigger_times([], total_duration=5.0, min_gap=1.0, max_gap=0.5)


def _make_synthetic_video_with_scene_change(path: str) -> None:
    """전반부는 빨간 화면, 후반부는 파란 화면 - 뚜렷한 장면전환 하나."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x240:d=2:r=10",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=2:r=10",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestExtractRepresentativeFramesIntegration(unittest.TestCase):
    def test_extracts_real_jpg_frames_at_detected_scene_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            _make_synthetic_video_with_scene_change(video_path)
            output_dir = str(Path(tmp) / "frames")

            frames = extract_representative_frames(
                video_path,
                output_dir,
                total_duration=4.0,
                min_gap=0.5,
                max_gap=1.0,
            )

            self.assertGreater(len(frames), 0)
            for frame in frames:
                self.assertTrue(Path(frame.path).exists())
                self.assertGreater(Path(frame.path).stat().st_size, 0)

            triggers_seen = {f.trigger for f in frames}
            self.assertIn(FrameTrigger.SCENE_CHANGE, triggers_seen)
            # 장면전환이 약 2초 지점에서 감지되어야 함
            scene_change_times = [f.time for f in frames if f.trigger == FrameTrigger.SCENE_CHANGE]
            self.assertTrue(any(1.5 <= t <= 2.5 for t in scene_change_times))


if __name__ == "__main__":
    unittest.main()
