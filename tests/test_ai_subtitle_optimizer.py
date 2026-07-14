"""자막 최적화(capcut_auto/ai/subtitle_optimizer.py) 테스트."""

import json
import unittest

from capcut_auto.ai.subtitle_optimizer import (
    SubtitleLineWithId,
    optimize_subtitles,
    validate_optimized_line,
)
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, noop_sleep


class TestValidateOptimizedLine(unittest.TestCase):
    def test_valid_line_passes(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="짧은 자막")
        self.assertIsNone(validate_optimized_line(line))

    def test_more_than_two_lines_fails(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="한\n두\n셋")
        self.assertIsNotNone(validate_optimized_line(line))

    def test_over_14_chars_per_line_fails(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="가" * 15)
        self.assertIsNotNone(validate_optimized_line(line))

    def test_lone_particle_line_fails(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="정리\n는")
        self.assertIsNotNone(validate_optimized_line(line))

    def test_number_unit_split_fails(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="10\n분이면 끝")
        self.assertIsNotNone(validate_optimized_line(line))

    def test_short_exposure_fails(self):
        line = SubtitleLineWithId(id="l1", start=0.0, end=0.3, text="너무 짧음")
        self.assertIsNotNone(validate_optimized_line(line))


class TestOptimizeSubtitles(unittest.TestCase):
    def test_valid_ai_output_is_used(self):
        original = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="원본 자막")]
        response = {"lines": [{"id": "l1", "start": 0.0, "end": 1.0, "text": "정리된 자막"}]}
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = optimize_subtitles(original, client=client, sleep_fn=noop_sleep)

        self.assertEqual(result[0].text, "정리된 자막")

    def test_line_violating_rules_falls_back_to_original_line_only(self):
        original = [
            SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="원본1"),
            SubtitleLineWithId(id="l2", start=2.0, end=3.0, text="원본2"),
        ]
        response = {
            "lines": [
                {"id": "l1", "start": 0.0, "end": 1.0, "text": "가" * 20},  # 규칙 위반(14자 초과)
                {"id": "l2", "start": 2.0, "end": 3.0, "text": "정상 자막"},
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = optimize_subtitles(original, client=client, sleep_fn=noop_sleep)

        by_id = {l.id: l for l in result}
        self.assertEqual(by_id["l1"].text, "원본1")  # 위반된 줄만 원본으로 폴백
        self.assertEqual(by_id["l2"].text, "정상 자막")  # 정상 줄은 AI 결과 사용

    def test_missing_line_in_ai_output_is_filled_from_original(self):
        original = [
            SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="원본1"),
            SubtitleLineWithId(id="l2", start=2.0, end=3.0, text="원본2"),
        ]
        response = {"lines": [{"id": "l1", "start": 0.0, "end": 1.0, "text": "정리1"}]}
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = optimize_subtitles(original, client=client, sleep_fn=noop_sleep)

        self.assertEqual(len(result), 2)
        by_id = {l.id: l for l in result}
        self.assertEqual(by_id["l2"].text, "원본2")

    def test_meaning_altering_overlap_falls_back_to_full_original(self):
        original = [
            SubtitleLineWithId(id="l1", start=0.0, end=2.0, text="원본1"),
            SubtitleLineWithId(id="l2", start=3.0, end=5.0, text="원본2"),
        ]
        # AI가 두 줄의 시간을 서로 겹치게 만들어버린 경우 (회복 불가능)
        response = {
            "lines": [
                {"id": "l1", "start": 0.0, "end": 4.0, "text": "겹침1"},
                {"id": "l2", "start": 3.0, "end": 5.0, "text": "겹침2"},
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = optimize_subtitles(original, client=client, sleep_fn=noop_sleep)

        self.assertEqual([l.text for l in result], ["원본1", "원본2"])


if __name__ == "__main__":
    unittest.main()
