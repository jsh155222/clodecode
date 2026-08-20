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

    def test_words_squeezed_together_by_a_cut_do_not_overlap(self):
        """실사용자 리포트: 필러워드/무음 컷으로 두 단어 사이 간격이 좁아지면, 원래 길이를
        그대로 유지한 단어들이 새 타임라인에서 서로 겹쳐 pycapcut이 CapCut 드래프트 생성
        자체를 "New segment overlaps with existing segment"로 거부했다. 컷 경계 바로
        양옆의 두 단어(둘 다 원래 길이가 길고, 컷 이후 서로 가까워짐)로 이 상황을 재현한다."""
        # 두 단어 다 원래 길이가 길고(0.8초), 그 사이의 [1.0, 1.6] 구간이 컷되어
        # 새 타임라인에서는 중간점끼리 0.6초밖에 떨어지지 않는다 - 각자 원래 길이(0.8초)를
        # 그대로 유지하면 겹칠 수밖에 없는 상황.
        keep = [Interval(0.0, 1.0), Interval(1.6, 2.6)]
        words = [Word(0.5, 1.3, "keep-A"), Word(1.7, 2.5, "keep-B")]
        result = remap_words_to_new_timeline(words, keep)
        self.assertEqual(len(result), 2)
        self.assertLessEqual(result[0].end, result[1].start)


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
