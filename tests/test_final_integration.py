"""Phase 4 최종 통합 검사 - 20개 시나리오.

1~7. 카테고리별(살림/청소/음식/육아/뷰티/여행/캠핑) 규칙이 SFX/BGM 추천에 실제로
     반영되는지 카테고리별로 검증한다.
8. 카테고리 전환 - 서로 다른 카테고리를 연달아 로드해도 상태가 섞이지 않는지.
9. 컷 편집 - AI 컷 후보 -> 사용자 승인 -> 실제 keep_intervals 적용까지 전체 흐름.
10. 자막 - 단어 -> 자막 줄 그룹핑 -> 컷 이후 타임라인 재매핑 -> SRT.
11. 훅 - 근거 segment가 실재하는 훅만 통과시키는지.
12. 9:16 크롭 - 크롭 계산 + 사용자 승인 게이트.
13. 자연음 보호 - preserveNaturalAudio가 SFX 배제와 BGM 덕킹에 실제로 반영되는지.
14. 효과음 추천 - 전체 추천 파이프라인.
15. BGM 추천 - 메타데이터만 추천하고 상업 정보는 만들어내지 않는지.
16. 촬영 가이드 - MODE 2 v2 계획 생성 + 체크리스트 + 진행률.
17. 실행 취소(undo).
18. 원상복구(revert).
19. 내보내기(export) - 실제 ffmpeg + 실제 pycapcut으로 컷+자막+훅이 반영된 드래프트 생성.
20. 기존 기능 회귀 - Phase 2~4 핵심 모듈이 전부 정상 import/연동되는지.

이 파일의 각 테스트는 이미 세부 모듈별 테스트 파일에서 검증된 내용을 반복하지 않고,
모듈 간 실제 연동(하나의 파이프라인으로 이어 붙였을 때도 맞물리는지)에 집중한다.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.ai.cut_apply import EditHistory, apply_approved_cuts
from capcut_auto.ai.cut_candidates import CutAction, CutCandidate, approved_cut_intervals, review_candidates
from capcut_auto.ai.hook_ai import HookCandidate, HookType, validate_hook_grounding
from capcut_auto.ai.video_structure import VideoSection, VideoSectionRole
from capcut_auto.bgm_recommend import BgmEnergy, assert_no_forbidden_fields, recommend_bgm_metadata
from capcut_auto.categories import ContentCategory
from capcut_auto.category_rules import load_all_category_rule_sets, load_category_rule_set, sfx_allowed
from capcut_auto.draft_builder import build_draft
from capcut_auto.sfx_recommend import SfxAsset, SfxPurpose, recommend_sfx_for_scenes
from capcut_auto.shooting_guide_v2 import (
    ShootingGuideInputV2,
    build_shooting_checklist,
    generate_shooting_plan_v2,
    mark_checklist_item_done,
    shooting_progress,
)
from capcut_auto.subtitles import SubtitleLine, group_words_into_lines, remap_words_to_new_timeline, write_srt
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word
from capcut_auto.visual.reframe import ReframePlan, apply_approved_reframe, compute_crop_window
from capcut_auto.visual.subject_detection import BoundingBox

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
try:
    import pycapcut  # noqa: F401

    PYCAPCUT_AVAILABLE = True
except ImportError:
    PYCAPCUT_AVAILABLE = False


def _sfx_library():
    return {
        SfxPurpose.RESULT_REVEAL: [SfxAsset("r1", SfxPurpose.RESULT_REVEAL, "r1", "/tmp/r1.m4a")],
        SfxPurpose.TRANSITION: [SfxAsset("t1", SfxPurpose.TRANSITION, "t1", "/tmp/t1.m4a")],
        SfxPurpose.EMPHASIS: [SfxAsset("e1", SfxPurpose.EMPHASIS, "e1", "/tmp/e1.m4a")],
        SfxPurpose.SUCCESS: [SfxAsset("s1", SfxPurpose.SUCCESS, "s1", "/tmp/s1.m4a")],
        SfxPurpose.BUILD_UP: [SfxAsset("b1", SfxPurpose.BUILD_UP, "b1", "/tmp/b1.m4a")],
    }


class _CategoryScenarioMixin:
    """카테고리별 시나리오 공통 검증: 규칙 로드 -> SFX/BGM 추천에 실제로 반영."""

    category: ContentCategory

    def _check(self):
        rule_set = load_category_rule_set(self.category)
        self.assertEqual(rule_set.category, self.category)
        self.assertGreater(len(rule_set.protected_moments), 0, "보호 모먼트가 비어있으면 안 됩니다")

        sections = [
            _section(0.0, 3.0, VideoSectionRole.HOOK),
            _section(10.0, 13.0, VideoSectionRole.RESULT),
        ]
        sfx_recs = recommend_sfx_for_scenes(sections, [], [], self.category, rule_set, _sfx_library())
        if rule_set.preserve_natural_audio:
            # 자연음 보호 카테고리는 궁금증 유발형(BUILD_UP)이 배제된다
            self.assertFalse(any(r.purpose == SfxPurpose.BUILD_UP for r in sfx_recs))
        # RESULT_REVEAL은 preserve_natural_audio 여부와 무관하게 항상 추천된다
        self.assertTrue(any(r.purpose == SfxPurpose.RESULT_REVEAL for r in sfx_recs))

        bgm_rec = recommend_bgm_metadata(self.category, rule_set)
        self.assertFalse(bgm_rec.has_vocals)
        if rule_set.preserve_natural_audio:
            self.assertEqual(bgm_rec.energy, BgmEnergy.LOW)

        return rule_set, sfx_recs, bgm_rec


def _section(start, end, role):
    return VideoSection(start, end, role, "")


class TestScenario1Living(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.LIVING

    def test_living_category_end_to_end(self):
        rule_set, _, _ = self._check()
        self.assertFalse(rule_set.preserve_natural_audio)


class TestScenario2Cleaning(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.CLEANING

    def test_cleaning_category_end_to_end(self):
        rule_set, _, _ = self._check()
        self.assertGreater(len(rule_set.removable_moments), 0)


class TestScenario3Food(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.FOOD

    def test_food_category_end_to_end(self):
        rule_set, _, _ = self._check()
        self.assertTrue(rule_set.preserve_natural_audio)


class TestScenario4Parenting(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.PARENTING

    def test_parenting_category_restricts_build_up_and_result(self):
        rule_set, sfx_recs, _ = self._check()
        # 육아는 preserve_natural_audio + 카테고리 제한이 겹쳐도 RESULT_REVEAL은 허용된다
        self.assertTrue(any(r.purpose == SfxPurpose.RESULT_REVEAL for r in sfx_recs))


class TestScenario5Beauty(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.BEAUTY

    def test_beauty_category_end_to_end(self):
        rule_set, _, bgm_rec = self._check()
        self.assertFalse(rule_set.preserve_natural_audio)
        self.assertEqual(bgm_rec.mood, "upbeat")


class TestScenario6Travel(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.TRAVEL

    def test_travel_category_end_to_end(self):
        rule_set, _, _ = self._check()
        self.assertTrue(rule_set.preserve_natural_audio)


class TestScenario7Camping(_CategoryScenarioMixin, unittest.TestCase):
    category = ContentCategory.CAMPING

    def test_camping_category_end_to_end(self):
        rule_set, _, _ = self._check()
        self.assertTrue(rule_set.preserve_natural_audio)


class TestScenario8CategorySwitching(unittest.TestCase):
    def test_switching_categories_does_not_leak_state(self):
        all_sets = load_all_category_rule_sets()
        self.assertEqual(len(all_sets), 7)
        living = all_sets[ContentCategory.LIVING]
        food = all_sets[ContentCategory.FOOD]
        self.assertNotEqual(living.preserve_natural_audio, food.preserve_natural_audio)
        # 두 번 연속 로드해도 매번 독립적인 객체/값을 반환한다 (공유 mutable 상태 없음)
        reloaded_living = load_category_rule_set(ContentCategory.LIVING)
        self.assertEqual(reloaded_living, living)
        self.assertIsNot(reloaded_living.protected_moments, living.protected_moments)

    def test_rapid_alternating_recommendations_stay_isolated(self):
        sections = [_section(0.0, 3.0, VideoSectionRole.HOOK)]
        food_rule = load_category_rule_set(ContentCategory.FOOD)
        living_rule = load_category_rule_set(ContentCategory.LIVING)
        food_recs = recommend_sfx_for_scenes(sections, [], [], ContentCategory.FOOD, food_rule, _sfx_library())
        living_recs = recommend_sfx_for_scenes(sections, [], [], ContentCategory.LIVING, living_rule, _sfx_library())
        self.assertEqual(food_recs, [])  # FOOD는 자연음 보호로 BUILD_UP 배제
        self.assertEqual(len(living_recs), 1)  # LIVING은 배제되지 않음


class TestScenario9CutEditing(unittest.TestCase):
    def test_ai_candidate_to_approved_keep_intervals_pipeline(self):
        candidates = [
            CutCandidate("c1", 2.0, 4.0, CutAction.REVIEW, "filler_word", "필러워드", 0.9, 0.1, 2.0),
            CutCandidate("c2", 8.0, 9.0, CutAction.REVIEW, "silence", "무음", 0.95, 0.05, 1.0),
        ]
        decisions = {"c1": CutAction.AUTO_CUT, "c2": CutAction.KEEP}
        reviewed = review_candidates(candidates, decisions)
        self.assertEqual(reviewed[0].action, CutAction.AUTO_CUT)
        self.assertEqual(reviewed[1].action, CutAction.KEEP)

        intervals = approved_cut_intervals(candidates, decisions)
        self.assertEqual(intervals, [Interval(2.0, 4.0)])

        result = apply_approved_cuts(total_duration=12.0, approved_cut_intervals=intervals)
        self.assertLess(result.kept_duration, 12.0)
        self.assertNotIn(Interval(2.0, 4.0), result.keep_intervals)


class TestScenario10Subtitles(unittest.TestCase):
    def test_words_survive_cut_and_regroup_into_lines_and_srt(self):
        words = [Word(0.0, 0.5, "안녕"), Word(0.6, 1.0, "하세요"), Word(5.0, 5.4, "반갑습니다")]
        keep_intervals = [Interval(0.0, 1.2), Interval(4.8, 6.0)]
        remapped = remap_words_to_new_timeline(words, keep_intervals)
        self.assertEqual(len(remapped), 3)

        lines = group_words_into_lines(remapped)
        self.assertGreater(len(lines), 0)

        with tempfile.TemporaryDirectory() as tmp:
            srt_path = write_srt(lines, str(Path(tmp) / "out.srt"))
            self.assertTrue(Path(srt_path).exists())
            self.assertIn("안녕", Path(srt_path).read_text(encoding="utf-8"))


class TestScenario11Hooks(unittest.TestCase):
    def test_hook_grounded_in_real_segments_passes(self):
        hook = HookCandidate("정말요?", HookType.CURIOSITY, ["seg_1", "seg_2"], 0.2)
        self.assertTrue(validate_hook_grounding(hook, {"seg_1", "seg_2", "seg_3"}))

    def test_hook_referencing_nonexistent_segment_is_rejected(self):
        hook = HookCandidate("정말요?", HookType.CURIOSITY, ["seg_99"], 0.2)
        self.assertFalse(validate_hook_grounding(hook, {"seg_1", "seg_2"}))

    def test_hook_with_no_evidence_is_rejected(self):
        hook = HookCandidate("정말요?", HookType.CURIOSITY, [], 0.2)
        self.assertFalse(validate_hook_grounding(hook, {"seg_1"}))


class TestScenario12NineBySixteenCrop(unittest.TestCase):
    def test_crop_computed_but_requires_approval_before_use(self):
        crop = compute_crop_window(1920, 1080, BoundingBox(900, 400, 100, 100))
        plan = ReframePlan(frame_times=[0.0], windows=[crop], approved=False)
        self.assertIsNone(apply_approved_reframe(plan))

        approved_plan = ReframePlan(frame_times=[0.0], windows=[crop], approved=True)
        applied = apply_approved_reframe(approved_plan)
        self.assertEqual(applied.windows[0], crop)
        self.assertLessEqual(applied.windows[0].x + applied.windows[0].width, 1920 + 1e-6)


class TestScenario13NaturalAudioProtection(unittest.TestCase):
    def test_preserve_natural_audio_suppresses_sfx_but_allows_bgm_at_lower_volume(self):
        food_rule = load_category_rule_set(ContentCategory.FOOD)
        self.assertTrue(sfx_allowed(food_rule) is False)  # sfx_allowed = not preserve_natural_audio

        sections = [_section(0.0, 3.0, VideoSectionRole.HOOK), _section(10.0, 13.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [], ContentCategory.FOOD, food_rule, _sfx_library())
        self.assertFalse(any(r.purpose == SfxPurpose.BUILD_UP for r in recs))

        bgm = recommend_bgm_metadata(ContentCategory.FOOD, food_rule)
        default_bgm = recommend_bgm_metadata(ContentCategory.FOOD, None)
        self.assertLess(bgm.duck_volume_ratio, default_bgm.duck_volume_ratio)


class TestScenario14SfxRecommendation(unittest.TestCase):
    def test_full_recommendation_and_approval_gate(self):
        from capcut_auto.sfx_recommend import apply_approved_sfx

        sections = [_section(10.0, 13.0, VideoSectionRole.RESULT)]
        recs = recommend_sfx_for_scenes(sections, [], [], None, None, _sfx_library())
        self.assertEqual(len(recs), 1)
        self.assertEqual(apply_approved_sfx(recs), [])  # 승인 전에는 배치되지 않음

        recs[0].approved = True
        recs[0].selected_asset_id = recs[0].candidates[0].asset.id
        placements = apply_approved_sfx(recs)
        self.assertEqual(len(placements), 1)


class TestScenario15BgmRecommendation(unittest.TestCase):
    def test_bgm_metadata_has_no_fabricated_commercial_info(self):
        assert_no_forbidden_fields()
        rec = recommend_bgm_metadata(ContentCategory.TRAVEL, None)
        self.assertTrue(rec.mood)
        self.assertGreater(len(rec.search_keywords), 0)
        self.assertTrue(rec.duck_during_voice)


class TestScenario16ShootingGuide(unittest.TestCase):
    def test_plan_generation_checklist_and_progress(self):
        guide_input = ShootingGuideInputV2(
            topic="캠핑 요리",
            category=ContentCategory.CAMPING,
            subject="더치오븐 요리",
            target_duration_seconds=30,
            must_show_steps=["불 피우는 장면"],
        )
        plan = generate_shooting_plan_v2(guide_input)
        self.assertGreaterEqual(plan.shot_count, plan.cut_count_range[0])

        checklist = build_shooting_checklist(plan)
        checklist = mark_checklist_item_done(checklist, order=1, done=True)
        progress = shooting_progress(checklist)
        self.assertEqual(progress["done"], 1)


class TestScenario17Undo(unittest.TestCase):
    def test_undo_restores_previous_edit(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 10.0)])
        history.push([Interval(0.0, 4.0), Interval(6.0, 10.0)], "cut filler")
        history.push([Interval(0.0, 4.0)], "cut more")
        self.assertEqual(history.current, [Interval(0.0, 4.0)])

        self.assertTrue(history.undo())
        self.assertEqual(history.current, [Interval(0.0, 4.0), Interval(6.0, 10.0)])

        self.assertTrue(history.undo())
        self.assertEqual(history.current, [Interval(0.0, 10.0)])
        self.assertFalse(history.can_undo)


class TestScenario18Revert(unittest.TestCase):
    def test_revert_after_multiple_edits_and_an_undo(self):
        history = EditHistory(original_keep_intervals=[Interval(0.0, 20.0)])
        history.push([Interval(0.0, 15.0)], "edit1")
        history.push([Interval(0.0, 10.0)], "edit2")
        history.undo()
        history.revert_to_original()
        self.assertEqual(history.current, [Interval(0.0, 20.0)])
        self.assertFalse(history.can_undo)
        self.assertFalse(history.can_redo)


@unittest.skipUnless(
    FFMPEG_AVAILABLE and PYCAPCUT_AVAILABLE,
    "ffmpeg 또는 pycapcut이 설치되어 있지 않아 통합 테스트를 건너뜁니다.",
)
class TestScenario19Export(unittest.TestCase):
    def test_full_pipeline_to_real_capcut_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "src.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=6",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video_path,
                ],
                capture_output=True, text=True, check=True,
            )

            words = [Word(1.0, 1.3, "안녕"), Word(1.4, 1.8, "하세요")]
            candidates = [CutCandidate("c1", 3.0, 4.0, CutAction.REVIEW, "silence", "무음", 0.95, 0.05, 1.0)]
            decisions = {"c1": CutAction.AUTO_CUT}
            cut_intervals = approved_cut_intervals(candidates, decisions)
            result = apply_approved_cuts(total_duration=6.0, approved_cut_intervals=cut_intervals, words=words)

            remapped_words = remap_words_to_new_timeline(words, result.keep_intervals)
            subtitle_lines = group_words_into_lines(remapped_words) or [SubtitleLine(0.0, 1.0, "안녕하세요")]

            drafts_dir = str(Path(tmp) / "drafts")
            Path(drafts_dir).mkdir()
            draft_name = build_draft(
                video_path=video_path,
                keep_intervals=result.keep_intervals,
                subtitle_lines=subtitle_lines,
                draft_name="final_integration_test",
                capcut_drafts_dir=drafts_dir,
                hook_text="진짜 이렇게 됐다고?",
            )
            self.assertTrue((Path(drafts_dir) / draft_name / "draft_content.json").exists())


class TestScenario20ExistingFeatureRegression(unittest.TestCase):
    """Phase 2~4에서 만든 핵심 모듈이 전부 정상적으로 import/상호운용되는지 확인한다.

    개별 모듈의 세부 동작은 각 모듈의 전용 테스트 파일이 담당한다 - 여기서는
    "이번 단계가 이전 단계를 깨지 않았는지"를 최소 스모크 수준으로 확인한다.
    """

    def test_all_phase_modules_import_cleanly(self):
        import capcut_auto.ai.cut_apply  # noqa: F401
        import capcut_auto.ai.cut_candidates  # noqa: F401
        import capcut_auto.ai.hook_ai  # noqa: F401
        import capcut_auto.ai.subtitle_highlight  # noqa: F401
        import capcut_auto.ai.subtitle_optimizer  # noqa: F401
        import capcut_auto.ai.timeline_recalc  # noqa: F401
        import capcut_auto.ai.video_structure  # noqa: F401
        import capcut_auto.audio_mix  # noqa: F401
        import capcut_auto.bgm_recommend  # noqa: F401
        import capcut_auto.category_rules  # noqa: F401
        import capcut_auto.cutlist  # noqa: F401
        import capcut_auto.draft_builder  # noqa: F401
        import capcut_auto.hooks  # noqa: F401
        import capcut_auto.pipeline  # noqa: F401
        import capcut_auto.sfx_recommend  # noqa: F401
        import capcut_auto.shooting_guide  # noqa: F401
        import capcut_auto.shooting_guide_v2  # noqa: F401
        import capcut_auto.subtitles  # noqa: F401
        import capcut_auto.timeline  # noqa: F401
        import capcut_auto.visual.frame_extraction  # noqa: F401
        import capcut_auto.visual.reframe  # noqa: F401
        import capcut_auto.visual.subject_detection  # noqa: F401
        import capcut_auto.visual.subtitle_safe_zone  # noqa: F401

    def test_original_v1_shooting_guide_still_works_alongside_v2(self):
        from capcut_auto.shooting_guide import ShootingGuideInput, generate_shooting_plan

        plan_v1 = generate_shooting_plan(
            ShootingGuideInput(
                topic="냉장고 정리",
                category=ContentCategory.LIVING,
                product_or_situation="냉장고",
                target_duration="1_TO_3MIN",
            )
        )
        self.assertGreater(len(plan_v1.shots), 0)

    def test_seven_category_rule_files_all_still_load(self):
        for category in ContentCategory:
            rule_set = load_category_rule_set(category)
            self.assertEqual(rule_set.category, category)


if __name__ == "__main__":
    unittest.main()
