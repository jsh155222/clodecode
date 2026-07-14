"""실제 ffmpeg + 실제 pycapcut으로 draft_builder를 검증하는 통합 테스트.

ffmpeg나 pycapcut이 없는 환경에서는 자동으로 건너뛴다.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from capcut_auto.draft_builder import build_draft
from capcut_auto.subtitles import SubtitleLine
from capcut_auto.timeline import Interval

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
try:
    import pycapcut  # noqa: F401

    PYCAPCUT_AVAILABLE = True
except ImportError:
    PYCAPCUT_AVAILABLE = False


def _make_synthetic_video(path: str, duration: int = 2) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:rate=10:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo",
            "-t",
            str(duration),
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


@unittest.skipUnless(
    FFMPEG_AVAILABLE and PYCAPCUT_AVAILABLE,
    "ffmpeg 또는 pycapcut이 설치되어 있지 않아 통합 테스트를 건너뜁니다.",
)
class TestDraftBuilderIntegration(unittest.TestCase):
    def test_two_drafts_in_same_folder_get_distinct_ids_and_correct_meta(self):
        """pycapcut 0.0.3은 draft_content.json의 id / draft_meta_info.json의
        draft_id를 매번 동일한 번들 템플릿 값으로 남겨둔다 (실제로 겪은 문제).
        같은 CapCut 드래프트 폴더에 여러 드래프트를 만들어도 서로 다른 id를 갖고,
        draft_meta_info.json의 이름/길이가 실제 값으로 채워지는지 확인한다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / "test.mp4")
            _make_synthetic_video(video_path)

            drafts_dir = str(Path(tmp) / "drafts")
            Path(drafts_dir).mkdir()

            names = ("draft_one", "draft_two")
            for name in names:
                build_draft(
                    video_path=video_path,
                    keep_intervals=[Interval(0.0, 2.0)],
                    subtitle_lines=[SubtitleLine(start=0.0, end=1.0, text="hello")],
                    draft_name=name,
                    capcut_drafts_dir=drafts_dir,
                    hook_text="hook!",
                )

            all_ids = set()
            for name in names:
                draft_dir = Path(drafts_dir) / name
                content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
                meta = json.loads((draft_dir / "draft_meta_info.json").read_text(encoding="utf-8"))

                self.assertNotEqual(content["id"], "91E08AC5-22FB-47e2-9AA0-7DC300FAEA2B")
                self.assertNotEqual(meta["draft_id"], "792BD5DA-E961-4821-B10E-F51E4683DEC0")
                self.assertEqual(meta["draft_name"], name)
                self.assertEqual(meta["tm_duration"], content["duration"])
                self.assertGreater(content["duration"], 0)
                # 영상 + 자막 + 훅, 총 3개 트랙이 실제로 생성됐는지 확인
                self.assertEqual(len(content["tracks"]), 3)

                all_ids.add(content["id"])
                all_ids.add(meta["draft_id"])

            self.assertEqual(len(all_ids), 4, "두 드래프트가 id를 공유하면 안 됨")


if __name__ == "__main__":
    unittest.main()
