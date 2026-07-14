"""BGM 추천(capcut_auto/bgm_recommend.py) 테스트.

순수 함수라 전부 곧바로 검증한다. 핵심은 "특정 곡 제목/아티스트/저작권 상태/트렌드
여부를 절대 지어내지 않는다"는 불변조건이다. (테스트 시나리오 15: BGM 추천)
"""

import unittest
from dataclasses import fields

from capcut_auto.bgm_recommend import (
    DEFAULT_DUCK_VOLUME_RATIO,
    NATURAL_AUDIO_DUCK_VOLUME_RATIO,
    BgmEnergy,
    BgmMetadataRecommendation,
    assert_no_forbidden_fields,
    recommend_bgm_metadata,
)
from capcut_auto.categories import ContentCategory
from capcut_auto.category_rules import CategoryRuleSet


def _rule_set(preserve_natural_audio=False):
    return CategoryRuleSet(
        category=ContentCategory.FOOD,
        protected_moments=[],
        removable_moments=[],
        preferred_pacing="",
        subtitle_density="",
        preserve_natural_audio=preserve_natural_audio,
        preferred_shot_types=[],
        discouraged_sound_effects=[],
        safety_checks=[],
        shooting_guide_rules=[],
    )


class TestNoFabricatedCommercialInfo(unittest.TestCase):
    def test_dataclass_never_gains_forbidden_fields(self):
        # 실제 곡 제목/아티스트/저작권/트렌드 필드가 이 데이터클래스에 추가되면 안 된다
        assert_no_forbidden_fields()

    def test_no_field_name_contains_forbidden_substrings(self):
        field_names = {f.name for f in fields(BgmMetadataRecommendation)}
        for forbidden in ("title", "artist", "copyright", "trending", "url"):
            for name in field_names:
                self.assertNotIn(forbidden, name.lower())


class TestRecommendBgmMetadata(unittest.TestCase):
    def test_no_category_falls_back_to_neutral_mood(self):
        rec = recommend_bgm_metadata(None, None)
        self.assertEqual(rec.mood, "neutral")

    def test_category_uses_its_default_mood(self):
        rec = recommend_bgm_metadata(ContentCategory.LIVING, None)
        self.assertEqual(rec.mood, "cozy")

    def test_mood_label_is_localized(self):
        rec = recommend_bgm_metadata(ContentCategory.CLEANING, None)
        self.assertEqual(rec.mood, "upbeat")
        self.assertTrue(rec.mood_label)

    def test_tempo_range_is_a_valid_ascending_pair(self):
        rec = recommend_bgm_metadata(ContentCategory.TRAVEL, None)
        low, high = rec.tempo_range_bpm
        self.assertLess(low, high)
        self.assertGreater(low, 0)

    def test_always_recommends_instrumental_only(self):
        for category in ContentCategory:
            rec = recommend_bgm_metadata(category, None)
            self.assertFalse(rec.has_vocals)

    def test_always_recommends_ducking_during_voice(self):
        rec = recommend_bgm_metadata(ContentCategory.BEAUTY, None)
        self.assertTrue(rec.duck_during_voice)
        self.assertEqual(rec.duck_volume_ratio, DEFAULT_DUCK_VOLUME_RATIO)

    def test_search_keywords_are_nonempty_and_include_mood(self):
        rec = recommend_bgm_metadata(ContentCategory.FOOD, None)
        self.assertGreater(len(rec.search_keywords), 0)
        self.assertTrue(any(rec.mood_label in kw for kw in rec.search_keywords))

    def test_preserve_natural_audio_caps_energy_to_low(self):
        rec = recommend_bgm_metadata(ContentCategory.CLEANING, _rule_set(preserve_natural_audio=True))
        # CLEANING 기본 무드(upbeat)는 HIGH 에너지지만 자연음 보호 카테고리는 LOW로 제한된다
        self.assertEqual(rec.energy, BgmEnergy.LOW)

    def test_preserve_natural_audio_uses_stronger_ducking(self):
        rec = recommend_bgm_metadata(ContentCategory.FOOD, _rule_set(preserve_natural_audio=True))
        self.assertEqual(rec.duck_volume_ratio, NATURAL_AUDIO_DUCK_VOLUME_RATIO)
        self.assertLess(rec.duck_volume_ratio, DEFAULT_DUCK_VOLUME_RATIO)

    def test_without_natural_audio_priority_energy_is_not_forced_down(self):
        rec = recommend_bgm_metadata(ContentCategory.CLEANING, _rule_set(preserve_natural_audio=False))
        self.assertEqual(rec.energy, BgmEnergy.HIGH)

    def test_every_category_produces_a_valid_recommendation(self):
        for category in ContentCategory:
            rec = recommend_bgm_metadata(category, None)
            self.assertIsInstance(rec, BgmMetadataRecommendation)
            self.assertIn(rec.energy, list(BgmEnergy))


if __name__ == "__main__":
    unittest.main()
