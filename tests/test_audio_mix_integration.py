"""실제 ffmpeg로 audio_mix 파이프라인을 검증하는 통합 테스트. ffmpeg 없으면 자동 skip."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.audio_mix import apply_multiple_sfx, apply_sfx_at_cuts, ensure_bgm_library, ensure_sfx_library, mix_bgm
from capcut_auto.timeline import Interval

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_video_with_tone(path: str, duration: int = 4) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=green:s=160x120:d={duration}:r=10",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg가 설치되어 있지 않아 통합 테스트를 건너뜁니다.")
class TestAudioMixIntegration(unittest.TestCase):
    def test_ensure_bgm_library_generates_playable_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = ensure_bgm_library(tmp)
            self.assertGreater(len(library), 0)
            for track in library.values():
                self.assertTrue(Path(track.path).exists())
                self.assertGreater(Path(track.path).stat().st_size, 0)

    def test_bgm_library_is_cached_on_second_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = ensure_bgm_library(tmp)
            mtimes_before = {k: Path(v.path).stat().st_mtime for k, v in first.items()}
            second = ensure_bgm_library(tmp)
            mtimes_after = {k: Path(v.path).stat().st_mtime for k, v in second.items()}
            self.assertEqual(mtimes_before, mtimes_after)

    def test_mix_bgm_produces_video_with_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path)
            library = ensure_bgm_library(str(Path(tmp) / "bgm"))

            out_path = str(Path(tmp) / "mixed.mp4")
            mix_bgm(video_path, library["warm"].path, out_path, bgm_volume=0.2)

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)

    def test_mix_bgm_with_voice_intervals_produces_ducked_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path)
            library = ensure_bgm_library(str(Path(tmp) / "bgm"))

            out_path = str(Path(tmp) / "ducked.mp4")
            mix_bgm(
                video_path,
                library["warm"].path,
                out_path,
                bgm_volume=0.2,
                voice_intervals=[Interval(1.0, 2.5)],
                duck_volume_ratio=0.3,
            )

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)

    def test_apply_multiple_sfx_with_distinct_assets_produces_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path)
            sfx = ensure_sfx_library(str(Path(tmp) / "sfx"))

            # 서로 다른 시각에 같은 소스를 각기 다른 "효과음"인 것처럼 두 번 배치해도
            # 실제 ffmpeg가 여러 입력을 처리할 수 있는지 확인 (실제 sfx_recommend.py는
            # 서로 다른 파일을 넘김)
            out_path = str(Path(tmp) / "out.mp4")
            apply_multiple_sfx(video_path, out_path, [(0.5, sfx["pop"]), (2.5, sfx["pop"])])

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)

    def test_apply_multiple_sfx_with_no_placements_copies_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path)
            out_path = str(Path(tmp) / "out.mp4")
            apply_multiple_sfx(video_path, out_path, [])
            self.assertTrue(Path(out_path).exists())

    def test_apply_sfx_at_cuts_with_no_cut_points_copies_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path)
            sfx = ensure_sfx_library(str(Path(tmp) / "sfx"))

            out_path = str(Path(tmp) / "out.mp4")
            apply_sfx_at_cuts(video_path, out_path, [], sfx["pop"])

            self.assertTrue(Path(out_path).exists())

    def test_apply_sfx_at_cuts_with_multiple_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "in.mp4")
            _make_video_with_tone(video_path, duration=4)
            sfx = ensure_sfx_library(str(Path(tmp) / "sfx"))

            out_path = str(Path(tmp) / "out.mp4")
            apply_sfx_at_cuts(video_path, out_path, [1.0, 2.0, 3.0], sfx["pop"])

            self.assertTrue(Path(out_path).exists())
            self.assertGreater(Path(out_path).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
