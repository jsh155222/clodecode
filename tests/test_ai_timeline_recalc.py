"""타임라인 재계산(capcut_auto/ai/timeline_recalc.py) 테스트.

테스트 시나리오 9: 타임라인 재계산 / 10: 자막 재매핑.
"""

import unittest

from capcut_auto.ai.timeline_recalc import (
    recalculate_hook_range,
    recalculate_sections,
    recalculate_subtitle_lines,
    recalculate_timeline,
)
from capcut_auto.ai.video_structure import VideoSection, VideoSectionRole
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word


class TestRecalculateSubtitleLines(unittest.TestCase):
    """10. 자막 재매핑"""

    def test_words_before_cut_are_shifted_correctly(self):
        # 원본: [단어1: 0~1] [컷: 1~3] [단어2: 3~4]
        words = [Word(0.0, 1.0, "안녕"), Word(3.0, 4.0, "하세요")]
        keep_intervals = [Interval(0.0, 1.0), Interval(3.0, 4.0)]  # 컷(1~3) 반영된 남길 구간

        lines = recalculate_subtitle_lines(words, keep_intervals, max_chars=100)

        # 두 단어의 gap이 새 타임라인에서는 0이 되어 한 줄로 합쳐짐 (같은 문장)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "안녕 하세요")
        self.assertAlmostEqual(lines[0].start, 0.0)
        self.assertAlmostEqual(lines[0].end, 2.0)  # 1초 + 1초(컷 구간 제거됨)

    def test_word_fully_inside_cut_is_dropped(self):
        words = [Word(0.0, 1.0, "유지"), Word(1.5, 2.0, "삭제됨"), Word(5.0, 6.0, "유지2")]
        keep_intervals = [Interval(0.0, 1.0), Interval(5.0, 6.0)]

        lines = recalculate_subtitle_lines(words, keep_intervals, max_chars=100)
        joined_text = " ".join(l.text for l in lines)
        self.assertNotIn("삭제됨", joined_text)


class TestRecalculateSections(unittest.TestCase):
    """9. 타임라인 재계산 (장면 구간)"""

    def test_section_boundaries_are_remapped(self):
        sections = [VideoSection(start=0.0, end=5.0, role=VideoSectionRole.HOOK, summary="")]
        keep_intervals = [Interval(0.0, 2.0), Interval(4.0, 5.0)]  # 2~4초가 컷됨

        result = recalculate_sections(sections, keep_intervals)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].start, 0.0)
        self.assertAlmostEqual(result[0].end, 3.0)  # (0~2) + (4~5) = 3초

    def test_section_fully_cut_is_dropped_or_snapped(self):
        sections = [VideoSection(start=10.0, end=12.0, role=VideoSectionRole.TRANSITION, summary="")]
        keep_intervals = [Interval(0.0, 5.0)]  # 10~12초는 완전히 컷됨

        result = recalculate_sections(sections, keep_intervals)
        # 경계가 가장 가까운 유효 지점(5.0)으로 스냅되어 start==end가 되므로 제거됨
        self.assertEqual(result, [])


class TestRecalculateHookRange(unittest.TestCase):
    def test_hook_keeps_its_duration_at_timeline_start(self):
        result = recalculate_hook_range(Interval(0.0, 2.5), keep_intervals=[Interval(0.0, 10.0)])
        self.assertEqual(result, Interval(0.0, 2.5))

    def test_none_hook_stays_none(self):
        self.assertIsNone(recalculate_hook_range(None, keep_intervals=[Interval(0.0, 10.0)]))


class TestRecalculateTimelineFullPipeline(unittest.TestCase):
    """9. 타임라인 재계산 (전체 파이프라인 성공/실패 경로)"""

    def test_successful_recalculation(self):
        words = [Word(0.0, 1.0, "안녕"), Word(2.0, 3.0, "하세요")]
        keep_intervals = [Interval(0.0, 1.0), Interval(2.0, 3.0)]
        sections = [VideoSection(start=0.0, end=3.0, role=VideoSectionRole.HOOK, summary="")]
        hook = Interval(0.0, 2.0)

        result = recalculate_timeline(words, keep_intervals, sections, hook)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.words), 2)
        self.assertEqual(len(result.subtitle_lines), 1)
        self.assertEqual(len(result.sections), 1)
        self.assertEqual(result.hook_range, Interval(0.0, 2.0))

    def test_failure_returns_success_false_and_preserves_originals_for_revert(self):
        words = [Word(0.0, 1.0, "테스트")]
        # keep_intervals가 완전히 잘못됨(비어 있음) -> group_words_into_lines 자체는 안 죽지만,
        # 겹치는 자막을 강제로 만들어 실패 경로를 검증한다.
        original_sections = [VideoSection(start=0.0, end=1.0, role=VideoSectionRole.HOOK, summary="")]

        # words에 억지로 겹치는 시간(동일 위치)을 둘 이상 넣어 group 결과가 겹치도록 유도하기보다,
        # 직접 실패를 일으키기 위해 존재하지 않는 keep_intervals 타입을 넘겨 예외를 검증한다.
        result = recalculate_timeline(words, keep_intervals="잘못된 타입", sections=original_sections)  # type: ignore[arg-type]

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        # 실패 시 원본 sections를 그대로 보존해 EditHistory.revert 등으로 되돌릴 수 있게 한다
        self.assertEqual(result.sections, original_sections)


if __name__ == "__main__":
    unittest.main()
