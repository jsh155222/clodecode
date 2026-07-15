"""MODE 2 촬영 가이드 확장(capcut_auto/shooting_guide_v2.py) 테스트.

(테스트 시나리오 16: 촬영 가이드)
"""

import unittest

from capcut_auto.categories import ContentCategory
from capcut_auto.shooting_guide_v2 import (
    MODE1_INDEPENDENCE_NOTICE,
    ShootingGuideInputV2,
    ShotRole,
    build_shooting_checklist,
    cut_count_range_for_duration,
    generate_shooting_plan_v2,
    mark_checklist_item_done,
    shooting_progress,
)


class TestCutCountRangeForDuration(unittest.TestCase):
    def test_15_to_30_seconds_band(self):
        self.assertEqual(cut_count_range_for_duration(15), (6, 12))
        self.assertEqual(cut_count_range_for_duration(30), (6, 12))
        self.assertEqual(cut_count_range_for_duration(22), (6, 12))

    def test_30_to_60_seconds_band_takes_precedence_at_upper_boundary(self):
        # 30초는 두 구간 경계에 걸치는데, 먼저 정의된 15~30 구간이 매칭된다
        self.assertEqual(cut_count_range_for_duration(45), (8, 18))
        self.assertEqual(cut_count_range_for_duration(60), (8, 18))

    def test_shorter_than_band_is_scaled_down(self):
        lo, hi = cut_count_range_for_duration(7.5)
        self.assertLess(hi, 12)
        self.assertGreaterEqual(lo, 2)

    def test_longer_than_band_extends_density(self):
        lo, hi = cut_count_range_for_duration(120)
        self.assertGreater(lo, 8)
        self.assertGreater(hi, 18)

    def test_zero_or_negative_raises(self):
        with self.assertRaises(ValueError):
            cut_count_range_for_duration(0)


def _base_input(**overrides):
    defaults = dict(
        topic="냉장고 정리",
        category=ContentCategory.LIVING,
        subject="냉장고",
        target_duration_seconds=30,
    )
    defaults.update(overrides)
    return ShootingGuideInputV2(**defaults)


class TestGenerateShootingPlanV2(unittest.TestCase):
    def test_empty_topic_raises(self):
        with self.assertRaises(ValueError):
            generate_shooting_plan_v2(_base_input(topic="  "))

    def test_empty_subject_raises(self):
        with self.assertRaises(ValueError):
            generate_shooting_plan_v2(_base_input(subject=""))

    def test_shot_count_within_cut_range(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=20))
        lo, hi = plan.cut_count_range
        self.assertGreaterEqual(plan.shot_count, lo)
        self.assertLessEqual(plan.shot_count, hi)

    def test_shots_are_sequentially_ordered_from_1(self):
        plan = generate_shooting_plan_v2(_base_input())
        self.assertEqual([s.order for s in plan.shots], list(range(1, len(plan.shots) + 1)))

    def test_hook_and_result_roles_present(self):
        plan = generate_shooting_plan_v2(_base_input())
        roles = {s.role for s in plan.shots}
        self.assertIn(ShotRole.HOOK.value, roles)
        self.assertIn(ShotRole.RESULT.value, roles)

    def test_first_shot_is_hook_last_is_result(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=45))
        self.assertEqual(plan.shots[0].role, ShotRole.HOOK.value)
        self.assertEqual(plan.shots[-1].role, ShotRole.RESULT.value)

    def test_every_shot_has_all_five_camera_dimensions(self):
        plan = generate_shooting_plan_v2(_base_input())
        for shot in plan.shots:
            self.assertTrue(shot.camera.angle)
            self.assertTrue(shot.camera.distance)
            self.assertTrue(shot.camera.height)
            self.assertTrue(shot.camera.direction)
            self.assertTrue(shot.camera.movement)

    def test_every_shot_has_subtitle_safe_zone_hint(self):
        plan = generate_shooting_plan_v2(_base_input())
        for shot in plan.shots:
            self.assertTrue(shot.subtitle_safe_zone_hint)

    def test_hook_change_result_are_mandatory(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=45))
        mandatory_roles = {s.role for s in plan.shots if s.mandatory}
        self.assertIn(ShotRole.HOOK.value, mandatory_roles)
        self.assertIn(ShotRole.RESULT.value, mandatory_roles)

    def test_subject_is_interpolated_into_description(self):
        plan = generate_shooting_plan_v2(_base_input(subject="에어프라이어"))
        self.assertTrue(any("에어프라이어" in s.description for s in plan.shots))

    def test_show_face_false_adjusts_hook_and_result_description(self):
        plan = generate_shooting_plan_v2(_base_input(show_face=False, target_duration_seconds=45))
        hook = next(s for s in plan.shots if s.role == ShotRole.HOOK.value)
        self.assertIn("내레이션", hook.description)

    def test_show_face_true_does_not_adjust_description(self):
        plan = generate_shooting_plan_v2(_base_input(show_face=True, target_duration_seconds=45))
        hook = next(s for s in plan.shots if s.role == ShotRole.HOOK.value)
        self.assertNotIn("내레이션", hook.description)

    def test_must_show_steps_are_inserted_as_mandatory_shots(self):
        plan = generate_shooting_plan_v2(
            _base_input(target_duration_seconds=45, must_show_steps=["유통기한 확인 장면", "정리함 라벨링"])
        )
        forced = [s for s in plan.shots if s.description in ("유통기한 확인 장면", "정리함 라벨링")]
        self.assertEqual(len(forced), 2)
        self.assertTrue(all(s.mandatory for s in forced))

    def test_many_must_show_steps_trigger_over_range_warning(self):
        many_steps = [f"필수 장면 {i}" for i in range(20)]
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=20, must_show_steps=many_steps))
        self.assertTrue(any("권장 컷 수 범위" in w for w in plan.warnings))

    def test_insufficient_available_time_triggers_warning(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=60, available_shooting_minutes=1))
        self.assertTrue(any("촬영 가능 시간" in w for w in plan.warnings))

    def test_sufficient_available_time_triggers_no_time_warning(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=20, available_shooting_minutes=120))
        self.assertFalse(any("촬영 가능 시간" in w for w in plan.warnings))

    def test_mode1_independence_notice_is_always_present(self):
        plan = generate_shooting_plan_v2(_base_input())
        self.assertIn(MODE1_INDEPENDENCE_NOTICE, plan.warnings)

    def test_equipment_list_is_echoed_back(self):
        plan = generate_shooting_plan_v2(_base_input(equipment=["삼각대", "짐벌"]))
        self.assertEqual(plan.equipment, ["삼각대", "짐벌"])

    def test_no_equipment_defaults_to_empty_list(self):
        plan = generate_shooting_plan_v2(_base_input())
        self.assertEqual(plan.equipment, [])

    def test_recommended_shooting_seconds_are_positive(self):
        plan = generate_shooting_plan_v2(_base_input())
        for shot in plan.shots:
            self.assertGreater(shot.recommended_shooting_seconds, 0)


class TestShootingChecklist(unittest.TestCase):
    def test_checklist_length_matches_shots(self):
        plan = generate_shooting_plan_v2(_base_input())
        checklist = build_shooting_checklist(plan)
        self.assertEqual(len(checklist), len(plan.shots))

    def test_checklist_items_start_undone(self):
        plan = generate_shooting_plan_v2(_base_input())
        checklist = build_shooting_checklist(plan)
        self.assertTrue(all(not item.done for item in checklist))

    def test_mark_item_done_only_affects_target_order(self):
        plan = generate_shooting_plan_v2(_base_input())
        checklist = build_shooting_checklist(plan)
        updated = mark_checklist_item_done(checklist, order=1, done=True)
        self.assertTrue(updated[0].done)
        self.assertTrue(all(not item.done for item in updated[1:]))

    def test_progress_reports_correct_counts(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=45))
        checklist = build_shooting_checklist(plan)
        checklist = mark_checklist_item_done(checklist, order=1, done=True)
        progress = shooting_progress(checklist)
        self.assertEqual(progress["done"], 1)
        self.assertEqual(progress["total"], len(checklist))

    def test_progress_on_empty_checklist_does_not_divide_by_zero(self):
        progress = shooting_progress([])
        self.assertEqual(progress["percent"], 0)
        self.assertEqual(progress["mandatory_percent"], 0)

    def test_mandatory_progress_tracks_only_mandatory_items(self):
        plan = generate_shooting_plan_v2(_base_input(target_duration_seconds=45))
        checklist = build_shooting_checklist(plan)
        hook_order = next(item.order for item in checklist if item.role_label == "초반 훅 장면")
        checklist = mark_checklist_item_done(checklist, order=hook_order, done=True)
        progress = shooting_progress(checklist)
        self.assertEqual(progress["mandatory_done"], 1)
        self.assertGreater(progress["mandatory_total"], 0)


if __name__ == "__main__":
    unittest.main()
