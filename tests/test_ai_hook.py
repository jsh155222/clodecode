"""AI 훅 생성(capcut_auto/ai/hook_ai.py) 테스트.

테스트 시나리오 12: 훅 근거 검증.
"""

import json
import unittest

from capcut_auto.ai.hook_ai import HookCandidate, HookType, generate_ai_hooks, validate_hook_grounding
from capcut_auto.ai.video_structure import TranscriptSegment
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, noop_sleep


def _hooks_response(hooks: list) -> str:
    return json.dumps({"hooks": hooks})


class TestValidateHookGrounding(unittest.TestCase):
    def test_hook_with_real_segment_ids_is_valid(self):
        hook = HookCandidate(text="훅", type=HookType.PROBLEM, evidence_segment_ids=["s1"], exaggeration_risk=0.1)
        self.assertTrue(validate_hook_grounding(hook, valid_segment_ids={"s1", "s2"}))

    def test_hook_with_fabricated_segment_id_is_invalid(self):
        hook = HookCandidate(text="훅", type=HookType.PROBLEM, evidence_segment_ids=["s99"], exaggeration_risk=0.1)
        self.assertFalse(validate_hook_grounding(hook, valid_segment_ids={"s1", "s2"}))

    def test_hook_with_no_evidence_is_invalid(self):
        hook = HookCandidate(text="훅", type=HookType.PROBLEM, evidence_segment_ids=[], exaggeration_risk=0.1)
        self.assertFalse(validate_hook_grounding(hook, valid_segment_ids={"s1"}))


class TestGenerateAiHooks(unittest.TestCase):
    def test_returns_grounded_hooks(self):
        segments = [
            TranscriptSegment(id="s1", start=0.0, end=2.0, text="문제 상황"),
            TranscriptSegment(id="s2", start=2.0, end=5.0, text="해결 과정"),
        ]
        response = _hooks_response(
            [
                {
                    "text": "이거 안 하면 큰일나요",
                    "type": "PROBLEM",
                    "evidenceSegmentIds": ["s1"],
                    "exaggerationRisk": 0.1,
                },
                {
                    "text": "이렇게 해결했어요",
                    "type": "RESULT_FIRST",
                    "evidenceSegmentIds": ["s2"],
                    "exaggerationRisk": 0.15,
                },
                {
                    "text": "궁금하지 않으세요?",
                    "type": "CURIOSITY",
                    "evidenceSegmentIds": ["s1", "s2"],
                    "exaggerationRisk": 0.2,
                },
            ]
        )
        client = FakeAnthropicClient([FakeResponse(response)])

        result = generate_ai_hooks("주제", segments, client=client, sleep_fn=noop_sleep)

        self.assertEqual(len(result), 3)

    def test_hook_referencing_nonexistent_segment_is_dropped(self):
        """근거 segment ID가 실제로 존재하지 않으면 코드에서 걸러내야 한다."""
        segments = [TranscriptSegment(id="s1", start=0.0, end=2.0, text="실제 발화")]
        response = _hooks_response(
            [
                {
                    "text": "진짜 근거 있는 훅",
                    "type": "PROBLEM",
                    "evidenceSegmentIds": ["s1"],
                    "exaggerationRisk": 0.1,
                },
                {
                    "text": "지어낸 근거의 훅",
                    "type": "LOSS",
                    "evidenceSegmentIds": ["s999"],  # 존재하지 않는 segment id
                    "exaggerationRisk": 0.05,
                },
                {
                    "text": "또 다른 진짜 훅",
                    "type": "QUESTION",
                    "evidenceSegmentIds": ["s1"],
                    "exaggerationRisk": 0.1,
                },
            ]
        )
        client = FakeAnthropicClient([FakeResponse(response)])

        result = generate_ai_hooks("주제", segments, client=client, sleep_fn=noop_sleep)

        texts = [h.text for h in result]
        self.assertIn("진짜 근거 있는 훅", texts)
        self.assertIn("또 다른 진짜 훅", texts)
        self.assertNotIn("지어낸 근거의 훅", texts)


if __name__ == "__main__":
    unittest.main()
