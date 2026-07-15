"""카테고리별 규칙(category-rules/*.json + capcut_auto/category_rules.py) 테스트.

요청된 10개 테스트 항목을 각각의 TestCase로 구성한다:
1. 보호 구간  2. 삭제 후보  3. 자막 밀도  4. 훅 생성  5. 자연음 보호
6. 화면 구도  7. 효과음 제한  8. 안전 규칙  9. 기존 공통 편집 엔진 정상 작동
10. 다른 카테고리 규칙이 섞이지 않는지
"""

import json
import tempfile
import unittest
from pathlib import Path

from capcut_auto.categories import ContentCategory
from capcut_auto.category_rules import (
    CategoryRuleSet,
    load_all_category_rule_sets,
    load_category_rule_set,
    load_common_rules,
    sfx_allowed,
)
from capcut_auto.ai.category_rules import (
    build_cut_protection_rules,
    build_discouraged_sound_effects,
    build_preferred_pacing,
    build_preferred_shot_types,
    build_preserve_natural_audio,
    build_removable_moment_hints,
    build_safety_checks,
    build_shooting_guide_rules,
    build_subtitle_density_rule,
    category_label,
)
from capcut_auto.ai.cut_candidates import TranscriptSegment, analyze_cut_candidates
from capcut_auto.ai.hook_ai import generate_ai_hooks
from capcut_auto.ai.subtitle_optimizer import SubtitleLineWithId, optimize_subtitles
from tests.ai_test_helpers import FakeAnthropicClient, FakeResponse, noop_sleep

ALL_CATEGORIES = list(ContentCategory)


class TestLoader(unittest.TestCase):
    def test_all_seven_categories_load_without_error(self):
        rules = load_all_category_rule_sets()
        self.assertEqual(set(rules.keys()), set(ALL_CATEGORIES))
        for category, rule_set in rules.items():
            self.assertIsInstance(rule_set, CategoryRuleSet)
            self.assertEqual(rule_set.category, category)

    def test_common_rules_file_has_seven_items(self):
        common = load_common_rules()
        self.assertEqual(len(common), 7)
        self.assertIn("안전 정보 삭제 금지", common)
        self.assertIn("모든 자동 편집은 되돌릴 수 있어야 함", common)

    def test_missing_category_file_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_category_rule_set(ContentCategory.FOOD, rules_dir=Path(tmp))

    def test_malformed_file_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "food.json"
            path.write_text(json.dumps({"category": "FOOD"}), encoding="utf-8")  # 필드 대부분 누락
            with self.assertRaises(ValueError):
                load_category_rule_set(ContentCategory.FOOD, rules_dir=Path(tmp))

    def test_invalid_pacing_value_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {
                "category": "FOOD",
                "protectedMoments": [],
                "removableMoments": [],
                "preferredPacing": "SUPER_FAST",  # 잘못된 값
                "subtitleDensity": "HIGH",
                "preserveNaturalAudio": True,
                "preferredShotTypes": [],
                "discouragedSoundEffects": [],
                "safetyChecks": [],
                "shootingGuideRules": [],
            }
            path = Path(tmp) / "food.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_category_rule_set(ContentCategory.FOOD, rules_dir=Path(tmp))


class TestProtectedMoments(unittest.TestCase):
    """1. 보호 구간"""

    def test_every_category_has_nonempty_protected_moments(self):
        for category in ALL_CATEGORIES:
            with self.subTest(category=category):
                rule_set = load_category_rule_set(category)
                self.assertGreater(len(rule_set.protected_moments), 0)

    def test_food_protects_cooking_sounds_and_safety_info(self):
        rule_set = load_category_rule_set(ContentCategory.FOOD)
        for moment in ["지글거리는 소리", "칼질", "조리 안전 정보", "완성 음식"]:
            self.assertIn(moment, rule_set.protected_moments)

    def test_camping_protects_fire_and_safety(self):
        rule_set = load_category_rule_set(ContentCategory.CAMPING)
        for moment in ["안전 정보", "불 사용 장면", "장비 설치 순서"]:
            self.assertIn(moment, rule_set.protected_moments)

    def test_parenting_protects_child_safety_info(self):
        rule_set = load_category_rule_set(ContentCategory.PARENTING)
        self.assertIn("아이 안전 정보", rule_set.protected_moments)
        self.assertIn("위험 요소", rule_set.protected_moments)


class TestRemovableMoments(unittest.TestCase):
    """2. 삭제 후보"""

    def test_cleaning_has_explicit_removable_moments(self):
        rule_set = load_category_rule_set(ContentCategory.CLEANING)
        self.assertEqual(
            rule_set.removable_moments,
            ["변화 없는 긴 닦기", "같은 청소 동작 반복", "반복 설명"],
        )

    def test_categories_without_explicit_removable_moments_are_empty(self):
        """사용자 스펙에 삭제 후보가 명시되지 않은 카테고리는 임의로 지어내지 않고 빈 목록이어야 한다."""
        for category in [
            ContentCategory.LIVING,
            ContentCategory.FOOD,
            ContentCategory.PARENTING,
            ContentCategory.BEAUTY,
            ContentCategory.TRAVEL,
            ContentCategory.CAMPING,
        ]:
            with self.subTest(category=category):
                rule_set = load_category_rule_set(category)
                self.assertEqual(rule_set.removable_moments, [])


class TestSubtitleDensity(unittest.TestCase):
    """3. 자막 밀도"""

    def test_density_matches_expected_mapping(self):
        expected = {
            ContentCategory.LIVING: "MEDIUM",
            ContentCategory.CLEANING: "LOW",
            ContentCategory.FOOD: "HIGH",
            ContentCategory.PARENTING: "LOW",
            ContentCategory.BEAUTY: "MEDIUM",
            ContentCategory.TRAVEL: "LOW",
            ContentCategory.CAMPING: "LOW",
        }
        for category, density in expected.items():
            with self.subTest(category=category):
                self.assertEqual(load_category_rule_set(category).subtitle_density, density)

    def test_density_reaches_subtitle_optimizer_payload(self):
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="자막")]
        client = FakeAnthropicClient([FakeResponse(json.dumps({"lines": []}))])

        optimize_subtitles(
            lines,
            category_label=category_label(ContentCategory.FOOD),
            density_rule=build_subtitle_density_rule(ContentCategory.FOOD),
            client=client,
            sleep_fn=noop_sleep,
        )

        sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertIn("빠짐없이", sent["densityRule"])  # FOOD는 HIGH밀도 지침


class TestHookGeneration(unittest.TestCase):
    """4. 훅 생성 (카테고리별 안전 규칙이 실제로 훅 생성 요청에 실림)"""

    def test_beauty_hook_request_carries_medical_claim_ban(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=2.0, text="발색 비교")]
        response = {
            "hooks": [
                {"text": "훅1", "type": "PROBLEM", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
                {"text": "훅2", "type": "CURIOSITY", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
                {"text": "훅3", "type": "RESULT_FIRST", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
            ]
        }
        client = FakeAnthropicClient([FakeResponse(json.dumps(response))])

        generate_ai_hooks(
            "주제",
            segments,
            category_label=category_label(ContentCategory.BEAUTY),
            safety_checks=build_safety_checks(ContentCategory.BEAUTY),
            client=client,
            sleep_fn=noop_sleep,
        )

        sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertIn("의학적 효능 생성 금지", sent["safetyChecks"])
        self.assertIn("영상에 없는 사실 생성 금지", sent["safetyChecks"])  # 공통 규칙도 함께 실림


class TestNaturalAudioProtection(unittest.TestCase):
    """5. 자연음 보호"""

    def test_categories_that_must_preserve_natural_audio(self):
        for category in [
            ContentCategory.FOOD,
            ContentCategory.CLEANING,
            ContentCategory.PARENTING,
            ContentCategory.TRAVEL,
            ContentCategory.CAMPING,
        ]:
            with self.subTest(category=category):
                self.assertTrue(load_category_rule_set(category).preserve_natural_audio)

    def test_categories_without_natural_audio_emphasis(self):
        for category in [ContentCategory.LIVING, ContentCategory.BEAUTY]:
            with self.subTest(category=category):
                self.assertFalse(load_category_rule_set(category).preserve_natural_audio)

    def test_natural_audio_flag_reaches_cut_candidates_payload(self):
        segments = [TranscriptSegment(id="s1", start=0.0, end=5.0, text="조리 소리")]
        client = FakeAnthropicClient([FakeResponse(json.dumps({"candidates": []}))])

        analyze_cut_candidates(
            segments,
            total_duration=5.0,
            preserve_natural_audio=build_preserve_natural_audio(ContentCategory.FOOD),
            client=client,
            sleep_fn=noop_sleep,
        )

        sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertTrue(sent["preserveNaturalAudio"])


class TestSoundEffectRestriction(unittest.TestCase):
    """7. 효과음 제한 (자연음 보호와 짝을 이루므로 자연음 보호 다음에 배치)"""

    def test_sfx_disallowed_when_natural_audio_must_be_preserved(self):
        for category in [ContentCategory.FOOD, ContentCategory.CAMPING, ContentCategory.TRAVEL]:
            with self.subTest(category=category):
                rule_set = load_category_rule_set(category)
                self.assertFalse(sfx_allowed(rule_set))
                self.assertGreater(len(rule_set.discouraged_sound_effects), 0)

    def test_sfx_allowed_for_categories_without_natural_audio_emphasis(self):
        for category in [ContentCategory.LIVING, ContentCategory.BEAUTY]:
            with self.subTest(category=category):
                rule_set = load_category_rule_set(category)
                self.assertTrue(sfx_allowed(rule_set))
                self.assertEqual(rule_set.discouraged_sound_effects, [])


class TestShotComposition(unittest.TestCase):
    """6. 화면 구도"""

    def test_food_preferred_shots_match_given_composition_guide(self):
        rule_set = load_category_rule_set(ContentCategory.FOOD)
        self.assertEqual(
            rule_set.preferred_shot_types,
            ["top_down", "side_angle_30_45", "close_up", "extreme_close_up"],
        )

    def test_cleaning_preferred_shots_match_given_composition_guide(self):
        rule_set = load_category_rule_set(ContentCategory.CLEANING)
        self.assertEqual(
            rule_set.preferred_shot_types,
            ["extreme_close_up", "detail", "top_down", "side_angle"],
        )

    def test_travel_includes_pov_and_follow(self):
        rule_set = load_category_rule_set(ContentCategory.TRAVEL)
        self.assertIn("POV", rule_set.preferred_shot_types)
        self.assertIn("follow", rule_set.preferred_shot_types)

    def test_every_category_has_shooting_guide_rules(self):
        for category in ALL_CATEGORIES:
            with self.subTest(category=category):
                self.assertGreater(len(build_shooting_guide_rules(category)), 0)
                self.assertGreater(len(build_preferred_shot_types(category)), 0)


class TestSafetyRules(unittest.TestCase):
    """8. 안전 규칙"""

    def test_parenting_safety_checks_match_given_rules(self):
        rule_set = load_category_rule_set(ContentCategory.PARENTING)
        self.assertEqual(
            rule_set.safety_checks,
            [
                "아이의 감정을 과장 해석하지 않는다",
                "안전 구간은 자동 삭제하지 않는다",
                "얼굴과 개인정보 노출을 고려한다",
                "울음이나 불편 반응을 재미 요소로 과도하게 사용하지 않는다",
            ],
        )

    def test_camping_safety_checks_match_given_rules(self):
        rule_set = load_category_rule_set(ContentCategory.CAMPING)
        self.assertIn("화기, 칼, 가스 관련 안전 설명 삭제 금지", rule_set.safety_checks)
        self.assertIn("캠핑 장비 성능을 과장하지 않는다", rule_set.safety_checks)

    def test_build_safety_checks_appends_common_rules_after_category_rules(self):
        checks = build_safety_checks(ContentCategory.BEAUTY, include_common=True)
        category_rules = load_category_rule_set(ContentCategory.BEAUTY).safety_checks
        common_rules = load_common_rules()

        self.assertEqual(checks[: len(category_rules)], category_rules)
        self.assertEqual(checks[len(category_rules) :], common_rules)

    def test_build_safety_checks_can_exclude_common_rules(self):
        checks = build_safety_checks(ContentCategory.BEAUTY, include_common=False)
        self.assertEqual(checks, load_category_rule_set(ContentCategory.BEAUTY).safety_checks)


class TestCommonEditingEngineStillWorksWithCategoryRules(unittest.TestCase):
    """9. 기존 공통 편집 엔진 정상 작동 (카테고리 규칙 주입 후에도 ai/* 엔진이 정상 동작하는지)"""

    def test_cut_candidates_engine_accepts_full_category_ruleset(self):
        category = ContentCategory.CAMPING
        segments = [TranscriptSegment(id="s1", start=0.0, end=10.0, text="장작을 준비합니다")]
        client = FakeAnthropicClient(
            [
                FakeResponse(
                    json.dumps(
                        {
                            "candidates": [
                                {
                                    "start": 2.0,
                                    "end": 3.0,
                                    "action": "REVIEW",
                                    "reasonCode": "long_silence",
                                    "reason": "무음",
                                    "confidence": 0.6,
                                    "contextRisk": 0.3,
                                }
                            ]
                        }
                    )
                )
            ]
        )

        result = analyze_cut_candidates(
            segments,
            total_duration=10.0,
            category_label=category_label(category),
            category_protection_rules=build_cut_protection_rules(category),
            removable_moment_hints=build_removable_moment_hints(category),
            preferred_pacing=build_preferred_pacing(category),
            preserve_natural_audio=build_preserve_natural_audio(category),
            safety_checks=build_safety_checks(category),
            client=client,
            sleep_fn=noop_sleep,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].reason_code, "long_silence")

    def test_subtitle_and_hook_engines_accept_category_ruleset(self):
        category = ContentCategory.TRAVEL
        lines = [SubtitleLineWithId(id="l1", start=0.0, end=1.0, text="자막")]
        segments = [TranscriptSegment(id="s1", start=0.0, end=2.0, text="여행 소개")]

        sub_client = FakeAnthropicClient([FakeResponse(json.dumps({"lines": []}))])
        optimize_subtitles(
            lines,
            category_label=category_label(category),
            density_rule=build_subtitle_density_rule(category),
            client=sub_client,
            sleep_fn=noop_sleep,
        )
        self.assertEqual(len(sub_client.messages.calls), 1)

        hook_client = FakeAnthropicClient(
            [
                FakeResponse(
                    json.dumps(
                        {
                            "hooks": [
                                {"text": "훅1", "type": "CURIOSITY", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
                                {"text": "훅2", "type": "QUESTION", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
                                {"text": "훅3", "type": "PROBLEM", "evidenceSegmentIds": ["s1"], "exaggerationRisk": 0.1},
                            ]
                        }
                    )
                )
            ]
        )
        hooks = generate_ai_hooks(
            "여행 주제",
            segments,
            category_label=category_label(category),
            safety_checks=build_safety_checks(category),
            client=hook_client,
            sleep_fn=noop_sleep,
        )
        self.assertEqual(len(hooks), 3)


class TestNoCrossCategoryLeakage(unittest.TestCase):
    """10. 다른 카테고리 규칙이 섞이지 않는지"""

    def test_all_categories_have_distinct_protected_moments(self):
        all_rules = load_all_category_rule_sets()
        seen = {}
        for category, rule_set in all_rules.items():
            key = tuple(sorted(rule_set.protected_moments))
            self.assertNotIn(key, seen.values(), f"{category}의 protectedMoments가 다른 카테고리와 동일함")
            seen[category] = key

    def test_loading_one_category_does_not_mutate_another(self):
        food_before = load_category_rule_set(ContentCategory.FOOD)
        load_category_rule_set(ContentCategory.CLEANING)
        load_category_rule_set(ContentCategory.CAMPING)
        food_after = load_category_rule_set(ContentCategory.FOOD)

        self.assertEqual(food_before.protected_moments, food_after.protected_moments)
        self.assertEqual(food_before.safety_checks, food_after.safety_checks)

    def test_category_specific_safety_checks_do_not_bleed_into_other_categories(self):
        beauty_checks = set(load_category_rule_set(ContentCategory.BEAUTY).safety_checks)
        parenting_checks = set(load_category_rule_set(ContentCategory.PARENTING).safety_checks)
        self.assertTrue(beauty_checks.isdisjoint(parenting_checks))

    def test_payloads_for_two_categories_in_sequence_do_not_mix(self):
        """같은 프로세스에서 카테고리를 바꿔가며 연속 호출해도 이전 카테고리 값이 섞이지 않는지 확인."""
        segments = [TranscriptSegment(id="s1", start=0.0, end=5.0, text="발화")]

        client_a = FakeAnthropicClient([FakeResponse(json.dumps({"candidates": []}))])
        analyze_cut_candidates(
            segments,
            total_duration=5.0,
            category_label=category_label(ContentCategory.FOOD),
            category_protection_rules=build_cut_protection_rules(ContentCategory.FOOD),
            client=client_a,
            sleep_fn=noop_sleep,
        )
        sent_a = json.loads(client_a.messages.calls[0]["messages"][0]["content"])

        client_b = FakeAnthropicClient([FakeResponse(json.dumps({"candidates": []}))])
        analyze_cut_candidates(
            segments,
            total_duration=5.0,
            category_label=category_label(ContentCategory.BEAUTY),
            category_protection_rules=build_cut_protection_rules(ContentCategory.BEAUTY),
            client=client_b,
            sleep_fn=noop_sleep,
        )
        sent_b = json.loads(client_b.messages.calls[0]["messages"][0]["content"])

        self.assertEqual(sent_a["category"], "음식")
        self.assertEqual(sent_b["category"], "뷰티")
        self.assertNotEqual(
            set(sent_a["categoryProtectionRules"]), set(sent_b["categoryProtectionRules"])
        )
        self.assertNotIn("지글거리는 소리", sent_b["categoryProtectionRules"])


if __name__ == "__main__":
    unittest.main()
