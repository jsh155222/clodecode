"""번들된 ffmpeg/ffprobe 탐지 로직(require_binary) 검증. 실제 ffmpeg는 필요 없음."""

import os
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
                resolved = silence.require_binary("ffmpeg")

            self.assertEqual(resolved, str(fake_exe))

    def test_falls_back_to_path_lookup_when_no_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "ffmpeg" / "bin"  # 존재하지 않음

            with mock.patch.object(silence, "_bundled_binary_dir", return_value=bundled_dir), \
                 mock.patch.object(silence.shutil, "which", return_value="/usr/bin/ffmpeg"):
                resolved = silence.require_binary("ffmpeg")

            self.assertEqual(resolved, "ffmpeg")

    def test_raises_when_neither_bundle_nor_path_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "ffmpeg" / "bin"

            with mock.patch.object(silence, "_bundled_binary_dir", return_value=bundled_dir), \
                 mock.patch.object(silence.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError):
                    silence.require_binary("ffmpeg")


class TestBundledBinaryDirEnvOverride(unittest.TestCase):
    """데스크톱 앱(desktop/main.js)이 쓰기 가능한 사용자 폴더를 가리킬 수 있어야 한다."""

    def test_env_override_takes_precedence_over_default_location(self):
        with mock.patch.dict(os.environ, {"CAPCUT_AUTO_FFMPEG_DIR": "/custom/ffmpeg/bin"}):
            self.assertEqual(silence._bundled_binary_dir(), Path("/custom/ffmpeg/bin"))

    def test_no_env_falls_back_to_repo_relative_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = silence._bundled_binary_dir()
            self.assertTrue(str(result).endswith(str(Path("ffmpeg") / "bin")))


if __name__ == "__main__":
    unittest.main()
