import tempfile
import unittest
from pathlib import Path

from capcut_auto.subtitles import (
    group_words_into_lines,
    remap_words_to_new_timeline,
    write_srt,
    _format_srt_timestamp,
)
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word


class TestRemapWords(unittest.TestCase):
    def test_drops_word_fully_inside_cut(self):
        keep = [Interval(0, 2), Interval(5, 8)]
        words = [Word(1.0, 1.5, "keep-me"), Word(3.0, 3.5, "cut-me")]
        result = remap_words_to_new_timeline(words, keep)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "keep-me")

    def test_shifts_word_after_cut(self):
        keep = [Interval(0, 2), Interval(5, 8)]
        words = [Word(6.0, 6.4, "hello")]
        result = remap_words_to_new_timeline(words, keep)
        self.assertEqual(len(result), 1)
        # 6.0 -> new timeline: 2.0(kept before) + (6.0-5.0) = 3.0
        self.assertAlmostEqual(result[0].start, 3.0)
        self.assertAlmostEqual(result[0].end, 3.4)


class TestGroupWordsIntoLines(unittest.TestCase):
    def test_splits_on_large_gap(self):
        words = [Word(0.0, 0.3, "안녕"), Word(2.0, 2.3, "하세요")]
        lines = group_words_into_lines(words, max_gap=0.5)
        self.assertEqual(len(lines), 2)

    def test_groups_close_words_into_one_line(self):
        words = [Word(0.0, 0.3, "안녕"), Word(0.35, 0.7, "하세요")]
        lines = group_words_into_lines(words, max_gap=0.5)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "안녕 하세요")
        self.assertEqual(lines[0].start, 0.0)
        self.assertEqual(lines[0].end, 0.7)

    def test_splits_on_max_chars(self):
        words = [Word(i * 0.5, i * 0.5 + 0.3, "가나다") for i in range(10)]
        lines = group_words_into_lines(words, max_chars=10, max_gap=10, max_duration=100)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(len(line.text), 13)  # 약간의 여유(마지막 단어 포함 경계)


class TestSrtFormatting(unittest.TestCase):
    def test_timestamp_format(self):
        self.assertEqual(_format_srt_timestamp(0), "00:00:00,000")
        self.assertEqual(_format_srt_timestamp(3661.5), "01:01:01,500")

    def test_write_srt_roundtrip(self):
        from capcut_auto.subtitles import SubtitleLine

        lines = [SubtitleLine(0.0, 1.5, "안녕하세요"), SubtitleLine(2.0, 3.0, "반갑습니다")]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_srt(lines, str(Path(tmp) / "out.srt"))
            content = Path(path).read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:01,500", content)
        self.assertIn("안녕하세요", content)
        self.assertIn("2\n", content)


if __name__ == "__main__":
    unittest.main()
