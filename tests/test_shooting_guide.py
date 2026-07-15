import unittest

from capcut_auto.categories import CATEGORY_RULES, ContentCategory
from capcut_auto.shooting_guide import (
    TARGET_DURATION_CONFIG,
    ShootingGuideInput,
    ShotAngle,
    generate_shooting_plan,
)


def _make_input(**overrides) -> ShootingGuideInput:
    base = dict(
        topic="원룸 정리 루틴",
        category=ContentCategory.LIVING,
        product_or_situation="옷장 정리",
        target_duration="1_TO_3MIN",
    )
    base.update(overrides)
    return ShootingGuideInput(**base)


class TestGenerateShootingPlan(unittest.TestCase):
    def test_every_category_produces_a_plan(self):
        for category in ContentCategory:
            plan = generate_shooting_plan(_make_input(category=category))
            self.assertGreater(len(plan.shots), 0)
            self.assertEqual(plan.category, category)

    def test_rejects_empty_topic(self):
        with self.assertRaises(ValueError):
            generate_shooting_plan(_make_input(topic="   "))

    def test_shot_count_matches_target_duration_when_template_allows(self):
        plan = generate_shooting_plan(_make_input(category=ContentCategory.FOOD, target_duration="UNDER_1MIN"))
        expected_count, _ = TARGET_DURATION_CONFIG["UNDER_1MIN"]
        self.assertEqual(len(plan.shots), expected_count)

    def test_shot_seconds_sum_to_total_estimated(self):
        for duration_label in TARGET_DURATION_CONFIG:
            plan = generate_shooting_plan(_make_input(target_duration=duration_label))
            self.assertEqual(sum(s.estimated_seconds for s in plan.shots), plan.total_estimated_seconds)

    def test_shots_are_sequentially_ordered_from_one(self):
        plan = generate_shooting_plan(_make_input())
        self.assertEqual([s.order for s in plan.shots], list(range(1, len(plan.shots) + 1)))

    def test_product_and_topic_are_interpolated_into_descriptions(self):
        plan = generate_shooting_plan(
            _make_input(category=ContentCategory.FOOD, product_or_situation="김치볶음밥")
        )
        joined = " ".join(s.description for s in plan.shots)
        self.assertIn("김치볶음밥", joined)

    def test_face_on_camera_false_removes_face_talk_angle(self):
        plan = generate_shooting_plan(_make_input(category=ContentCategory.FOOD, face_on_camera=False))
        self.assertNotIn(ShotAngle.FACE_TALK.value, [s.angle for s in plan.shots])

    def test_face_on_camera_true_keeps_face_talk_angle(self):
        plan = generate_shooting_plan(_make_input(category=ContentCategory.FOOD, face_on_camera=True))
        self.assertIn(ShotAngle.FACE_TALK.value, [s.angle for s in plan.shots])

    def test_must_show_scenes_are_injected_as_extra_shots(self):
        plan = generate_shooting_plan(
            _make_input(must_show_scenes="라벨링 장면, 완성 후 문 닫는 장면")
        )
        descriptions = [s.description for s in plan.shots]
        self.assertIn("라벨링 장면", descriptions)
        self.assertIn("완성 후 문 닫는 장면", descriptions)

    def test_must_show_scenes_inserted_before_final_shot(self):
        plan = generate_shooting_plan(_make_input(must_show_scenes="필수 장면"))
        custom_index = next(i for i, s in enumerate(plan.shots) if s.description == "필수 장면")
        self.assertLess(custom_index, len(plan.shots) - 1)

    def test_equipment_keyword_produces_matching_tip(self):
        plan = generate_shooting_plan(_make_input(equipment="삼각대와 짐벌 있음"))
        joined = " ".join(plan.equipment_tips)
        self.assertIn("삼각대", joined)
        self.assertIn("짐벌", joined)

    def test_no_equipment_gives_default_tip(self):
        plan = generate_shooting_plan(_make_input(equipment=""))
        self.assertEqual(len(plan.equipment_tips), 1)

    def test_short_available_time_produces_warning(self):
        plan = generate_shooting_plan(_make_input(target_duration="OVER_5MIN", available_time="5분"))
        self.assertTrue(any("촬영 가능 시간" in w for w in plan.warnings))

    def test_ample_available_time_produces_no_warning(self):
        plan = generate_shooting_plan(_make_input(target_duration="UNDER_1MIN", available_time="3시간"))
        self.assertEqual(plan.warnings, [])

    def test_unparseable_available_time_is_ignored_gracefully(self):
        plan = generate_shooting_plan(_make_input(available_time="주말에 한가할 때"))
        self.assertEqual(plan.warnings, [])

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            generate_shooting_plan(_make_input(category="NOT_REAL"))  # type: ignore[arg-type]

    def test_deterministic_for_same_input(self):
        a = generate_shooting_plan(_make_input())
        b = generate_shooting_plan(_make_input())
        self.assertEqual(a, b)

    def test_all_categories_have_a_cutlist_rule_too(self):
        # categories.py와 shooting_guide.py가 같은 ContentCategory enum을 공유하는지 확인
        for category in ContentCategory:
            self.assertIn(category, CATEGORY_RULES)


if __name__ == "__main__":
    unittest.main()
