"""번들된 ffmpeg/ffprobe 탐지 로직(_require_binary) 검증. 실제 ffmpeg는 필요 없음."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capcut_auto import silence


class TestRequireBinary(unittest.TestCase):
    def test_prefers_bundled_binary_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "ffmpeg" / "bin"
            bundled_dir.mkdir(parents=True)
            fake_exe = bundled_dir / "ffmpeg.exe"
            fake_exe.write_text("fake")

            with mock.patch.object(silence, "_bundled_binary_dir", return_value=bundled_dir), \
                 mock.patch.object(silence.platform, "system", return_value="Windows"):
                resolved = silence._require_binary("ffmpeg")

            self.assertEqual(resolved, str(fake_exe))

    def test_falls_back_to_path_lookup_when_no_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "ffmpeg" / "bin"  # 존재하지 않음

            with mock.patch.object(silence, "_bundled_binary_dir", return_value=bundled_dir), \
                 mock.patch.object(silence.shutil, "which", return_value="/usr/bin/ffmpeg"):
                resolved = silence._require_binary("ffmpeg")

            self.assertEqual(resolved, "ffmpeg")

    def test_raises_when_neither_bundle_nor_path_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "ffmpeg" / "bin"

            with mock.patch.object(silence, "_bundled_binary_dir", return_value=bundled_dir), \
                 mock.patch.object(silence.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError):
                    silence._require_binary("ffmpeg")


if __name__ == "__main__":
    unittest.main()
