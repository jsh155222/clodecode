"""transcribe()의 VAD 재시도 폴백 로직 검증. 실제 faster-whisper 모델은 필요 없음
(faster_whisper 모듈 자체를 가짜로 주입해서 테스트한다)."""

import sys
import types
import unittest
from unittest import mock


class _FakeWord:
    def __init__(self, start, end, word):
        self.start = start
        self.end = end
        self.word = word


class _FakeSegment:
    def __init__(self, words):
        self.words = words


def _install_fake_faster_whisper(transcribe_side_effect):
    """faster_whisper.WhisperModel.transcribe가 transcribe_side_effect(vad_filter)를
    호출하도록 하는 가짜 모듈을 sys.modules에 주입한다."""

    class _FakeWhisperModel:
        def __init__(self, model_size, device="auto", compute_type="auto"):
            self.model_size = model_size

        def transcribe(self, audio_path, language, word_timestamps, vad_filter):
            segments = transcribe_side_effect(vad_filter)
            return segments, object()

    fake_module = types.ModuleType("faster_whisper")
    fake_module.WhisperModel = _FakeWhisperModel
    return mock.patch.dict(sys.modules, {"faster_whisper": fake_module})


class TestTranscribeVadFallback(unittest.TestCase):
    def test_retries_without_vad_when_first_pass_finds_nothing(self):
        """실사용자 리포트: 배경 소음이 섞인(예: 드론/실외) 오디오에서 vad_filter=True가
        실제 대사를 전부 걸러내 '단어 0개'가 나왔다. vad_filter 없이 재시도해서 구제해야
        한다."""
        calls = []

        def side_effect(vad_filter):
            calls.append(vad_filter)
            if vad_filter:
                return []  # VAD가 전부 걸러냄
            return [_FakeSegment([_FakeWord(0.0, 0.5, "안녕")])]

        with _install_fake_faster_whisper(side_effect):
            from capcut_auto.transcribe import transcribe

            words = transcribe("audio.wav")

        self.assertEqual(calls, [True, False])  # 먼저 VAD 켜서 시도, 비었으니 꺼서 재시도
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0].text, "안녕")

    def test_does_not_retry_when_first_pass_succeeds(self):
        calls = []

        def side_effect(vad_filter):
            calls.append(vad_filter)
            return [_FakeSegment([_FakeWord(0.0, 0.5, "안녕")])]

        with _install_fake_faster_whisper(side_effect):
            from capcut_auto.transcribe import transcribe

            words = transcribe("audio.wav")

        self.assertEqual(calls, [True])  # 재시도 없음
        self.assertEqual(len(words), 1)

    def test_still_returns_empty_if_both_passes_find_nothing(self):
        def side_effect(vad_filter):
            return []

        with _install_fake_faster_whisper(side_effect):
            from capcut_auto.transcribe import transcribe

            words = transcribe("audio.wav")

        self.assertEqual(words, [])

    def test_no_retry_when_vad_filter_disabled_from_the_start(self):
        calls = []

        def side_effect(vad_filter):
            calls.append(vad_filter)
            return []

        with _install_fake_faster_whisper(side_effect):
            from capcut_auto.transcribe import transcribe

            transcribe("audio.wav", vad_filter=False)

        self.assertEqual(calls, [False])  # vad_filter가 처음부터 꺼져있으면 재시도할 이유 없음


if __name__ == "__main__":
    unittest.main()
