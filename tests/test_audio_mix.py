import unittest

from capcut_auto.audio_mix import MOOD_CHORDS, MOOD_LABELS, _bgm_volume_expression
from capcut_auto.timeline import Interval


class TestBgmVolumeExpression(unittest.TestCase):
    def test_no_voice_intervals_uses_flat_volume(self):
        expr = _bgm_volume_expression(0.2, [], duck_volume_ratio=0.35)
        self.assertEqual(expr, "volume=0.2")

    def test_voice_intervals_produce_conditional_expression_with_ducked_value(self):
        expr = _bgm_volume_expression(0.2, [Interval(1.0, 2.0)], duck_volume_ratio=0.5)
        self.assertIn("between(t,1.0,2.0)", expr)
        self.assertIn("0.1", expr)  # 0.2 * 0.5 = 0.1 (ducked volume)
        self.assertIn("0.2", expr)  # 기본 볼륨도 표현식에 남아 있어야 함

    def test_multiple_voice_intervals_are_combined_with_plus(self):
        expr = _bgm_volume_expression(0.2, [Interval(1.0, 2.0), Interval(5.0, 6.0)], duck_volume_ratio=0.5)
        self.assertIn("between(t,1.0,2.0)+between(t,5.0,6.0)", expr)


class TestAudioMixMoodTables(unittest.TestCase):
    def test_every_mood_used_by_categories_has_a_chord(self):
        from capcut_auto.categories import CATEGORY_RULES

        used_moods = {rule.default_bgm_mood for rule in CATEGORY_RULES.values()}
        for mood in used_moods:
            self.assertIn(mood, MOOD_CHORDS, f"{mood} 무드에 대응하는 화음이 없습니다")

    def test_every_mood_has_a_label(self):
        for mood in MOOD_CHORDS:
            self.assertIn(mood, MOOD_LABELS)

    def test_chords_are_nonempty_frequency_lists(self):
        for mood, freqs in MOOD_CHORDS.items():
            self.assertGreater(len(freqs), 0, f"{mood} 화음이 비어 있습니다")
            for f in freqs:
                self.assertGreater(f, 0)


if __name__ == "__main__":
    unittest.main()
