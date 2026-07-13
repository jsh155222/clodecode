"""ffmpeg/whisper 없이 CLI 파이프라인 배선(orchestration)을 검증하는 통합 테스트."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capcut_auto import cli
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word


class TestCliDryRun(unittest.TestCase):
    def test_dry_run_pipeline_produces_report(self):
        words = [
            Word(0.5, 0.8, "어"),  # 필러 -> 컷
            Word(1.0, 1.4, "안녕하세요"),
            Word(6.0, 6.5, "반갑습니다"),  # 무음 뒤 발화
        ]

        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "input.mp4"
            video_path.write_bytes(b"fake")
            workdir = Path(tmp) / "work"

            with mock.patch.object(cli.silence_mod, "get_duration", return_value=10.0), \
                 mock.patch.object(cli.silence_mod, "extract_audio", return_value=str(Path(tmp) / "a.wav")), \
                 mock.patch.object(cli.silence_mod, "detect_silence", return_value=[Interval(2.0, 5.0)]), \
                 mock.patch.object(cli, "transcribe_audio", return_value=words):
                exit_code = cli.main(
                    [
                        "--video", str(video_path),
                        "--draft-name", "test_draft",
                        "--workdir", str(workdir),
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = json.loads((workdir / "report.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(report["total_duration_sec"], 10.0)
            # 무음(2.0-5.0, edge padding 기본 0.12 shrink) + 필러("어") 컷 반영되어 kept < total
            self.assertLess(report["kept_duration_sec"], 10.0)
            self.assertTrue((workdir / "subtitle.srt").exists())
            # 필러 "어"는 컷되어 자막에 남지 않아야 함
            srt_text = (workdir / "subtitle.srt").read_text(encoding="utf-8")
            self.assertNotIn("어\n", srt_text)
            self.assertIn("안녕하세요", srt_text)
            self.assertIn("반갑습니다", srt_text)

    def test_missing_video_returns_error(self):
        exit_code = cli.main(["--video", "/nonexistent.mp4", "--draft-name", "x", "--dry-run"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
