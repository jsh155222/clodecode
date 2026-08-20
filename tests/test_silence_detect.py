"""detect_silence / _parse_silencedetect_output 파싱 로직 검증. 실제 ffmpeg는 필요 없음."""

import subprocess
import unittest
from unittest import mock

from capcut_auto import silence


class TestParseSilencedetectOutput(unittest.TestCase):
    def test_parses_start_end_pairs(self):
        text = (
            "[silencedetect @ 0x1] silence_start: 1.5\n"
            "[silencedetect @ 0x1] silence_end: 3.25 | silence_duration: 1.75\n"
        )
        intervals = silence._parse_silencedetect_output(text)
        self.assertEqual(len(intervals), 1)
        self.assertAlmostEqual(intervals[0].start, 1.5)
        self.assertAlmostEqual(intervals[0].end, 3.25)

    def test_empty_string_yields_no_intervals(self):
        self.assertEqual(silence._parse_silencedetect_output(""), [])


class TestDetectSilenceHandlesMissingStderr(unittest.TestCase):
    """일부 Windows 환경(백신/EDR이 자식 프로세스 파이프에 개입하는 경우 등)에서는
    capture_output=True를 줬는데도 CompletedProcess.stderr가 None으로 관측된 사례가 있었다
    (실사용자 리포트: '오류: 예상치 못한 오류: 'NoneType' object has no attribute 'splitlines'').
    None이어도 크래시하지 않고 무음 구간 없음으로 처리되어야 한다."""

    def test_none_stderr_does_not_raise(self):
        fake_result = subprocess.CompletedProcess(args=["ffmpeg"], returncode=0, stdout="", stderr=None)
        with mock.patch.object(silence, "require_binary", return_value="ffmpeg"), \
             mock.patch.object(silence.subprocess, "run", return_value=fake_result):
            intervals = silence.detect_silence("audio.wav")
        self.assertEqual(intervals, [])


if __name__ == "__main__":
    unittest.main()
