"""faster-whisper 기반 음성 인식 (단어 단위 타임스탬프 포함).

faster-whisper는 무거운 의존성(torch/ctranslate2)이므로 모듈 최상단에서
import하지 않고, 실제로 transcribe()를 호출할 때만 지연 import한다.
이렇게 하면 timeline/stutter/subtitles 같은 순수 로직은 faster-whisper가
설치되어 있지 않아도 독립적으로 테스트할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    language: str = "ko",
    device: str = "auto",
    compute_type: str = "auto",
    vad_filter: bool = True,
) -> List[Word]:
    """오디오를 전사하고 단어 단위 타임스탬프 리스트를 반환한다.

    Requires: pip install faster-whisper
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - 환경 의존적
        raise RuntimeError(
            "faster-whisper가 설치되어 있지 않습니다. `pip install faster-whisper`로 설치하세요."
        ) from exc

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=vad_filter,
    )

    words: List[Word] = []
    for segment in segments:
        segment_words = getattr(segment, "words", None) or []
        for w in segment_words:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(start=float(w.start), end=float(w.end), text=text))
    return words


def words_from_iterable(raw_words: List[dict]) -> List[Word]:
    """딕셔너리 리스트(예: 캐시된 JSON)로부터 Word 리스트를 만든다."""
    return [Word(start=float(w["start"]), end=float(w["end"]), text=str(w["text"])) for w in raw_words]
