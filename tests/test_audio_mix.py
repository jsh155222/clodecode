import unittest

from capcut_auto.audio_mix import MOOD_CHORDS, MOOD_LABELS


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
