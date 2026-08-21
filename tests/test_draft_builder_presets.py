"""자막 위치/스타일 프리셋(build_subtitle_appearance) 순수 로직 검증. pycapcut 불필요."""

import unittest

from capcut_auto.draft_builder import (
    SUBTITLE_POSITION_LABELS,
    SUBTITLE_POSITION_PRESETS,
    SUBTITLE_STYLE_LABELS,
    SUBTITLE_STYLE_PRESETS,
    TextBackgroundSpec,
    TextBorderSpec,
    build_subtitle_appearance,
)


class TestPositionPresets(unittest.TestCase):
    def test_every_position_preset_has_a_label(self):
        self.assertEqual(set(SUBTITLE_POSITION_PRESETS), set(SUBTITLE_POSITION_LABELS))

    def test_upper_is_positive_lower_is_negative(self):
        self.assertGreater(SUBTITLE_POSITION_PRESETS["upper"], 0)
        self.assertEqual(SUBTITLE_POSITION_PRESETS["middle"], 0.0)
        self.assertLess(SUBTITLE_POSITION_PRESETS["lower"], 0)

    def test_build_subtitle_appearance_maps_position_key_to_vertical_position(self):
        appearance = build_subtitle_appearance(position="upper")
        self.assertEqual(appearance.vertical_position, SUBTITLE_POSITION_PRESETS["upper"])

    def test_unknown_position_falls_back_to_lower(self):
        appearance = build_subtitle_appearance(position="does-not-exist")
        self.assertEqual(appearance.vertical_position, SUBTITLE_POSITION_PRESETS["lower"])


class TestStylePresets(unittest.TestCase):
    def test_every_style_preset_has_a_label(self):
        self.assertEqual(set(SUBTITLE_STYLE_PRESETS), set(SUBTITLE_STYLE_LABELS))

    def test_default_style_has_no_border_or_background(self):
        appearance = build_subtitle_appearance(style="default")
        self.assertIsNone(appearance.border)
        self.assertIsNone(appearance.background)

    def test_yellow_outline_style_has_border_not_background(self):
        appearance = build_subtitle_appearance(style="yellow_outline")
        self.assertIsInstance(appearance.border, TextBorderSpec)
        self.assertIsNone(appearance.background)
        self.assertEqual(appearance.color, (1.0, 0.85, 0.0))

    def test_black_box_style_has_background_not_border(self):
        appearance = build_subtitle_appearance(style="black_box")
        self.assertIsInstance(appearance.background, TextBackgroundSpec)
        self.assertIsNone(appearance.border)

    def test_unknown_style_falls_back_to_default(self):
        appearance = build_subtitle_appearance(style="does-not-exist")
        self.assertIsNone(appearance.border)
        self.assertIsNone(appearance.background)

    def test_size_is_passed_through(self):
        appearance = build_subtitle_appearance(size=12.5)
        self.assertEqual(appearance.size, 12.5)


if __name__ == "__main__":
    unittest.main()
