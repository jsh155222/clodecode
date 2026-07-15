"""컷 후보 분석(capcut_auto/ai/cut_candidates.py) 테스트.

테스트 시나리오 5: 컷 후보 / 6: 보호 구간 충돌 / 13: 기존 기능 폴백(일부) / 14: 카테고리별 판단(일부).
"""

import json
import unittest

from capcut_auto.ai.cut_candidates import (
    CutAction,
    CutCandidate,
    ProtectedInterval,
    analyze_cut_candidates,
    approved_cut_intervals,
    fallback_from_rule_based_intervals,
    meets_auto_apply_criteria,
    review_candidates,
)
from capcut_auto.ai.video_structure import TranscriptSegment
from capcut_auto.timeline import Interval
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, noop_sleep


def _candidate(**overrides) -> CutCandidate:
    base = dict(
        id="c1",
        start=1.0,
        end=2.0,
        action=CutAction.REVIEW,
        reason_code="long_silence",
        reason="무음 구간",
        confidence=0.95,
        context_risk=0.1,
        estimated_time_saved=1.0,
    )
    base.update(overrides)
    return CutCandidate(**base)


class TestAnalyzeCutCandidates(unittest.TestCase):
    """5. 컷 후보 분석"""

    def test_parses_candidates_from_ai_response(self):
        response_body = {
            "candidates": [
                {
                    "start": 3.0,
                    "end": 4.5,
                    "action": "AUTO_CUT",
                    "reasonCode": "long_silence",
                    "reason": "3초 무음",
                    "confidence": 0.97,
                    "contextRisk": 0.05,
                }
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response_body))])
        segments = [TranscriptSegment(id="s1", start=0.0, end=5.0, text="테스트 발화")]

        result = analyze_cut_candidates(segments, total_duration=5.0, client=client, sleep_fn=noop_sleep)

        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.start, 3.0)
        self.assertEqual(candidate.end, 4.5)
        self.assertEqual(candidate.action, CutAction.AUTO_CUT)
        self.assertAlmostEqual(candidate.estimated_time_saved, 1.5)
        self.assertTrue(candidate.id)  # 코드에서 id를 부여함

    def test_category_protection_rules_are_sent_in_request(self):
        response_body = {"candidates": []}
        client = FakeAnthropicClient([FakeResponse(json.dumps(response_body))])
        segments = [TranscriptSegment(id="s1", start=0.0, end=5.0, text="발화")]

        analyze_cut_candidates(
            segments,
            total_duration=5.0,
            category_label="음식",
            category_protection_rules=["레시피 계량/순서", "완성 결과물"],
            client=client,
            sleep_fn=noop_sleep,
        )

        sent_content = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertEqual(sent_content["category"], "음식")
        self.assertIn("완성 결과물", sent_content["categoryProtectionRules"])


class TestAutoApplyCriteria(unittest.TestCase):
    """6. 보호 구간 충돌"""

    def test_high_confidence_low_risk_meets_criteria(self):
        candidate = _candidate(confidence=0.95, context_risk=0.1)
        self.assertTrue(meets_auto_apply_criteria(candidate, protected_intervals=[]))

    def test_low_confidence_fails_criteria(self):
        candidate = _candidate(confidence=0.5, context_risk=0.1)
        self.assertFalse(meets_auto_apply_criteria(candidate, protected_intervals=[]))

    def test_high_context_risk_fails_criteria(self):
        candidate = _candidate(confidence=0.99, context_risk=0.9)
        self.assertFalse(meets_auto_apply_criteria(candidate, protected_intervals=[]))

    def test_overlap_with_protected_interval_fails_criteria(self):
        candidate = _candidate(start=1.0, end=2.0, confidence=0.99, context_risk=0.0)
        protected = [ProtectedInterval(start=1.5, end=3.0, reason="key_procedure")]
        self.assertFalse(meets_auto_apply_criteria(candidate, protected_intervals=protected))

    def test_non_overlapping_protected_interval_still_meets_criteria(self):
        candidate = _candidate(start=1.0, end=2.0, confidence=0.99, context_risk=0.0)
        protected = [ProtectedInterval(start=10.0, end=12.0, reason="key_procedure")]
        self.assertTrue(meets_auto_apply_criteria(candidate, protected_intervals=protected))


class TestFallbackFromRuleBased(unittest.TestCase):
    """13. 기존 기능 폴백 (컷 후보 분석 AI 실패 시 기존 규칙 기반 파이프라인으로)"""

    def test_converts_rule_based_intervals_to_review_candidates(self):
        silence = [Interval(1.0, 2.0)]
        filler = [Interval(5.0, 5.3)]
        repetition = [Interval(8.0, 8.5)]

        result = fallback_from_rule_based_intervals(silence, filler, repetition)

        self.assertEqual(len(result), 3)
        self.assertTrue(all(c.action == CutAction.REVIEW for c in result))
        self.assertTrue(all(c.confidence == 0.5 and c.context_risk == 0.5 for c in result))
        reason_codes = {c.reason_code for c in result}
        self.assertEqual(reason_codes, {"long_silence", "meaningless_filler", "repeated_utterance"})
        # 시작 시각 순으로 정렬됨
        self.assertEqual([round(c.start, 1) for c in result], [1.0, 5.0, 8.0])


class TestReviewAndApprove(unittest.TestCase):
    """5. 사용자 컷 검토 (+ 승인된 컷만 적용 엔진으로 전달)"""

    def test_review_overrides_action_for_decided_candidates_only(self):
        candidates = [
            _candidate(id="c1", action=CutAction.REVIEW),
            _candidate(id="c2", action=CutAction.REVIEW),
        ]
        reviewed = review_candidates(candidates, decisions={"c1": CutAction.AUTO_CUT})

        by_id = {c.id: c for c in reviewed}
        self.assertEqual(by_id["c1"].action, CutAction.AUTO_CUT)
        self.assertEqual(by_id["c2"].action, CutAction.REVIEW)  # 결정 안 한 후보는 그대로

    def test_only_explicitly_approved_candidates_become_apply_intervals(self):
        candidates = [
            _candidate(id="c1", start=1.0, end=2.0, action=CutAction.REVIEW),
            _candidate(id="c2", start=5.0, end=6.0, action=CutAction.REVIEW),
            _candidate(id="c3", start=8.0, end=9.0, action=CutAction.KEEP),
        ]
        # 사용자가 c1만 승인, c2는 보류(결정 안 함), c3는 애초에 KEEP으로 결정
        decisions = {"c1": CutAction.AUTO_CUT, "c3": CutAction.KEEP}
        reviewed = review_candidates(candidates, decisions=decisions)

        intervals = approved_cut_intervals(reviewed, decisions=decisions)

        self.assertEqual(intervals, [Interval(1.0, 2.0)])

    def test_ai_assigned_auto_cut_without_user_review_is_not_applied(self):
        """AI가 처음부터 AUTO_CUT으로 매겨도, 사용자가 검토(decisions에 명시적으로
        AUTO_CUT을 기록)하지 않는 한 절대 적용되지 않는다는 초기 버전 정책을 검증한다.
        """
        candidates = [_candidate(id="c1", start=1.0, end=2.0, action=CutAction.AUTO_CUT)]

        # 사용자가 아직 아무 결정도 내리지 않음(decisions가 비어 있음)
        intervals = approved_cut_intervals(candidates, decisions={})

        self.assertEqual(intervals, [])


if __name__ == "__main__":
    unittest.main()
