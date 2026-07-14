import unittest

from capcut_auto.categories import CATEGORY_LABELS, CATEGORY_RULES, ContentCategory, get_rule


class TestCategories(unittest.TestCase):
    def test_all_seven_categories_defined(self):
        self.assertEqual(
            {c.value for c in ContentCategory},
            {"LIVING", "CLEANING", "FOOD", "PARENTING", "BEAUTY", "TRAVEL", "CAMPING"},
        )

    def test_every_category_has_a_label_and_rule(self):
        for category in ContentCategory:
            self.assertIn(category, CATEGORY_LABELS)
            self.assertIn(category, CATEGORY_RULES)

    def test_get_rule_returns_matching_category(self):
        rule = get_rule(ContentCategory.FOOD)
        self.assertEqual(rule.category, ContentCategory.FOOD)
        self.assertGreater(len(rule.hook_keywords), 0)

    def test_labels_match_frontend_korean_names(self):
        expected = {
            ContentCategory.LIVING: "살림",
            ContentCategory.CLEANING: "청소",
            ContentCategory.FOOD: "음식",
            ContentCategory.PARENTING: "육아",
            ContentCategory.BEAUTY: "뷰티",
            ContentCategory.TRAVEL: "여행",
            ContentCategory.CAMPING: "캠핑",
        }
        self.assertEqual(CATEGORY_LABELS, expected)


if __name__ == "__main__":
    unittest.main()
