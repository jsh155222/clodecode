"""CLI 배선(argparse -> PipelineOptions -> run_pipeline) 검증."""

import unittest
from unittest import mock

from capcut_auto import cli
from capcut_auto.pipeline import PipelineError, PipelineResult


class TestCliWiring(unittest.TestCase):
    def test_builds_options_and_delegates_to_pipeline(self):
        captured = {}

        def fake_run_pipeline(opts, log):
            captured["opts"] = opts
            log("hello")
            return PipelineResult(
                total_duration=1, kept_duration=1, removed_duration=0, removed_pct=0,
                num_cuts=0, num_subtitle_lines=0, report_path="r.json", srt_path=None, draft_name=None,
            )

        with mock.patch.object(cli, "run_pipeline", side_effect=fake_run_pipeline):
            exit_code = cli.main(
                [
                    "--video", "in.mp4",
                    "--draft-name", "proj",
                    "--whisper-model", "small",
                    "--language", "en",
                    "--silence-db", "-25",
                    "--repeat-min-count", "3",
                    "--disable-subtitles",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        opts = captured["opts"]
        self.assertEqual(opts.video, "in.mp4")
        self.assertEqual(opts.draft_name, "proj")
        self.assertEqual(opts.whisper_model, "small")
        self.assertEqual(opts.language, "en")
        self.assertEqual(opts.silence_db, -25.0)
        self.assertEqual(opts.repeat_min_count, 3)
        self.assertTrue(opts.disable_subtitles)
        self.assertTrue(opts.dry_run)

    def test_pipeline_error_prints_message_and_returns_1(self):
        with mock.patch.object(cli, "run_pipeline", side_effect=PipelineError("boom")):
            exit_code = cli.main(["--video", "in.mp4", "--draft-name", "proj", "--dry-run"])
        self.assertEqual(exit_code, 1)

    def test_missing_video_file_returns_1(self):
        # run_pipeline은 mock하지 않음: 실제 파일 존재 검사가 PipelineError로 이어지는지 확인
        exit_code = cli.main(["--video", "/nonexistent/video.mp4", "--draft-name", "x", "--dry-run"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
