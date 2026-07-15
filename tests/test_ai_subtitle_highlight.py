"""자막 강조(capcut_auto/ai/subtitle_highlight.py) 테스트.

테스트 시나리오 11: 강조 단어 검증.
"""

import json
import unittest

from capcut_auto.ai.subtitle_highlight import (
    SubtitleHighlightType,
    generate_highlights,
    validate_highlight,
)
from capcut_auto.ai.subtitle_optimizer import SubtitleLineWithId
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, noop_sleep


class TestValidateHighlight(unittest.TestCase):
    def test_word_present_in_text_is_valid(self):
        self.assertTrue(validate_highlight("10분", "이거 10분이면 끝나요"))

    def test_word_not_in_text_is_invalid(self):
        self.assertFalse(validate_highlight("30분", "이거 10분이면 끝나요"))

    def test_empty_word_is_invalid(self):
        self.assertFalse(validate_highlight("", "아무 텍스트"))


class TestGenerateHighlights(unittest.TestCase):
    def test_valid_highlight_is_kept(self):
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="이거 10분이면 끝나요")]
        response = {"lines": [{"id": "l1", "highlights": [{"word": "10분", "type": "DURATION"}]}]}
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = generate_highlights(lines, client=client, sleep_fn=noop_sleep)

        self.assertEqual(len(result["l1"]), 1)
        self.assertEqual(result["l1"][0].word, "10분")
        self.assertEqual(result["l1"][0].type, SubtitleHighlightType.DURATION)

    def test_hallucinated_word_not_in_subtitle_is_dropped(self):
        """AI가 실제 자막에 없는 단어를 강조로 지어내면 코드에서 걸러낸다."""
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="이거 10분이면 끝나요")]
        response = {
            "lines": [
                {
                    "id": "l1",
                    "highlights": [
                        {"word": "10분", "type": "DURATION"},
                        {"word": "3만원", "type": "PRICE"},  # 자막에 없는 단어 (환각)
                    ],
                }
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = generate_highlights(lines, client=client, sleep_fn=noop_sleep)

        words = [h.word for h in result["l1"]]
        self.assertIn("10분", words)
        self.assertNotIn("3만원", words)
        self.assertEqual(len(result["l1"]), 1)

    def test_at_most_two_highlights_per_line(self):
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="10분 3천원 리뷰 결과 완료")]
        response = {
            "lines": [
                {
                    "id": "l1",
                    "highlights": [
                        {"word": "10분", "type": "DURATION"},
                        {"word": "3천원", "type": "PRICE"},
                    ],
                }
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        result = generate_highlights(lines, client=client, sleep_fn=noop_sleep)
        self.assertLessEqual(len(result["l1"]), 2)


if __name__ == "__main__":
    unittest.main()
