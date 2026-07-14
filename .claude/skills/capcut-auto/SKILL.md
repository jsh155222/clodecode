---
name: capcut-auto
description: Use when working on this repo's capcut_auto/ pycapcut-based CapCut auto-editing engine (silence/filler-word/stutter auto-cut, auto-subtitles, visual correction, audio mixing, hook generation, shooting-guide/shot-list generation), its FastAPI backend (server.py), the webapp/ React frontend (mode/category selection, 9-step AUTO_EDIT wizard, SHOOTING_GUIDE form + result), its Tkinter GUI/CLI, or its Windows install.bat/run.bat installer. Also use when the user asks in Korean or English to build/extend/debug "CapCut 자동 편집", "무음 컷", "버벅임/필러워드 컷", "자막 자동 생성", "화면 보정", "배경음/효과음", "훅 문구", "촬영 가이드/앵글/촬영 순서", a "pycapcut" automation, or the webapp/backend integration, or reports install.bat/run.bat errors. Trigger even if they don't name the file paths directly - match on the task shape, not just exact keywords.
---

# capcut-auto: pycapcut CapCut 자동 편집 엔진 + 웹앱

이 저장소는 두 개의 큰 부분으로 이루어져 있다:

1. **`capcut_auto/`** (Python) — 무음/필러워드/말더듬 자동 컷, 자막 생성, 화면 보정(밝기/대비/흔들림),
   배경음·효과음 믹싱, 훅 문구 생성, [pycapcut](https://github.com/GuanYixuan/pyCapCut)으로 CapCut
   드래프트 생성까지 담당하는 처리 엔진. CLI(`cli.py`)와 Tkinter GUI(`gui.py`)가 이 엔진을 로컬에서
   직접 쓰고, **FastAPI 백엔드(`server.py`)**가 같은 엔진을 REST API로 노출해 웹 프론트엔드가 쓸 수 있게 한다.
2. **`webapp/`** (React 19 + TypeScript + Vite) — 모드 선택(AI 자동 편집/AI 촬영 가이드) → 카테고리 선택 →
   MODE 1의 9단계 마법사(영상 불러오기~내보내기) UI. `server.py`를 HTTP로 호출한다.

이 스킬은 이 프로젝트를 다루는 모든 세션에서 반복 조사를 피하기 위해, 이미 검증된
사실과 흔한 실패 지점을 요약한다. **아래 내용을 다시 처음부터 조사하지 말고 그대로 신뢰할 것.**

## 아키텍처 (한눈에)

```
capcut_auto/
  timeline.py         구간(Interval) 병합/패딩/역산 - 순수 함수
  silence.py          ffmpeg 오디오 추출 + silencedetect, ffmpeg/ffprobe 바이너리 탐지(require_binary)
  transcribe.py        faster-whisper 단어 단위 음성 인식 (지연 import)
  stutter.py           필러워드/반복(말더듬) 탐지 - 순수 함수
  cutlist.py           위 세 소스를 합쳐 최종 keep/cut 구간 계산 (CutlistConfig)
  subtitles.py          컷 반영 자막 리타이밍 + SRT 생성 - 순수 함수
  categories.py         ContentCategory enum(LIVING/CLEANING/FOOD/PARENTING/BEAUTY/TRAVEL/CAMPING),
                        카테고리별 CutlistConfig/훅 키워드/BGM 무드 (CATEGORY_RULES)
  hooks.py              카테고리+주제 → 훅 문구 후보 (템플릿 기반, LLM 아님 - 아래 참고)
  shooting_guide.py      MODE 2용: 카테고리+주제+제품/상황+목표 길이 → 앵글/촬영 순서(ShootingPlan)
                        생성 (역시 템플릿 기반, LLM 아님). project_store/서버 상태 전혀 안 씀 -
                        영상 파일이 없는 완전히 별도 흐름이라 순수 함수로 독립시킴
  visual_correction.py  ffmpeg 고전 영상처리: signalstats 밝기 측정 → eq 필터 자동 보정,
                        libvidstab 2-pass 흔들림 안정화 (딥러닝 아님, 결정론적)
  audio_mix.py           배경음(무드별 화음 루프, ffmpeg lavfi로 절차적 생성) + 컷 전환 효과음,
                        ffmpeg amix/adelay/aloop 믹싱 파이프라인
  draft_builder.py       pycapcut으로 CapCut 드래프트 생성 (video 트랙 + 자막 text 트랙 +
                        선택적 hook_text 전용 text 트랙)
  project_store.py       서버용 인메모리 프로젝트 상태 저장소 (Project/CutCandidate/JobState) - DB 없음
  server.py              FastAPI 백엔드. MODE 1의 3~9단계를 위 모듈들에 연결하는 REST API (아래 표 참고)
  pipeline.py             PipelineOptions/PipelineResult/run_pipeline() - CLI/GUI 전용 단일 파이프라인
                          (server.py는 이걸 쓰지 않고 각 단계를 개별 호출 - 사용자가 단계 사이에
                          검토/수정할 수 있어야 하기 때문)
  cli.py / gui.py         기존 CLI/Tkinter GUI, run_pipeline() 기반, 그대로 유지됨
tests/                    91개 유닛테스트. ffmpeg/whisper/pycapcut 없이도 순수 로직은 전부 통과.
                          test_*_integration.py는 실제 ffmpeg 있을 때만 돌아감(skipUnless)
install.bat / run.bat     Windows 원클릭 설치/실행 (CLI/GUI용, 웹앱과는 별개)

webapp/
  src/api/client.ts        server.py의 모든 엔드포인트에 대응하는 fetch 래퍼
  src/hooks/useJobPolling.ts  "POST로 시작 → GET으로 폴링" 패턴 공용 훅 (analyze/correction/audio/export)
  src/state/ProjectContext.tsx  mode/category를 localStorage에 저장 (프로젝트 = 현재 진행 중인 것 1개)
  src/screens/StartScreen.tsx      모드 카드 2개
  src/screens/AutoEditScreen.tsx    9단계 오케스트레이션. 1~2단계 완료 시 POST /api/projects로
                                   프로젝트 생성 → projectId를 3~9단계에 내려줌
  src/screens/steps/Step1~9*.tsx    각 단계. 3,5,7,9는 useJobPolling으로 백엔드 작업 실행,
                                   4,6은 동기 CRUD, 8은 요약 조회
  src/screens/ShootingGuideScreen.tsx  MODE 2 입력 폼 + 빈 결과 화면 (계획 생성 로직은 아직 없음 - 의도된 범위)
```

## server.py REST API

MODE 1은 전부 `/api/projects/{id}/...` (project_store 상태 기반):

| 메서드/경로 | 용도 |
|---|---|
| `POST /api/projects` | multipart: video 파일 + category + topic → 프로젝트 생성 |
| `POST`/`GET .../analyze` | 3단계: 무음/필러/반복 탐지 + whisper 전사 (백그라운드 스레드+폴링) |
| `GET`/`PATCH .../cuts` | 4단계: 컷 후보 조회/토글 (토글 시 keep_intervals·자막 즉시 재계산) |
| `POST`/`GET .../correction` | 5단계: 화면 보정 (visual_correction.auto_correct, 폴링) |
| `GET`/`PATCH .../subtitles`, `GET .../hooks`, `PATCH .../hook` | 6단계: 자막 수정, 훅 문구 추천/선택 |
| `GET .../bgm-library`, `PATCH .../audio-settings`, `POST`/`GET .../audio` | 7단계: 배경음/효과음 (폴링) |
| `GET .../summary` | 8단계: 지금까지 선택 요약 |
| `POST`/`GET .../export` | 9단계: draft_builder.build_draft 호출 (폴링) |

MODE 2는 완전히 별도, **상태 없는(stateless) 단일 엔드포인트**:

| 메서드/경로 | 용도 |
|---|---|
| `POST /api/shooting-guide` | topic/category/productOrSituation/targetDuration(필수) + location/equipment/faceOnCamera/mustShowScenes/availableTime/notes(선택) → `shooting_guide.generate_shooting_plan()` 호출, 앵글/촬영 순서(ShootingPlan) 즉시 반환. 빠른 순수 함수라 폴링 불필요 |

모든 "무거운" 단계(analyze/correction/audio/export)는 **같은 패턴**: POST가 스레드를 띄우고 즉시
`{"status":"running"}` 반환, 같은 경로 GET으로 `{status, log, error}`를 폴링. `Project.job(name)`이
`JobState`를 관리한다. 상태는 **프로세스 메모리에만** 있음 — 서버 재시작하면 진행 중이던 프로젝트가
사라진다 (의도된 범위 제한, 로컬 1인 도구라 DB 없이 시작함).

## 이미 검증된 사실 (재조사 불필요)

- **pycapcut 실제 API는 draft_builder.py와 정확히 일치함을 실제 설치해서 확인함** (자세한 시그니처는
  코드 참고). PyPI의 pycapcut 최신 버전은 **0.0.3**이 최대치 (`>=0.1.0`처럼 존재하지 않는 버전을
  요구하면 `pip install`이 그 자리에서 실패한다 - 실제로 겪은 버그).
- **draft_builder.build_draft()의 hook_text 기능도 실제 pycapcut으로 검증함**: hook_text를 주면
  자막 트랙과 별개인 "hook" text 트랙을 추가로 만들어(`add_track` 한 번 더) 0초~hook_duration초에
  더 큰 텍스트(기본 size*1.5)로 넣는다. 자막과 겹쳐도 트랙이 다르므로 문제없음.
- **visual_correction.py, audio_mix.py 전부 실제 ffmpeg로 end-to-end 검증함** (합성 테스트 영상으로
  `analyze_brightness`→`compute_correction_params`→`apply_brightness_correction`→`stabilize`,
  `ensure_bgm_library`→`mix_bgm`→`apply_sfx_at_cuts`까지 전부 실행해 출력 파일 생성 확인).
  이 ffmpeg 빌드는 `--enable-libvidstab`이 포함되어 있어 `vidstabdetect`/`vidstabtransform` 필터를
  실제로 쓸 수 있다(설치 시 반드시 확인할 것 - 없으면 5단계가 통째로 실패함).
- **audio_mix.py는 라이선스 있는 실제 음원을 쓰지 않는다** — ffmpeg lavfi로 절차적으로 생성한
  화음 루프(무드별 sine 조합)가 "배경음"이다. 실제 음원으로 바꾸려면 `MOOD_CHORDS`에 대응하는
  실제 파일 경로를 `ensure_bgm_library()`가 반환하도록 바꾸면 됨(믹싱 파이프라인 자체는 안 바뀜).
- **hooks.py도 LLM이 아니라 카테고리 키워드(categories.py) + 문장 템플릿 조합**이다. API 키 인프라가
  프로젝트에 전혀 없어서(환경변수/키 관리 전무) 이렇게 시작함. 실제 LLM 연결 시
  `generate_hook_suggestions(topic, category, max_suggestions)` 시그니처만 유지하고 내부만 바꾸면 됨.
- **server.py는 FastAPI TestClient로 91개 백엔드+엔진 테스트 중 18개(`tests/test_server.py`)를
  실제로 mock 기반 검증함** — 이 과정에서 실제 버그(`library.get(mood, library["neutral"])`가
  "neutral" 키 없으면 KeyError 나는 문제, 파이썬은 기본값 인자를 즉시 평가함)를 잡아 고침.
  이런 패턴(`.get(key, dict[fallback_key])`)은 항상 `.get(key) or .get(fallback) or ...`로 바꿀 것.
- **웹앱↔백엔드 전체 흐름을 실제 uvicorn 서버 + 실제 vite dev 서버 + Playwright로 진짜 검증함**:
  10초 합성 영상을 실제로 업로드해서 1~9단계를 전부 브라우저로 진행, 최종적으로 진짜 CapCut
  드래프트가 생성되고(비디오 3세그먼트로 정확히 컷 분할됨, 자막+훅 트랙 정상) `duration`이 10s→5.9s로
  올바르게 줄어든 것까지 확인함. **whisper 전사만 mock**(huggingface.co가 이 개발 환경에서
  차단되어 있어서 - 아래 참고) 하고 나머지(ffmpeg 무음탐지/화면보정/오디오믹싱, pycapcut 내보내기)는
  전부 진짜로 돌렸다.
- **CORS 주의**: `server.py`는 `http://localhost:5173`/`http://127.0.0.1:5173`만 허용한다(Vite 기본 포트).
  다른 포트로 `npm run dev -- --port XXXX`를 실행하면 프론트엔드가 백엔드를 호출할 때 CORS 에러로
  전부 막힌다 — 이걸 실제로 겪었음. 포트를 바꿔야 한다면 `server.py`의 `allow_origins`도 같이 바꿀 것.
- **MODE 2(shooting_guide.py + `/api/shooting-guide`)도 실제 uvicorn+vite+Playwright로 검증함**:
  카테고리별 앵글 템플릿, 목표 길이별 샷 개수 스케일링(`_select_templates`), `mustShowScenes`가
  마지막 샷 앞에 정확히 삽입되는 것, `faceOnCamera=false`일 때 FACE_TALK이 손 클로즈업+내레이션
  제안으로 바뀌는 것, 장비 키워드 매칭 팁, 촬영 가능 시간 부족 경고까지 브라우저에서 실제로 확인함.
  MODE 1과 달리 project_store를 안 쓰는 완전 stateless 엔드포인트라 폴링/작업 상태 관리가 없다.
- **faster-whisper 모델 다운로드(huggingface.co), ffmpeg 다운로드(gyan.dev)만 이 개발 샌드박스에서
  네트워크 정책상 차단되어 미검증** - 표준적인 방식이라 인터넷 연결 있는 일반 환경에서는 정상 동작할
  것으로 신뢰해도 됨. 이 두 가지를 검증해야 하면 실제 사용자 PC에서만 가능.
- **GUI(Tkinter)는 Xvfb + `apt-get install python3-tk`로 실제 창을 띄워 검증함** (기본 파이썬
  인터프리터엔 tkinter가 없을 수 있으니 `python3.12` 등 tk가 포함된 버전을 따로 써야 함).
  `ttk.Button`의 `["state"]` 값은 `str()`로 감싸야 `"disabled"`/`"normal"`과 비교 가능함(Tcl 객체).

## 흔한 실패 지점과 원인 (실제로 겪은 버그들)

1. **install.bat/run.bat 검은 창이 바로 사라짐** → LF 줄바꿈 문제. `file install.bat`로 CRLF 확인.
2. **cmd.exe가 echo 텍스트를 명령어로 착각** → 괄호 `(` `)` 이스케이프 누락. `^(...^)` 사용.
3. **`pip install`이 `No matching distribution`으로 실패** → requirements.txt 버전이 PyPI 실제 최신보다
   높음. `pip index versions <패키지>`로 먼저 확인.
4. **바탕화면 바로가기 한글 파일명 인코딩 깨짐** → ASCII 파일명 사용.
5. **`dict.get(key, dict[fallback])` 패턴에서 KeyError** → 파이썬은 기본값 인자(`dict[fallback]`)를
   `key`가 존재하든 말든 항상 먼저 평가한다. `.get(key) or .get(fallback)`으로 바꿀 것.
6. **웹앱에서 백엔드 호출이 전부 CORS 에러로 실패** → 프론트엔드를 5173이 아닌 다른 포트로 띄운 경우.
   `server.py`의 CORS 허용 origin과 `npm run dev`의 실제 포트가 일치하는지 항상 먼저 확인.
7. **Node/tsc 빌드에서 `Cannot find name 'node:fs'` 등** → `webapp/tsconfig.app.json`의
   `compilerOptions.types`에 `"node"`가 빠지면 `src/` 아래에서 Node 내장 모듈 타입을 못 찾는다
   (테스트 파일이 `node:fs` 등을 직접 쓸 때 발생).
8. **RTL(`@testing-library/react`)에서 `getByRole('button', {name: '살림'})` 같은 정확 문자열 매칭이
   선택 후 실패** → `CategoryCard`가 선택되면 접근성 이름에 "선택됨"이 추가되어 `'살림'` !=
   `'살림 선택됨'`. 선택 상태가 바뀔 수 있는 요소는 항상 정규식(`/살림/`)으로 조회할 것.
9. **server.py를 고치고 실제 서버로 검증하는데 새 엔드포인트가 계속 404** → 십중팔구 **예전 서버
   프로세스가 코드 수정 전 상태로 아직 포트를 붙잡고 있는 것**(uvicorn은 코드 변경 시 자동 리로드
   안 함, `--reload` 안 쓰는 한). `lsof -i :8000` 또는 `ps aux | grep run_server`로 실제 PID를 확인해
   확실히 죽이고 나서 재시작할 것. `pkill -f uvicorn` 같은 패턴 매칭은 이 환경에서 가끔 조용히
   실패하거나 세션을 리셋시키므로, PID를 직접 확인 후 `kill <pid>`로 죽이는 편이 안전하다.

## 코드를 고친 뒤 검증하는 방법

```bash
# 1. 파이썬 순수 로직 전체 (항상 통과해야 함, ffmpeg/whisper/pycapcut 불필요)
python3 -m unittest discover -s tests -v   # 91개

# 2. .bat 파일을 건드렸다면 CRLF/괄호 이스케이프 재확인 (위 1, 2번 참고)

# 3. draft_builder/visual_correction/audio_mix를 건드렸다면 실제 ffmpeg+pycapcut으로 검증
#    (합성 테스트 영상: ffmpeg -f lavfi -i "color=..." + sine/anullsrc concat 조합, 이 파일들의
#    test_*_integration.py가 예시. ffmpeg 빌드에 --enable-libvidstab 있는지 `ffmpeg -filters | grep vidstab`)

# 4. server.py를 건드렸다면 FastAPI TestClient로 (실제 ffmpeg/whisper는 mock):
python3 -m unittest tests.test_server -v   # 18개, ProjectStore를 tempdir로 patch해서 격리

# 5. gui.py를 건드렸다면 Xvfb로 실제 렌더링 (apt-get install python3-tk x11-apps 최초 1회)

# 6. webapp/을 건드렸다면
cd webapp && npx tsc -b && npm run build && npx vitest run   # 30개

# 7. 백엔드+프론트엔드 통합을 건드렸다면 진짜로 둘 다 띄워서 확인 (CORS 포트 주의! 위 6번 참고):
python3 -c "
import capcut_auto.server as s
from capcut_auto.transcribe import Word
s.transcribe_audio = lambda *a, **k: [Word(0.3,0.6,'어'), Word(1.0,2.0,'테스트')]
import uvicorn; uvicorn.run(s.app, host='127.0.0.1', port=8000)
" &
(cd webapp && npm run dev -- --port 5173 --host 127.0.0.1) &
# 그 다음 Playwright(/opt/pw-browsers/chromium)로 실제 업로드→9단계 진행→draft_content.json 확인
```

## 남은 사용자 미확인 사항 (질문 오면 이렇게 답할 것)

- Windows에서 `install.bat`이 ffmpeg 다운로드 → GUI 실행까지 완전히 끝까지 성공한 것은 아직 사용자
  확인 전. CLI/GUI 경로와 웹앱/백엔드 경로는 서로 다른 설치 흐름이라는 점도 안내할 것
  (웹앱은 `pip install -r requirements.txt` + `uvicorn capcut_auto.server:app` + `npm install && npm run dev`
  둘 다 띄워야 함, 아직 원클릭 설치 스크립트 없음).
- CapCut 드래프트 폴더 기본 경로(`default_capcut_drafts_dir()`)는 추정치. 실제 폴더가 다르면
  9단계의 "CapCut 드래프트 폴더 경로" 고급 설정에 직접 입력하면 된다.
- 배경음(BGM)은 절차적으로 생성한 화음일 뿐 실제 음원이 아니고, 훅 문구/촬영 가이드 둘 다 템플릿
  기반이지 LLM이 아니라는 점을 사용자가 재차 물으면 솔직히 답할 것 (README/보고서에도 명시되어 있음).
- SHOOTING_GUIDE(MODE 2)의 촬영 계획 생성 로직은 이제 구현되어 있다(`shooting_guide.py` +
  `/api/shooting-guide`). 카테고리당 6~8개 앵글 템플릿만 정의돼 있어서, 정의되지 않은 세부 상황에는
  다소 일반적인 문구가 나올 수 있다는 점은 한계로 남아있음.
