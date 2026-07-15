"""장면에 맞는 효과음 추천(capcut_auto/sfx_recommend.py) 테스트.

순수 함수는 곧바로 검증하고, 실제 ffmpeg 톤 생성은 real ffmpeg 통합 테스트(skipUnless)로
검증한다. (테스트 시나리오 14: 효과음 추천)
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from capcut_auto.ai.video_structure import VideoSection, VideoSectionRole
from capcut_auto.categories import ContentCategory
from capcut_auto.category_rules import CategoryRuleSet
from capcut_auto.sfx_recommend import (
    DEFAULT_MAX_PER_10S,
    DEFAULT_SFX_DURATION,
    SfxAsset,
    SfxCandidate,
    SfxPlacement,
    SfxPurpose,
    SfxRecommendation,
    apply_approved_sfx,
    classify_scene_purpose,
    ensure_sfx_asset_library,
    exceeds_frequency_limit,
    is_consecutive_repeat,
    overlaps_protected_interval,
    overlaps_voice,
    recommend_sfx_for_scenes,
    search_sfx_candidates,
)
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _section(start, end, role, summary=""):
    return VideoSection(start, end, role, summary)


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


class TestClassifySceneMPurpose(unittest.TestCase):
    def test_result_role_maps_to_result_reveal(self):
        section = _section(0.0, 2.0, VideoSectionRole.RESULT)
        self.assertEqual(classify_scene_purpose(section), SfxPurpose.RESULT_REVEAL)

    def test_proof_role_also_maps_to_result_reveal(self):
        section = _section(0.0, 2.0, VideoSectionRole.PROOF)
        self.assertEqual(classify_scene_purpose(section), SfxPurpose.RESULT_REVEAL)

    def test_hook_role_maps_to_build_up(self):
        section = _section(0.0, 2.0, VideoSectionRole.HOOK)
        self.assertEqual(classify_scene_purpose(section), SfxPurpose.BUILD_UP)

    def test_unmapped_role_returns_none_not_fabricated(self):
        for role in (VideoSectionRole.PROBLEM, VideoSectionRole.CAUSE, VideoSectionRole.SOLUTION,
                     VideoSectionRole.PROCESS, VideoSectionRole.UNKNOWN):
            section = _section(0.0, 2.0, role)
            self.assertIsNone(classify_scene_purpose(section))


class TestExceedsFrequencyLimit(unittest.TestCase):
    def test_under_limit_within_window_is_allowed(self):
        self.assertFalse(exceeds_frequency_limit([0.0], 3.0, window=10.0, max_per_window=DEFAULT_MAX_PER_10S))

    def test_at_limit_within_window_is_rejected(self):
        self.assertTrue(exceeds_frequency_limit([0.0, 2.0], 3.0, window=10.0, max_per_window=DEFAULT_MAX_PER_10S))

    def test_outside_window_does_not_count(self):
        self.assertFalse(exceeds_frequency_limit([0.0, 100.0], 50.0, window=10.0, max_per_window=1))


class TestOverlapsVoice(unittest.TestCase):
    def test_overlapping_word_blocks_placement(self):
        words = [Word(1.0, 2.0, "안녕")]
        self.assertTrue(overlaps_voice(1.2, DEFAULT_SFX_DURATION, words))

    def test_non_overlapping_word_allows_placement(self):
        words = [Word(1.0, 2.0, "안녕")]
        self.assertFalse(overlaps_voice(5.0, DEFAULT_SFX_DURATION, words))


class TestOverlapsProtectedInterval(unittest.TestCase):
    def test_overlap_blocks_placement(self):
        intervals = [Interval(1.0, 3.0)]
        self.assertTrue(overlaps_protected_interval(2.0, DEFAULT_SFX_DURATION, intervals))

    def test_no_overlap_allows_placement(self):
        intervals = [Interval(1.0, 3.0)]
        self.assertFalse(overlaps_protected_interval(10.0, DEFAULT_SFX_DURATION, intervals))


class TestIsConsecutiveRepeat(unittest.TestCase):
    def test_empty_history_is_never_repeat(self):
        self.assertFalse(is_consecutive_repeat([], "soft_reveal_1"))

    def test_same_asset_as_last_is_repeat(self):
        placements = [SfxPlacement(0.0, "soft_reveal_1")]
        self.assertTrue(is_consecutive_repeat(placements, "soft_reveal_1"))

    def test_different_asset_from_last_is_not_repeat(self):
        placements = [SfxPlacement(0.0, "soft_reveal_1")]
        self.assertFalse(is_consecutive_repeat(placements, "soft_reveal_2"))


class TestSearchSfxCandidates(unittest.TestCase):
    def test_returns_up_to_max_candidates(self):
        library = {
            SfxPurpose.RESULT_REVEAL: [
                SfxAsset("a1", SfxPurpose.RESULT_REVEAL, "a1", "/tmp/a1.m4a"),
                SfxAsset("a2", SfxPurpose.RESULT_REVEAL, "a2", "/tmp/a2.m4a"),
                SfxAsset("a3", SfxPurpose.RESULT_REVEAL, "a3", "/tmp/a3.m4a"),
                SfxAsset("a4", SfxPurpose.RESULT_REVEAL, "a4", "/tmp/a4.m4a"),
            ]
        }
        candidates = search_sfx_candidates(library, SfxPurpose.RESULT_REVEAL, max_candidates=3)
        self.assertEqual(len(candidates), 3)

    def test_unknown_purpose_returns_empty(self):
        self.assertEqual(search_sfx_candidates({}, SfxPurpose.RESULT_REVEAL), [])

    def test_candidates_carry_a_reason(self):
        library = {SfxPurpose.TRANSITION: [SfxAsset("t1", SfxPurpose.TRANSITION, "t1", "/tmp/t1.m4a")]}
        candidates = search_sfx_candidates(library, SfxPurpose.TRANSITION)
        self.assertTrue(candidates[0].reason)


class TestApplyApprovedSfx(unittest.TestCase):
    def test_unapproved_recommendation_is_dropped(self):
        rec = SfxRecommendation(time=1.0, purpose=SfxPurpose.RESULT_REVEAL, candidates=[], selected_asset_id="a1", approved=False)
        self.assertEqual(apply_approved_sfx([rec]), [])

    def test_approved_without_selection_is_dropped(self):
        rec = SfxRecommendation(time=1.0, purpose=SfxPurpose.RESULT_REVEAL, candidates=[], selected_asset_id=None, approved=True)
        self.assertEqual(apply_approved_sfx([rec]), [])

    def test_approved_with_selection_is_applied(self):
        rec = SfxRecommendation(time=1.0, purpose=SfxPurpose.RESULT_REVEAL, candidates=[], selected_asset_id="a1", approved=True)
        self.assertEqual(apply_approved_sfx([rec]), [SfxPlacement(time=1.0, asset_id="a1")])


def _library():
    return {
        SfxPurpose.RESULT_REVEAL: [SfxAsset("soft_reveal_1", SfxPurpose.RESULT_REVEAL, "l1", "/tmp/r1.m4a")],
        SfxPurpose.TRANSITION: [SfxAsset("soft_whoosh_1", SfxPurpose.TRANSITION, "l2", "/tmp/tr1.m4a")],
        SfxPurpose.EMPHASIS: [SfxAsset("emphasis_tap_1", SfxPurpose.EMPHASIS, "l3", "/tmp/e1.m4a")],
        SfxPurpose.SUCCESS: [SfxAsset("success_chime_1", SfxPurpose.SUCCESS, "l4", "/tmp/s1.m4a")],
        SfxPurpose.BUILD_UP: [SfxAsset("build_up_1", SfxPurpose.BUILD_UP, "l5", "/tmp/b1.m4a")],
    }


class TestRecommendSfxForScenes(unittest.TestCase):
    def test_recommends_for_result_section(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [], None, None, _library())
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].purpose, SfxPurpose.RESULT_REVEAL)
        self.assertEqual(recs[0].time, 10.0)

    def test_unmapped_role_produces_no_recommendation(self):
        sections = [_section(0.0, 5.0, VideoSectionRole.PROCESS)]
        recs = recommend_sfx_for_scenes(sections, [], [], None, None, _library())
        self.assertEqual(recs, [])

    def test_low_confidence_scene_is_skipped(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(
            sections, [], [], None, None, _library(), section_confidence={10.0: 0.1}
        )
        self.assertEqual(recs, [])

    def test_voice_overlap_blocks_recommendation(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        words = [Word(10.0, 10.5, "짠")]
        recs = recommend_sfx_for_scenes(sections, words, [], None, None, _library())
        self.assertEqual(recs, [])

    def test_protected_interval_blocks_recommendation(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [Interval(9.5, 10.5)], None, None, _library())
        self.assertEqual(recs, [])

    def test_parenting_category_restricts_build_up(self):
        sections = [_section(0.0, 5.0, VideoSectionRole.HOOK)]
        recs = recommend_sfx_for_scenes(sections, [], [], ContentCategory.PARENTING, None, _library())
        self.assertEqual(recs, [])

    def test_parenting_category_allows_result_reveal(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [], ContentCategory.PARENTING, None, _library())
        self.assertEqual(len(recs), 1)

    def test_preserve_natural_audio_suppresses_build_up(self):
        sections = [_section(0.0, 5.0, VideoSectionRole.HOOK)]
        recs = recommend_sfx_for_scenes(
            sections, [], [], ContentCategory.FOOD, _rule_set(preserve_natural_audio=True), _library()
        )
        self.assertEqual(recs, [])

    def test_preserve_natural_audio_still_allows_result_reveal(self):
        sections = [_section(10.0, 15.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(
            sections, [], [], ContentCategory.FOOD, _rule_set(preserve_natural_audio=True), _library()
        )
        self.assertEqual(len(recs), 1)

    def test_frequency_limit_caps_recommendations_within_window(self):
        # 연속 반복 금지 규칙과 분리해서 검증하려고 서로 다른 후보 자산 2개를 둔다
        library = {
            SfxPurpose.RESULT_REVEAL: [
                SfxAsset("r1", SfxPurpose.RESULT_REVEAL, "r1", "/tmp/r1.m4a"),
                SfxAsset("r2", SfxPurpose.RESULT_REVEAL, "r2", "/tmp/r2.m4a"),
            ]
        }
        sections = [
            _section(0.0, 1.0, VideoSectionRole.RESULT),
            _section(2.0, 3.0, VideoSectionRole.RESULT),
            _section(4.0, 5.0, VideoSectionRole.RESULT),
        ]
        recs = recommend_sfx_for_scenes(sections, [], [], None, None, library)
        # DEFAULT_MAX_PER_10S=2, window=10초(반경 5초) - 세 번째(4.0)는 0.0/2.0 둘 다와
        # 5초 이내라 창 안 배치 수가 이미 2개가 되어 차단된다
        self.assertEqual([r.time for r in recs], [0.0, 2.0])

    def test_max_three_candidates_per_recommendation(self):
        library = {
            SfxPurpose.RESULT_REVEAL: [
                SfxAsset(f"r{i}", SfxPurpose.RESULT_REVEAL, f"r{i}", f"/tmp/r{i}.m4a") for i in range(5)
            ]
        }
        sections = [_section(0.0, 2.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [], None, None, library)
        self.assertLessEqual(len(recs[0].candidates), 3)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestEnsureSfxAssetLibraryIntegration(unittest.TestCase):
    def test_generates_real_playable_audio_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = ensure_sfx_asset_library(tmp)
            self.assertIn(SfxPurpose.RESULT_REVEAL, library)
            for purpose, assets in library.items():
                self.assertGreater(len(assets), 0)
                for asset in assets:
                    self.assertTrue(Path(asset.path).exists())
                    self.assertGreater(Path(asset.path).stat().st_size, 0)

    def test_reuses_existing_files_instead_of_regenerating(self):
        with tempfile.TemporaryDirectory() as tmp:
            library1 = ensure_sfx_asset_library(tmp)
            first_mtime = Path(library1[SfxPurpose.EMPHASIS][0].path).stat().st_mtime_ns
            library2 = ensure_sfx_asset_library(tmp)
            second_mtime = Path(library2[SfxPurpose.EMPHASIS][0].path).stat().st_mtime_ns
            self.assertEqual(first_mtime, second_mtime)


if __name__ == "__main__":
    unittest.main()
