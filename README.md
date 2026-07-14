# capcut-auto

[pyCapCut](https://github.com/GuanYixuan/pyCapCut)을 이용해 CapCut 자동 편집 드래프트를 생성하는 파이프라인입니다.

1. **무음 구간 자동 컷** — ffmpeg `silencedetect`로 조용한 구간을 찾아 제거
2. **버벅임(간투사·반복) 자동 컷** — "어", "음", "그..." 같은 필러워드와 "저 저 저는" 같은 즉시 반복(말더듬)을 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 단어 타임스탬프 기반으로 탐지해 제거
3. **자막 자동 생성** — 컷 편집으로 압축된 새 타임라인에 맞춰 자막(SRT)을 재정렬하고, CapCut 텍스트 트랙으로 삽입

> 참고: CapCut 앱에는 이미 "무음 감지"와 "자동 캡션" 기능이 내장되어 있어 설치 없이 버튼 클릭만으로 쓸 수 있습니다. 이 프로젝트는 그와 별개로 **필러워드/반복(말더듬) 탐지**와 **여러 영상 일괄 자동 처리**처럼 CapCut UI에는 없는 커스텀 로직이 필요한 경우를 위한 것입니다.

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

## 설치 (Windows, 제일 쉬운 방법)

1. 이 저장소를 ZIP으로 다운로드해 원하는 폴더에 압축을 풉니다 (GitHub 페이지의 초록색 "Code" → "Download ZIP").
2. 압축을 푼 폴더 안의 **`install.bat`을 더블클릭**합니다. (처음 한 번만 실행하면 됩니다)
   - 파이썬이 없으면 자동으로 설치를 시도합니다 (winget 필요, Windows 10/11 대부분에 기본 내장).
   - 필요한 파이썬 패키지(faster-whisper 등)와 ffmpeg를 자동으로 내려받아 이 폴더 안에 넣어줍니다. 시스템 PATH를 건드리지 않으므로 다른 프로그램에 영향이 없습니다.
   - 용량이 커서(약 0.5~1GB) 인터넷 속도에 따라 몇 분 걸릴 수 있습니다.
   - 마지막에 바탕화면 바로가기를 만들지 물어봅니다.
3. 설치가 끝나면, 그 다음부터는 **`run.bat`**(또는 바탕화면 바로가기)을 더블클릭하면 바로 앱이 실행됩니다.

> 이 설치 스크립트는 아직 실제 Windows 환경에서 검증되지 못했습니다. 실행 중 오류 메시지가 뜨면 그 내용을 그대로 알려주시면 바로 고쳐드리겠습니다.

### 수동 설치 (Windows 외 OS, 또는 스크립트가 안 될 때)

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

## 웹앱 (카테고리별 AI 자동 편집 / AI 촬영 가이드)

`webapp/`에 React 기반 웹 UI가 있습니다. 모드 선택(AI 자동 편집 / AI 촬영 가이드) → 카테고리 선택
(살림/청소/음식/육아/뷰티/여행/캠핑) → 두 가지 흐름 중 하나로 이어집니다:

- **AI 자동 편집**: 9단계 마법사(영상 불러오기 → 자동 분석 → 컷 검토 → 화면 보정 → 자막·훅 →
  소리 → 최종 확인 → 내보내기)
- **AI 촬영 가이드**: 주제/제품/목표 길이 등을 입력하면 카테고리에 맞는 앵글·촬영 순서(샷 리스트)를
  생성. 결과 화면에서 "이 계획으로 영상 편집 시작"을 누르면 카테고리·주제를 그대로 들고 AI 자동
  편집으로 넘어가고, 1단계부터 촬영 계획을 접었다 펼 수 있는 참고 패널로 계속 볼 수 있다.

`capcut_auto/server.py`(FastAPI)가 백엔드로 위 파이썬 엔진을 REST API로 감쌉니다.

**둘 다 띄워야 합니다** (CLI/GUI와는 별개의 실행 방식):

```bash
# 1) 백엔드 (터미널 1)
pip install -r requirements.txt
uvicorn capcut_auto.server:app --port 8000

# 2) 프론트엔드 (터미널 2)
cd webapp
npm install
npm run dev   # http://localhost:5173 접속
```

> 프론트엔드를 5173이 아닌 다른 포트로 띄우면 `server.py`의 CORS 설정(`allow_origins`)과 맞지 않아
> 모든 API 호출이 막힙니다. 포트를 바꿔야 한다면 `capcut_auto/server.py`도 함께 수정하세요.

**현재 정직하게 밝혀둘 한계**:
- 화면 보정(5단계)은 딥러닝 색보정이 아니라 ffmpeg의 `signalstats`/`eq`/`vidstab` 필터를 쓴
  고전적 영상처리입니다 (결정론적: 같은 입력엔 항상 같은 보정값).
- 배경음(7단계)은 실제 음원이 아니라 ffmpeg로 절차적으로 만든 화음 루프 플레이스홀더입니다.
- 훅 문구(6단계)는 LLM이 아니라 카테고리별 키워드 + 문장 템플릿 조합입니다 (API 키 인프라가
  아직 없음).
- MODE 2(AI 촬영 가이드)의 앵글/촬영 순서 생성도 LLM이 아니라 카테고리별 앵글 템플릿(6~8개) +
  목표 길이에 따른 샷 개수 조절 규칙입니다. 템플릿에 없는 세부 상황은 다소 일반적인 문구로 나옵니다.
- 프로젝트 상태는 서버 프로세스 메모리에만 있어 서버를 재시작하면 진행 중이던 작업이 사라집니다.
- 이 프로젝트가 만든 CapCut 드래프트는 리눅스/macOS에서 생성만 가능하며(파이썬으로 파일만 생성),
  실제 CapCut 앱에서 열어보는 것은 이 환경(리눅스 컨테이너, CapCut 미설치)에서는 검증하지 못했습니다.
  드래프트 파일의 최상위 id/메타 정보는 pycapcut 실제 소스를 직접 읽어 구조를 확인하고 여러 개를
  생성해도 서로 다른 id를 갖도록 고쳤지만, CapCut 앱이 이 파일을 실제로 어떻게 처리하는지는
  실사용자가 Windows/Mac에서 열어봐야 최종 확인됩니다.

**테스트**:

```bash
python -m unittest tests.test_server -v   # 백엔드 API (mock 기반, 23개)
cd webapp && npx vitest run                # 프론트엔드 (39개)
```

## AI 자동 편집 핵심 기능 (capcut_auto/ai/, 진행 중)

실제 Claude API(Structured Outputs)를 호출해 영상 구조 분석, 컷 후보 판단(신뢰도/맥락
위험도 포함), 자막 최적화·강조, 훅 후보 생성을 수행하는 새 엔진 레이어입니다.

- **아직 REST 엔드포인트나 웹앱 UI에 연결되지 않았습니다.** 이번 단계는 엔진 코드와
  테스트까지만 포함하며, `server.py`의 3/4/6단계는 여전히 기존 규칙 기반 로직만 씁니다.
- 사용하려면 `ANTHROPIC_API_KEY` 환경변수가 필요합니다(코드에는 하드코딩되어 있지 않고,
  프론트엔드에도 절대 노출되지 않습니다).
- AI 호출이 재시도/스키마 수정 요청까지 실패하면 해당 기능만 예외(`AiModuleError`)를
  던지며, 각 모듈은 기존 규칙 기반 기능(무음/필러 탐지, 템플릿 훅 등)으로 폴백할 수 있게
  설계되어 있습니다.
- 실제 Claude API 호출 자체(진짜 키로 정상 응답을 받는지)는 이 저장소의 개발 환경에
  API 키가 없어 검증하지 못했습니다. 대신 가짜(fake) Anthropic 클라이언트로 재시도/
  JSON 오류/스키마 오류/네트워크 오류·타임아웃 등 14가지 시나리오를 테스트했습니다.

```bash
python -m unittest tests.test_ai_client tests.test_ai_cut_candidates \
  tests.test_ai_cut_apply tests.test_ai_timeline_recalc \
  tests.test_ai_subtitle_optimizer tests.test_ai_subtitle_highlight \
  tests.test_ai_hook tests.test_ai_fallback_and_category -v   # 73개
```

## 카테고리별 규칙 (category-rules/)

카테고리마다 별도의 앱이나 코드 분기를 두지 않습니다. `category-rules/*.json`
(살림/청소/음식/육아/뷰티/여행/캠핑 + 공통 규칙, 총 8개 파일)이 유일한 데이터 소스이고,
`capcut_auto/category_rules.py`가 이를 읽어 위 AI 엔진에 그대로 전달합니다. 새 카테고리를
추가하거나 규칙을 조정할 때 파이썬 코드를 건드릴 필요 없이 JSON 파일만 고치면 됩니다.

각 파일은 다음 필드를 담습니다: `protectedMoments`(보호 구간), `removableMoments`(삭제
후보), `preferredPacing`(SLOW/MEDIUM/FAST), `subtitleDensity`(LOW/MEDIUM/HIGH),
`preserveNaturalAudio`(자연음 보호 여부), `preferredShotTypes`(추천 구도),
`discouragedSoundEffects`(지양할 효과음), `safetyChecks`(카테고리별 안전 규칙),
`shootingGuideRules`(촬영 가이드 규칙). `common.json`의 7개 공통 규칙은 모든 카테고리에
항상 함께 적용됩니다.

**정직하게 밝혀둘 부분**: 사용자가 명시적으로 제시한 보호 구간/삭제 후보/규칙/추천 구도는
그대로 반영했습니다. 반면 `preferredPacing`·`subtitleDensity`처럼 명시되지 않은 값은
카테고리 성격에 맞춰 합리적으로 추론해 채웠습니다(예: 정보량이 많은 음식 카테고리는
자막 밀도 HIGH, 무음 컷 여유를 크게 둔 여행/캠핑/육아는 페이싱 SLOW).

```bash
python -m unittest tests.test_category_rules -v   # 33개
```
