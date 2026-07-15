"""ffmpeg/whisper 없이 run_pipeline() 오케스트레이션 전체를 검증하는 통합 테스트."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capcut_auto import pipeline
from capcut_auto.pipeline import PipelineError, PipelineOptions, run_pipeline
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word


class TestRunPipelineDryRun(unittest.TestCase):
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

            with mock.patch.object(pipeline.silence_mod, "get_duration", return_value=10.0), \
                 mock.patch.object(pipeline.silence_mod, "extract_audio", return_value=str(Path(tmp) / "a.wav")), \
                 mock.patch.object(pipeline.silence_mod, "detect_silence", return_value=[Interval(2.0, 5.0)]), \
                 mock.patch.object(pipeline, "transcribe_audio", return_value=words):
                opts = PipelineOptions(video=str(video_path), draft_name="test_draft", workdir=str(workdir), dry_run=True)
                result = run_pipeline(opts)

            self.assertAlmostEqual(result.total_duration, 10.0)
            self.assertLess(result.kept_duration, 10.0)
            self.assertIsNone(result.draft_name)
            self.assertTrue((workdir / "subtitle.srt").exists())

            srt_text = (workdir / "subtitle.srt").read_text(encoding="utf-8")
            self.assertNotIn("어\n", srt_text)
            self.assertIn("안녕하세요", srt_text)
            self.assertIn("반갑습니다", srt_text)

            report = json.loads((workdir / "report.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(report["total_duration_sec"], 10.0)

    def test_missing_video_raises_pipeline_error(self):
        opts = PipelineOptions(video="/nonexistent/video.mp4", draft_name="x", dry_run=True)
        with self.assertRaises(PipelineError):
            run_pipeline(opts)

    def test_missing_drafts_dir_raises_when_not_dry_run(self):
        words = [Word(0.0, 0.3, "안녕")]
        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "input.mp4"
            video_path.write_bytes(b"fake")
            workdir = Path(tmp) / "work"

            with mock.patch.object(pipeline.silence_mod, "get_duration", return_value=1.0), \
                 mock.patch.object(pipeline.silence_mod, "extract_audio", return_value=str(Path(tmp) / "a.wav")), \
                 mock.patch.object(pipeline.silence_mod, "detect_silence", return_value=[]), \
                 mock.patch.object(pipeline, "transcribe_audio", return_value=words), \
                 mock.patch.object(pipeline, "default_capcut_drafts_dir", return_value=None):
                opts = PipelineOptions(
                    video=str(video_path), draft_name="x", workdir=str(workdir), dry_run=False, capcut_drafts_dir=None
                )
                with self.assertRaises(PipelineError):
                    run_pipeline(opts)

    def test_log_callback_receives_progress_messages(self):
        words = [Word(0.0, 0.3, "안녕")]
        logged = []
        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "input.mp4"
            video_path.write_bytes(b"fake")
            workdir = Path(tmp) / "work"

            with mock.patch.object(pipeline.silence_mod, "get_duration", return_value=1.0), \
                 mock.patch.object(pipeline.silence_mod, "extract_audio", return_value=str(Path(tmp) / "a.wav")), \
                 mock.patch.object(pipeline.silence_mod, "detect_silence", return_value=[]), \
                 mock.patch.object(pipeline, "transcribe_audio", return_value=words):
                opts = PipelineOptions(video=str(video_path), draft_name="x", workdir=str(workdir), dry_run=True)
                run_pipeline(opts, log=logged.append)

        self.assertTrue(any("음성 인식" in m for m in logged))


if __name__ == "__main__":
    unittest.main()
