# capcut-auto

[pyCapCut](https://github.com/GuanYixuan/pyCapCut)을 이용해 CapCut 자동 편집 드래프트를 생성하는 파이프라인입니다.

1. **무음 구간 자동 컷** — ffmpeg `silencedetect`로 조용한 구간을 찾아 제거
2. **버벅임(간투사·반복) 자동 컷** — "어", "음", "그..." 같은 필러워드와 "저 저 저는" 같은 즉시 반복(말더듬)을 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 단어 타임스탬프 기반으로 탐지해 제거
3. **자막 자동 생성** — 컷 편집으로 압축된 새 타임라인에 맞춰 자막(SRT)을 재정렬하고, CapCut 텍스트 트랙으로 삽입

## 동작 원리

```
영상 입력
  → ffmpeg로 오디오 추출 + 무음 구간 탐지
  → faster-whisper로 단어 단위 음성 인식
  → 필러워드 / 반복 발화 탐지
  → 무음 + 필러 + 반복 구간을 합쳐 최종 컷 리스트 계산
  → 컷 편집 후 압축된 타임라인 기준으로 자막 재정렬
  → pycapcut으로 CapCut 드래프트 생성 (영상 트랙 + 자막 트랙)
```

컷/자막 로직(`capcut_auto/timeline.py`, `stutter.py`, `cutlist.py`, `subtitles.py`)은 ffmpeg나 whisper 없이도 순수 함수로 동작하며 `tests/`에서 유닛테스트로 검증됩니다.

CLI(`cli.py`)와 데스크톱 GUI(`gui.py`)는 동일한 `capcut_auto/pipeline.py`의 `run_pipeline()`을 공유합니다.

## 설치

```bash
# 시스템 의존성
brew install ffmpeg        # macOS
# 또는: apt-get install ffmpeg  (Linux)

pip install -r requirements.txt
```

> **주의**: pyCapCut은 리눅스/macOS에서 드래프트 파일 생성은 가능하지만, 실제 CapCut 앱에서 열어 렌더링/내보내기를 하려면 CapCut이 설치된 Windows(또는 지원 OS)로 드래프트 폴더를 옮기거나, 해당 OS에서 이 스크립트를 실행해야 합니다.

## 데스크톱 GUI

CLI 대신 창을 띄워서 사용하고 싶다면 Tkinter GUI를 실행하세요 (Python 표준 라이브러리만 사용하므로 GUI 자체를 위한 추가 설치는 필요 없습니다. Windows/macOS의 python.org 설치판에는 기본 포함되어 있고, 리눅스는 배포판에 따라 `python3-tk` 패키지가 필요할 수 있습니다):

```bash
python -m capcut_auto.gui
```

- **기본 설정** 탭: 영상 파일, 드래프트 이름, CapCut 드래프트 폴더(자동 감지 버튼 제공), 음성 인식 모델/언어, 기능별 on/off, "미리보기만 실행"(dry-run) 체크박스
- **고급 설정** 탭: 무음/필러/반복 탐지 임계값, 자막 줄바꿈 옵션 등 CLI의 모든 튜닝 파라미터
- 실행을 누르면 백그라운드 스레드에서 파이프라인이 돌아가며, 진행 로그가 실시간으로 표시되고 완료/오류 시 요약 팝업이 뜹니다.

pip으로 설치했다면 `capcut-auto-gui` 명령으로도 실행할 수 있습니다(Windows에서는 콘솔 창 없이 실행됨).

## CLI 사용법

```bash
python -m capcut_auto.cli \
  --video input.mp4 \
  --draft-name my_project \
  --capcut-drafts-dir "/path/to/CapCut/User Data/Projects/com.lveditor.draft"
```

`--capcut-drafts-dir`를 생략하면 OS별 기본 경로를 추정합니다(설치 환경에 따라 다를 수 있으니 확인 필요):

- Windows: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
- macOS: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft`

### 먼저 분석만 해보고 싶다면 (`--dry-run`)

CapCut 드래프트를 만들지 않고, 컷 리스트/자막만 생성해서 확인할 수 있습니다.

```bash
python -m capcut_auto.cli --video input.mp4 --draft-name preview --dry-run
```

실행 후 `capcut_auto_work/preview/` 폴더에 다음이 생성됩니다:

- `audio.wav` — 추출된 오디오
- `subtitle.srt` — 컷 편집 반영된 자막
- `report.json` — 원본/편집 후 길이, 컷 구간 목록, 자막 목록

컷 결과가 마음에 들면 `--dry-run` 없이 다시 실행해 실제 드래프트를 생성하세요.

## 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--whisper-model` | `medium` | faster-whisper 모델 크기 (`tiny`~`large-v3`, 클수록 정확하지만 느림) |
| `--language` | `ko` | 인식 언어 |
| `--silence-db` | `-30.0` | 이보다 조용하면 무음으로 간주(dB) |
| `--min-silence` | `0.6` | 이 시간(초) 이상 지속되어야 무음으로 인정 |
| `--silence-edge-padding` | `0.12` | 무음 컷 경계에 남길 정적 여유(초), 클수록 덜 공격적으로 컷 |
| `--max-filler-duration` | `0.6` | 필러워드로 인정할 최대 발화 길이(초) |
| `--repeat-max-gap` | `0.3` | 반복(말더듬)으로 볼 단어 간 최대 간격(초) |
| `--repeat-min-count` | `2` | 반복으로 볼 최소 연속 횟수 |
| `--min-keep-duration` | `0.12` | 컷 사이 잔여 구간이 이보다 짧으면 흡수(깜빡임 방지) |
| `--subtitle-max-chars` | `24` | 자막 한 줄 최대 글자 수 |
| `--disable-silence-cut` / `--disable-filler-cut` / `--disable-repetition-cut` / `--disable-subtitles` | - | 각 기능 개별 비활성화 |

전체 옵션은 `python -m capcut_auto.cli --help`로 확인하세요.

## 한계 및 튜닝 팁

- **필러워드 목록**(`capcut_auto/stutter.py`의 `DEFAULT_FILLER_WORDS`)은 휴리스틱입니다. "그", "이제", "막" 같은 단어는 문맥에 따라 의미 있는 단어일 수도 있어 `--max-filler-duration`으로 발화 길이 기반 오탐을 줄입니다. 필요하면 목록을 프로젝트에 맞게 수정하세요.
- **반복(말더듬) 탐지**는 정확히 같은 단어가 짧은 간격으로 반복될 때만 잡아냅니다("음절 일부만 반복"되는 진짜 말더듬은 탐지하지 못할 수 있음).
- 컷이 너무 잦다면 `--min-silence`를 늘리거나 `--silence-edge-padding`을 늘려 보수적으로 조정하세요.
- 자막 줄바꿈은 whisper 단어 간 공백 기준 근사치입니다. 한국어 어절 단위와 정확히 일치하지 않을 수 있습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

ffmpeg/faster-whisper 없이도 전체 로직(타임라인 병합, 필러/반복 탐지, 자막 재정렬, CLI 배선)이 검증됩니다.
