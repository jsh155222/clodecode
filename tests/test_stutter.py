import unittest

from capcut_auto.stutter import detect_filler_words, detect_repetitions
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word


class TestDetectFillerWords(unittest.TestCase):
    def test_matches_default_filler(self):
        words = [Word(0.0, 0.3, "어"), Word(0.5, 1.0, "안녕하세요")]
        result = detect_filler_words(words)
        self.assertEqual(result, [Interval(0.0, 0.3)])

    def test_ignores_long_duration_match(self):
        # "그"가 필러 목록에 있어도 너무 길게 발화되면(의미 있는 단어일 가능성) 제외
        words = [Word(0.0, 1.5, "그")]
        result = detect_filler_words(words, max_filler_duration=0.6)
        self.assertEqual(result, [])

    def test_custom_filler_list(self):
        words = [Word(0.0, 0.2, "웁스")]
        result = detect_filler_words(words, filler_words=["웁스"])
        self.assertEqual(result, [Interval(0.0, 0.2)])


class TestDetectRepetitions(unittest.TestCase):
    def test_detects_simple_repeat(self):
        words = [
            Word(0.0, 0.2, "그"),
            Word(0.25, 0.45, "그"),
            Word(0.5, 1.0, "그거는"),
        ]
        result = detect_repetitions(words, max_gap=0.3, min_repeats=2)
        # 첫 번째 "그"만 컷 대상 (마지막 반복은 유지)
        self.assertEqual(result, [Interval(0.0, 0.2)])

    def test_no_repeat_when_gap_too_large(self):
        words = [Word(0.0, 0.2, "그"), Word(1.0, 1.2, "그")]
        result = detect_repetitions(words, max_gap=0.3, min_repeats=2)
        self.assertEqual(result, [])

    def test_triple_repeat_cuts_first_two(self):
        words = [
            Word(0.0, 0.2, "저"),
            Word(0.22, 0.4, "저"),
            Word(0.42, 0.6, "저"),
            Word(0.65, 1.2, "저기요"),
        ]
        result = detect_repetitions(words, max_gap=0.3, min_repeats=2)
        self.assertEqual(result, [Interval(0.0, 0.4)])

    def test_no_false_positive_on_distinct_words(self):
        words = [Word(0.0, 0.3, "안녕"), Word(0.35, 0.7, "하세요")]
        result = detect_repetitions(words)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
