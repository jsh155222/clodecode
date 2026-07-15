import unittest

from capcut_auto.categories import ContentCategory
from capcut_auto.hooks import generate_hook_suggestions


class TestGenerateHookSuggestions(unittest.TestCase):
    def test_returns_requested_count(self):
        result = generate_hook_suggestions("원룸 정리 루틴", ContentCategory.LIVING, max_suggestions=2)
        self.assertEqual(len(result), 2)

    def test_includes_topic_text(self):
        result = generate_hook_suggestions("무선 청소기 리뷰", ContentCategory.CLEANING, max_suggestions=3)
        for suggestion in result:
            self.assertIn("무선 청소기 리뷰", suggestion)

    def test_deterministic_for_same_input(self):
        a = generate_hook_suggestions("캠핑 요리", ContentCategory.CAMPING)
        b = generate_hook_suggestions("캠핑 요리", ContentCategory.CAMPING)
        self.assertEqual(a, b)

    def test_different_categories_produce_different_suggestions(self):
        living = generate_hook_suggestions("정리 팁", ContentCategory.LIVING)
        travel = generate_hook_suggestions("정리 팁", ContentCategory.TRAVEL)
        self.assertNotEqual(living, travel)

    def test_rejects_empty_topic(self):
        with self.assertRaises(ValueError):
            generate_hook_suggestions("   ", ContentCategory.FOOD)

    def test_zero_max_suggestions_returns_empty(self):
        self.assertEqual(generate_hook_suggestions("주제", ContentCategory.BEAUTY, max_suggestions=0), [])


if __name__ == "__main__":
    unittest.main()
