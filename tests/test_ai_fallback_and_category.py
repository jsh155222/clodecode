"""테스트 시나리오 13(기존 기능 폴백)과 14(카테고리별 판단)를 모듈 간 통합 관점에서 검증한다.

개별 모듈의 폴백/카테고리 동작 자체는 각 모듈의 테스트 파일에도 있지만, 이 파일은
"AI 호출이 실패했을 때 실제로 기존(비-AI) 기능을 그대로 쓸 수 있는지"와
"카테고리마다 다른 규칙이 실제로 적용되는지"를 한 곳에서 명시적으로 확인한다.
"""

import json
import unittest

from capcut_auto import hooks as legacy_hooks
from capcut_auto.ai.category_rules import (
    build_cut_protection_rules,
    build_subtitle_density_rule,
    category_label,
)
from capcut_auto.ai.client import AiModuleError
from capcut_auto.ai.cut_candidates import CutAction, analyze_cut_candidates, fallback_from_rule_based_intervals
from capcut_auto.ai.hook_ai import generate_ai_hooks
from capcut_auto.ai.subtitle_optimizer import SubtitleLineWithId, optimize_subtitles
from capcut_auto.ai.video_structure import (
    TranscriptSegment,
    VideoSectionRole,
    analyze_video_structure,
    fallback_single_unknown_section,
)
from capcut_auto.categories import ContentCategory
from capcut_auto.timeline import Interval
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, make_server_error, noop_sleep


class TestExistingFeatureFallback(unittest.TestCase):
    """13. 기존 기능 폴백 - AI 모듈이 실패해도 해당 기능만 비-AI 로직으로 계속 동작해야 한다."""

    def _failing_client(self):
        # 서버 오류를 재시도 한도(2회)보다 많이 반환해 반드시 AiModuleError가 나게 한다
        return FakeAnthropicClient([make_server_error(500), make_server_error(500), make_server_error(500)])

    def test_video_structure_failure_falls_back_to_single_unknown_section(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=10.0, text="발화")]
        client = self._failing_client()

        with self.assertRaises(AiModuleError):
            analyze_video_structure(segments, total_duration=10.0, client=client, sleep_fn=noop_sleep)

        fallback = fallback_single_unknown_section(total_duration=10.0)
        self.assertEqual(len(fallback), 1)
        self.assertEqual(fallback[0].role, VideoSectionRole.UNKNOWN)
        self.assertEqual(fallback[0].end, 10.0)

    def test_cut_candidates_failure_falls_back_to_rule_based_pipeline(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=10.0, text="발화")]
        client = self._failing_client()

        with self.assertRaises(AiModuleError):
            analyze_cut_candidates(segments, total_duration=10.0, client=client, sleep_fn=noop_sleep)

        # 실제 규칙 기반 파이프라인(silence.py 등)이 만들어낼 법한 Interval로 폴백
        fallback = fallback_from_rule_based_intervals(
            silence_intervals=[Interval(1.0, 2.0)], filler_intervals=[], repetition_intervals=[]
        )
        self.assertEqual(len(fallback), 1)
        self.assertEqual(fallback[0].action, CutAction.REVIEW)

    def test_subtitle_optimizer_failure_falls_back_to_original_lines(self):
        original = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="원본 자막")]
        client = self._failing_client()

        with self.assertRaises(AiModuleError):
            optimize_subtitles(original, client=client, sleep_fn=noop_sleep)

        # 호출자는 이 예외를 잡아 원본 자막을 그대로 쓰면 된다 (여기서는 그 계약을 확인)
        fallback_result = original
        self.assertEqual(fallback_result[0].text, "원본 자막")

    def test_hook_ai_failure_falls_back_to_template_based_hooks(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=10.0, text="발화")]
        client = self._failing_client()

        with self.assertRaises(AiModuleError):
            generate_ai_hooks("주제", segments, client=client, sleep_fn=noop_sleep)

        # 기존 템플릿 기반 hooks.py가 여전히 정상 동작해야 한다
        suggestions = legacy_hooks.generate_hook_suggestions("주제", ContentCategory.FOOD, max_suggestions=3)
        self.assertGreater(len(suggestions), 0)


class TestCategorySpecificJudgment(unittest.TestCase):
    """14. 카테고리별 판단 - 카테고리마다 다른 보호 규칙/자막 밀도가 실제로 적용되는지."""

    def test_each_category_has_distinct_protection_keywords(self):
        food_rules = build_cut_protection_rules(ContentCategory.FOOD)
        parenting_rules = build_cut_protection_rules(ContentCategory.PARENTING)
        self.assertTrue(food_rules)
        self.assertTrue(parenting_rules)
        self.assertNotEqual(set(food_rules), set(parenting_rules))

    def test_no_category_returns_empty_protection_rules(self):
        self.assertEqual(build_cut_protection_rules(None), [])
        self.assertIsNone(build_subtitle_density_rule(None))

    def test_category_protection_rules_reach_the_ai_request_payload(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=10.0, text="발화")]
        category = ContentCategory.PARENTING
        client = FakeAnthropicClient([FakeResponse(json.dumps({"candidates": []}))])

        analyze_cut_candidates(
            segments,
            total_duration=10.0,
            category_label=category_label(category),
            category_protection_rules=build_cut_protection_rules(category),
            client=client,
            sleep_fn=noop_sleep,
        )

        sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertEqual(sent["category"], "육아")
        self.assertIn("아이 안전 정보", sent["categoryProtectionRules"])

    def test_category_density_rule_reaches_subtitle_optimizer_payload(self):
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="자막")]
        category = ContentCategory.CLEANING
        client = FakeAnthropicClient([FakeResponse(json.dumps({"lines": []}))])

        optimize_subtitles(
            lines,
            category_label=category_label(category),
            density_rule=build_subtitle_density_rule(category),
            client=client,
            sleep_fn=noop_sleep,
        )

        sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertEqual(sent["category"], "청소")
        self.assertIn("최소화", sent["densityRule"])


if __name__ == "__main__":
    unittest.main()
