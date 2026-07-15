---
name: capcut-auto
description: Use when working on this repo's capcut_auto/ pycapcut-based CapCut auto-editing engine (silence/filler-word/stutter auto-cut, auto-subtitles, visual correction, audio mixing, hook generation, shooting-guide/shot-list generation), its FastAPI backend (server.py), the webapp/ React frontend (mode/category selection, 9-step AUTO_EDIT wizard, SHOOTING_GUIDE form + result), its Tkinter GUI/CLI, its desktop/ Electron desktop app shell (main.js/setup.js/electron-builder packaging), or its Windows install.bat/run.bat installer. Also use when the user asks in Korean or English to build/extend/debug "CapCut 자동 편집", "무음 컷", "버벅임/필러워드 컷", "자막 자동 생성", "화면 보정", "배경음/효과음", "훅 문구", "촬영 가이드/앵글/촬영 순서", a "pycapcut" automation, "데스크톱 앱"/"설치형 앱"/"Electron" packaging, or the webapp/backend integration, or reports install.bat/run.bat errors. Trigger even if they don't name the file paths directly - match on the task shape, not just exact keywords.
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
  server.py              FastAPI 백엔드. MODE 1의 3~9단계를 위 모듈들에 연결하는 REST API (아래 표 참고).
                          아직 ai/ 패키지를 호출하는 엔드포인트는 없음(엔진+테스트만 이번 단계 범위) -
                          기존 3/4/6단계는 여전히 규칙 기반(silence/stutter/hooks.py)만 사용함
  pipeline.py             PipelineOptions/PipelineResult/run_pipeline() - CLI/GUI 전용 단일 파이프라인
                          (server.py는 이걸 쓰지 않고 각 단계를 개별 호출 - 사용자가 단계 사이에
                          검토/수정할 수 있어야 하기 때문)
  cli.py / gui.py         기존 CLI/Tkinter GUI, run_pipeline() 기반, 그대로 유지됨
  ai/                     AI 기반 자동 편집 핵심 기능 (아래 "capcut_auto/ai/" 절 참고).
                          기존 규칙 기반 파이프라인과 독립적으로 추가된 레이어 - server.py의
                          3/4/6단계는 아직 이 패키지를 쓰지 않음(연결은 다음 단계)
  visual/                 대표 프레임 추출/피사체 감지/9:16 리프레이밍/자막 안전 영역
                          (아래 "capcut_auto/visual/" 절 참고). reframe.py의 crop 계산+렌더링은
                          server.py Step5(화면 보정)에 연결됨(아래 "9:16 자동 리프레이밍 연결" 참고).
                          frame_extraction.py/subject_detection.py는 그 내부에서만 쓰이고
                          단독 REST 엔드포인트는 아직 없음
  sfx_recommend.py         장면에 맞는 효과음 추천 - 목적 분류 → 내부 에셋(ffmpeg 절차 생성) 검색 →
                          실제 오디오 충돌(빈도/음성/보호구간/연속반복) 확인 → 최대 3개 후보 →
                          apply_approved_sfx()로 승인된 것만 적용. server.py Step7(소리)에 연결됨
  bgm_recommend.py          BGM 추천 - 무드/템포범위/에너지/보컬유무/검색키워드/음성중 자동
                          덕킹 규칙만 추천. 곡 제목/아티스트/저작권/트렌드 여부는 절대 만들지
                          않음(FORBIDDEN_FIELD_NAMES로 하드 가드). server.py Step7(소리)에 연결됨
  shooting_guide_v2.py     MODE 2 확장 - 새 ShootingGuideInput 스키마(topic/category/subject/
                          targetDurationSeconds/...), 길이 기반 컷개수 규칙, 역할별
                          카메라 5요소+자막안전영역+필수여부, 체크리스트+진행률.
                          기존 shooting_guide.py(v1, server.py에 연결됨)는 그대로 두고 별도
                          모듈로 추가함 - `/api/shooting-guide-v2`로 연결됨(webapp의
                          ShootingGuideScreen "새 방식" 토글). **MODE1 인계(continueToAutoEdit)는
                          아직 v1 스키마만 지원해서 v2 계획은 열람/체크리스트 전용**(알려진 한계)
tests/                    407개 유닛테스트. ffmpeg/whisper/pycapcut 없이도 순수 로직은 전부 통과.
                          test_*_integration.py는 실제 ffmpeg 있을 때만 돌아감(skipUnless).
                          ai_test_helpers.py는 진짜 네트워크 호출 없이 client.py를 검증하는
                          가짜(fake) Anthropic 클라이언트 - 모든 tests/test_ai_*.py가 공유함
install.bat / run.bat     Windows 원클릭 설치/실행 (CLI/GUI용, 웹앱과는 별개)
build-desktop.bat         Windows 원클릭 데스크톱 앱 빌드(webapp 빌드 → desktop npm install →
                          electron-builder). 결과물은 desktop/dist-electron/에 생김

webapp/
  src/api/client.ts        server.py의 모든 엔드포인트에 대응하는 fetch 래퍼
  src/hooks/useJobPolling.ts  "POST로 시작 → GET으로 폴링" 패턴 공용 훅 (analyze/correction/audio/export)
  src/state/ProjectContext.tsx  mode/category를 localStorage에 저장 (프로젝트 = 현재 진행 중인 것 1개)
  src/screens/StartScreen.tsx      모드 카드 2개
  src/screens/AutoEditScreen.tsx    9단계 오케스트레이션. 1~2단계 완료 시 POST /api/projects로
                                   프로젝트 생성 → projectId를 3~9단계에 내려줌
  src/screens/steps/Step1~9*.tsx    각 단계. 3,5,7,9는 useJobPolling으로 백엔드 작업 실행,
                                   4,6은 동기 CRUD, 8은 요약 조회
  src/screens/ShootingGuideScreen.tsx  MODE 2 입력 폼 + 실제 촬영 계획 결과 화면. "기본 방식"(v1)/
                                   "새 방식"(v2, 카메라 세부정보+체크리스트) 토글 제공. v1 결과 화면의
                                   "이 계획으로 영상 편집 시작" 버튼을 누르면 continueToAutoEdit(plan)으로
                                   MODE 1로 즉시 전환됨 (아래 "MODE 1 ↔ MODE 2 인계" 참고) - v2는 아직
                                   이 인계를 지원하지 않음
  .env.development           npm run dev(vite 개발 서버)에서만 VITE_API_BASE=http://127.0.0.1:8000를
                                   지정한다. 프로덕션 빌드(webapp/dist)는 server.py 자신이 프론트엔드까지
                                   같은 오리진에서 서빙하므로 src/api/client.ts의 API_BASE가 상대경로(빈
                                   문자열)로 자동 전환됨 - 데스크톱 앱이 포트에 상관없이 동작하게 하기 위함

desktop/                    Electron 데스크톱 앱 셸 (Windows/Mac 설치형, 아래 "데스크톱 앱" 절 참고)
  main.js                   Electron 메인 프로세스 - 로컬 uvicorn을 자식 프로세스로 띄우고 그 주소를
                                   여는 창 하나만 보여줌. REPO_ROOT(앱 코드, 읽기전용일 수 있음)와
                                   DATA_DIR(app.getPath('userData'), 쓰기 가능)를 구분해서 쓴다
  setup.js                  최초 실행 시 venv 생성 + pip install(+Windows는 ffmpeg 자동 다운로드)을
                                   Node로 재현. Electron 의존성 전혀 없는 순수 Node 코드라 Electron 없이도
                                   단독 테스트 가능(실제로 이렇게 검증함 - 아래 "이미 검증된 사실" 참고)
  package.json               electron-builder 설정(extraResources로 capcut_auto/+category-rules/+
                                   webapp/dist를 패키징. .venv는 크고 이식성이 떨어져 번들하지 않음 -
                                   대신 setup.js가 설치 후 첫 실행 시 만듦)
```

## capcut_auto/ai/ - AI 자동 편집 핵심 기능

실제 Claude API(Structured Outputs)를 호출하는 새 레이어. `pip install anthropic jsonschema`
필요(requirements.txt에 이미 추가됨). **아직 server.py 엔드포인트나 webapp UI에 연결되지
않은 순수 엔진 + 테스트 단계**임 - 다음 단계에서 REST 엔드포인트로 노출하고 프론트엔드에
연결하는 작업이 남아 있다.

```
ai/
  client.py              공통 AI 호출: AiModuleRequest, call_ai_module(request, *, model=,
                          max_tokens=, client=, sleep_fn=). system_prompt와 input_data(JSON
                          직렬화)를 분리해서 보내고, output_config.format(json_schema)으로
                          Structured Outputs를 강제한 뒤 jsonschema로 재검증한다.
                          네트워크 오류(연결/429/5xx) 최대 2회 재시도, JSON파싱/스키마 오류는
                          합쳐서 1회만 수정 요청, 그래도 실패하면 AiModuleError를 던진다 -
                          호출자는 이 예외를 잡아 "해당 기능만" 폴백해야 한다.
                          기본 모델은 claude-opus-4-8 (claude-api 스킬의 기본 모델 규칙을 따름).
  schemas.py              각 모듈의 출력 JSON Schema (VIDEO_STRUCTURE/CUT_CANDIDATES/
                          SUBTITLE_OPTIMIZE/SUBTITLE_HIGHLIGHT/HOOK_CANDIDATES)
  video_structure.py      VideoSectionRole(HOOK/PROBLEM/CAUSE/SOLUTION/PROCESS/PROOF/RESULT/
                          CTA/TRANSITION/UNKNOWN), analyze_video_structure(), 실패 시
                          fallback_single_unknown_section()
  cut_candidates.py       CutAction(AUTO_CUT/REVIEW/KEEP), CutCandidate, ProtectedInterval,
                          analyze_cut_candidates(), meets_auto_apply_criteria()(UI 배지 용도일
                          뿐 실제 자동적용에는 안 씀), fallback_from_rule_based_intervals()
                          (AI 실패 시 기존 silence/stutter 결과를 재활용), review_candidates()
                          (사용자가 후보별 action을 결정), approved_cut_intervals()
                          (**decisions 딕셔너리에 사용자가 명시적으로 AUTO_CUT을 기록한
                          후보만** Interval로 뽑음 - candidate.action이 이미 AUTO_CUT이어도
                          decisions에 없으면 절대 적용 안 됨. "모든 후보는 사용자 검토 후 적용"
                          정책을 코드로 강제하기 위한 설계)
  cut_apply.py            AI 아닌 순수 로직 + 실제 ffmpeg. clip_to_video_range(),
                          snap_to_word_boundaries()(컷 경계를 더 가까운 단어 경계로 스냅해
                          음절 반토막 방지), apply_approved_cuts()(병합+클램프+스냅 후
                          keep_intervals 재계산, 전후 미리보기 정보 포함), EditHistory
                          (undo/redo/revert_to_original 스냅샷 스택),
                          render_crossfade_preview()(실제 ffmpeg로 keep_intervals만 이어붙인
                          미리보기 렌더링 - 진짜 acrossfade 대신 각 클립 경계에 afade in/out만
                          걸어 오디오/비디오 동기화가 안 어긋나게 함 - real ffmpeg 통합 테스트로
                          검증됨, 5초 keep 합계에 대해 출력 길이 ≈5초 확인)
  timeline_recalc.py      recalculate_words/subtitle_lines/sections/hook_range,
                          recalculate_timeline()(전체 파이프라인, 실패하면 success=False +
                          원본 값을 그대로 담아 반환 - 호출자는 이걸 보고 내보내기를 막고
                          EditHistory로 원상복구해야 함). 효과음/BGM/크롭/줌은 아직 기능
                          자체가 없어서 재계산 대상에서 제외(주석에 명시)
  subtitle_optimizer.py   optimize_subtitles(), validate_optimized_line()(2줄/14자/조사분리/
                          숫자단위분리/0.7초 노출/시간겹침 규칙을 코드에서 검증). 규칙 위반한
                          "줄 하나"는 그 줄만 원본으로 폴백, 최종 결과가 여전히 겹치면(회복
                          불가) 전체를 원본으로 폴백하는 2단계 안전망
  subtitle_highlight.py   SubtitleHighlightType, generate_highlights(), validate_highlight()
                          (강조 단어가 실제 자막 텍스트에 포함돼 있는지 반드시 코드에서 검증 -
                          AI가 지어낸 단어는 버림), 한 줄 최대 2개
  hook_ai.py              HookType, HookCandidate, generate_ai_hooks(), validate_hook_grounding()
                          (evidenceSegmentIds가 전부 실재하는 segment id를 가리키는지 검증 -
                          지어낸 근거의 훅은 코드에서 버림)
  category_rules.py       category-rules/*.json → capcut_auto.category_rules.CategoryRuleSet을
                          AI 입력 파라미터 모양(camelCase 문자열/리스트)으로 바꿔주는 얇은 어댑터.
                          build_cut_protection_rules/build_removable_moment_hints/
                          build_preferred_pacing/build_preserve_natural_audio/
                          build_subtitle_density_rule/build_safety_checks(카테고리 규칙 +
                          공통 규칙을 합쳐서 반환, include_common=False로 카테고리 규칙만도 가능)/
                          build_discouraged_sound_effects/build_preferred_shot_types/
                          build_shooting_guide_rules/category_label. **더 이상 categories.py를
                          데이터 소스로 쓰지 않는다** - categories.py의 CategoryRule에 있던
                          protected_scene_keywords/subtitle_density_label 필드는 이제
                          category-rules/*.json이 유일한 출처가 되면서 삭제됨(중복 소스 방지)
```

**아직 검증되지 않은 부분**: 실제 Claude API 호출(진짜 ANTHROPIC_API_KEY로 정상 응답을
받는지)은 이 샌드박스에 API 키가 없어서 검증 못 했다. 대신 `tests/ai_test_helpers.py`의
가짜(fake) Anthropic 클라이언트로 `client.messages.create()` 반환값/예외를 흉내내서
`call_ai_module()`의 재시도/스키마검증/폴백 분기를 전부 실제로 통과시켰다 - 요청 페이로드
구성(system/messages 분리, JSON 직렬화)과 응답 파싱/검증 로직은 진짜 코드지만, "Claude가
실제로 이 프롬프트에 이렇게 응답한다"는 것 자체는 미검증이다. 실사용자가 API 키를 넣고
한 번 실행해보면 프롬프트 튜닝이 필요할 수 있다는 점을 안내할 것.

## category-rules/ - 카테고리별 규칙 (독립 설정 파일)

카테고리마다 별도의 코드/앱을 두지 않는다. `category-rules/<카테고리소문자>.json` 8개
(7개 카테고리 + `common.json`)가 유일한 데이터 소스이고, `capcut_auto/category_rules.py`가
이를 읽어 `CategoryRuleSet` 파이썬 객체로 만든 뒤, `ai/category_rules.py`가 그걸 각 AI 모듈이
받는 파라미터 모양으로 변환해 넘긴다. 새 카테고리를 추가하거나 기존 규칙을 조정할 때
**파이썬 코드를 건드릴 필요가 없다** - JSON 파일만 고치면 된다.

```
category-rules/
  common.json     모든 카테고리에 공통으로 적용되는 7개 규칙(commonRules) - load_common_rules()
  living.json     ContentCategory와 1:1 대응. 각 파일은 CategoryRuleSet 인터페이스와
  cleaning.json   정확히 같은 필드를 camelCase로 담는다: category, protectedMoments,
  food.json       removableMoments, preferredPacing(SLOW/MEDIUM/FAST),
  parenting.json  subtitleDensity(LOW/MEDIUM/HIGH), preserveNaturalAudio(bool),
  beauty.json     preferredShotTypes, discouragedSoundEffects, safetyChecks,
  travel.json     shootingGuideRules
  camping.json
```

`capcut_auto/category_rules.py`:
- `CategoryRuleSet` (frozen dataclass, snake_case 필드) + `.to_payload()`(camelCase dict로 역변환)
- `load_category_rule_set(category, rules_dir=None)` - 필수 키 누락/잘못된 enum 값(preferredPacing이
  SLOW/MEDIUM/FAST가 아니거나, subtitleDensity가 LOW/MEDIUM/HIGH가 아니면)이면 **조용히 기본값으로
  넘어가지 않고 예외를 던진다** (안전 규칙처럼 조용히 틀리면 안 되는 데이터라서 fail-fast로 설계함)
- `load_common_rules()`, `load_all_category_rule_sets()`(전체 로드, 테스트/검증용)
- `sfx_allowed(rule_set)` - `preserve_natural_audio`가 true면 효과음을 제한(False)하는 순수 함수

**사용자가 명시적으로 준 스펙만 데이터로 넣었다**: 예를 들어 살림/뷰티는 "삭제 후보"나
"규칙" 목록이 스펙에 없었으므로 `removableMoments`/`safetyChecks`를 빈 배열로 두었다(임의로
지어내지 않음). `preferredPacing`/`subtitleDensity`처럼 스펙에 명시되지 않은 필드는 카테고리의
성격과 기존 `cutlist_config`(edge padding 크기 - 클수록 보수적으로 컷)에서 합리적으로 추론해
채웠다 - 정확한 매핑 근거는 `capcut_auto/ai/category_rules.py`와 커밋 메시지에 남겨뒀다.

`tests/test_category_rules.py`(33개)가 요청받은 10개 테스트 항목(보호 구간/삭제 후보/자막
밀도/훅 생성/자연음 보호/화면 구도/효과음 제한/안전 규칙/기존 엔진 정상 작동/카테고리 간
미혼입)을 각각 커버한다. "다른 카테고리가 섞이지 않는지"는 전체 카테고리 쌍의 protectedMoments가
서로 다른지, 한 카테고리를 로드해도 다른 카테고리 로드 결과가 안 바뀌는지, 같은 프로세스에서
연속으로 다른 카테고리를 호출해도 페이로드가 안 섞이는지까지 실제로 확인한다.

## capcut_auto/visual/ - 대표 프레임/피사체/9:16/자막 안전 영역 (Phase 4)

```
visual/
  frame_extraction.py     장면전환(ffmpeg select=gt(scene,threshold)+showinfo 실제 파싱)/
                          모션변화/문장시작/의미 기반(결과공개·비포애프터, VideoSection 역할
                          전이로 판단) 트리거를 merge_and_space_trigger_times()로 합쳐 min_gap~
                          max_gap 간격으로 스페이싱한 뒤 extract_representative_frames()가
                          실제 ffmpeg로 JPG 프레임을 뽑는다. 영상 전체를 AI에 보내지 않기 위한
                          전처리 단계 - 기본 간격 0.5~1초
  subject_detection.py     실제 OpenCV Haar Cascade(오프라인, opencv-python-headless==4.10.0.84
                          로 버전 고정 - 최신 5.0.0은 cascade 데이터가 비어 있어 못 씀)로 얼굴만
                          실제 검출. UNSUPPORTED_WITHOUT_REAL_MODEL(hand/product/tool/food/
                          child/beauty_area/travel_location/camping_equipment/work_area/
                          problem_area/text)은 진짜 검출기가 없으므로 **절대 좌표를 지어내지
                          않고 항상 빈 리스트를 반환** - "Claude가 텍스트만으로 객체 좌표를
                          생성하지 않는다" 요구사항을 LLM 호출 코드와 아예 분리하는 방식으로
                          충족(이 모듈은 ai/ 패키지를 import하지 않음). is_confident()가
                          bbox 없음/confidence 낮음을 걸러내 "좌표 신뢰도가 낮으면 자동 크롭
                          안 함"을 강제
  reframe.py                compute_crop_window()(피사체 bbox+여백이 9:16 안에 들어오도록
                          zoom 계산, max_zoom 기본 1.35·해상도 낮으면 zoom_limit_for_resolution()
                          으로 더 낮춤, 못 담으면 subject_fully_contained=False로 정직하게 표시),
                          smooth_crop_path()(중심 이동/줌 변화를 프레임당 최대치로 클램프해
                          급격한 크롭 점프 방지 - 결정론적 클램프 방식이며 ML 트래커는 아님,
                          범위를 벗어나는 설계 결정으로 문서화), align_before_after_crop()
                          (비포/애프터는 같은 구도 재사용), apply_approved_reframe()
                          (approved=True인 계획만 통과 - "모든 화면 보정은 사용자 검토 후 적용")
  subtitle_safe_zone.py     compute_subtitle_safe_zone() - 하단 밴드를 기본으로 쓰고, 신뢰도
                          높은 피사체가 겹치면 상단으로 이동, 양쪽 다 겹치면 overlaps_subject=True
                          로 정직하게 플래그(조용히 무시하지 않음)
```

## sfx_recommend.py - 장면에 맞는 효과음 추천 (Phase 4)

사용자가 전문 효과음 이름을 직접 고르지 않는다. `classify_scene_purpose()`가 `VideoSection.role`
(이미 분석된 실제 데이터)만으로 목적(RESULT_REVEAL/TRANSITION/EMPHASIS/SUCCESS/BUILD_UP)을
정하고(매핑 안 되는 역할은 None - 지어내지 않음), `ensure_sfx_asset_library()`가 목적별로
2~3개 톤 시퀀스를 실제 ffmpeg로 생성(라이선스 음원 없어서 `audio_mix.py`와 같은 방식의
플레이스홀더). `recommend_sfx_for_scenes()`가 장면마다 신뢰도(<0.5면 스킵)→자연음 보호
카테고리면 BUILD_UP 배제→보호구간/음성 겹침→10초당 최대 2개 빈도 제한→연속 동일 효과음
금지 순으로 걸러 최대 3개 후보를 만든다. `apply_approved_sfx()`는 `approved=True`이고
`selected_asset_id`가 있는 추천만 실제 배치로 확정한다. `_CATEGORY_PURPOSE_RESTRICTIONS`에
육아만 명시적으로 제한(과도한 충격음 방지) - 스펙에 없는 카테고리 제한은 지어내지 않음.

## bgm_recommend.py - BGM 추천 (Phase 4)

`recommend_bgm_metadata()`는 카테고리 기본 무드(`categories.py`의 `default_bgm_mood`)로
무드/템포범위(BPM)/에너지(LOW/MEDIUM/HIGH)/보컬유무(항상 False - 내레이션과 안 겹치게)/
검색 키워드/음성 중 자동 덕킹 규칙만 담은 `BgmMetadataRecommendation`을 반환한다.
`preserve_natural_audio`가 true인 카테고리는 에너지를 LOW로 강제 제한하고 덕킹을 더 세게
건다. **곡 제목/아티스트/저작권 상태/트렌드 여부 필드가 데이터클래스에 아예 없다** -
`FORBIDDEN_FIELD_NAMES`와 `assert_no_forbidden_fields()`로 이 불변조건을 테스트에서도
직접 검증한다(실수로 이런 필드가 나중에 추가돼도 테스트가 바로 잡아냄).

`audio_mix.mix_bgm()`도 이 단계에서 확장함: `voice_intervals`를 넘기면 ffmpeg
`volume=eval=frame:volume='if(gt(between(t,s1,e1)+...,0),duck,normal)'` 표현식으로 발화
구간에서만 실제로 볼륨을 낮춘다("음성 중 자동 볼륨 감소"). 안 넘기면 기존과 100% 동일한
고정 볼륨 믹싱이라 기존 호출부는 전혀 안 바뀌어도 됨.

## shooting_guide_v2.py - MODE 2 확장 (Phase 4)

기존 `shooting_guide.py`(v1, `/api/shooting-guide`에 연결됨, `product_or_situation`/
`target_duration`(문자열 버킷)/`face_on_camera`/`must_show_scenes`(자유 텍스트) 필드)는
그대로 두고, 사용자가 준 새 `ShootingGuideInput` TS 인터페이스(topic/category/subject/
location?/equipment?: string[]/targetDurationSeconds/showFace?/availableShootingMinutes?/
mustShowSteps?: string[]/additionalNotes?)를 그대로 반영한 **별도 모듈**로 추가했다(필드
모양이 달라 기존 모듈을 고치면 서버/웹앱에 이미 연결된 v1이 깨지므로).

- `cut_count_range_for_duration(seconds)`: 15~30초→6~12컷, 30~60초→8~18컷(스펙에 명시된
  정확한 값). 그 밖의 길이는 가장 가까운 구간의 컷 밀도를 연장한 추정치이며 그렇게
  문서화되어 있음(스펙에 없는 값을 정확한 규칙인 척하지 않음).
- 매 샷마다 역할(HOOK/OVERVIEW/SUBJECT_DETAIL/PROCESS/CHANGE/RESULT = 초반 훅/전체 상황/
  핵심 대상 디테일/실제 과정/핵심 변화/결과), 카메라 5요소(angle/distance/height/direction/
  movement), 촬영 권장 시간(최종 컷 길이가 아니라 역할별 리테이크 배수를 곱한 "여유 있게
  찍어둘 시간"), 자막 안전 영역 힌트, 필수 촬영 여부(mandatory)를 담은 `ShotSpecV2`를 만든다.
- `mustShowSteps`는 마지막 샷(보통 RESULT) 앞에 강제 삽입되고 항상 mandatory=True. 너무
  많아서 권장 컷 수 범위를 넘으면 조용히 자르지 않고 경고를 추가한다.
- `build_shooting_checklist()`/`mark_checklist_item_done()`/`shooting_progress()`로
  체크리스트 + 진행률(전체/필수 항목 각각) 추적.
- **`MODE1_INDEPENDENCE_NOTICE`가 모든 계획의 warnings에 항상 포함됨**: "촬영 계획에 있던
  장면이 실제 영상에 존재한다고 가정하지 않는다"를 코드로 강제하기 위해, 이 모듈은
  `ai/video_structure.py` 등 MODE 1 분석 함수를 아예 import/호출하지 않는다(아키텍처로
  분리) - MODE 1은 이 계획과 완전히 무관하게 업로드된 영상을 처음부터 다시 분석한다.

## tests/test_final_integration.py - 최종 통합 검사 (Phase 4, 20개 시나리오)

7개 카테고리 각각 + 카테고리 전환 + 컷 편집 + 자막 + 훅 + 9:16 크롭 + 자연음 보호 + 효과음
추천 + BGM 추천 + 촬영 가이드 + 실행취소(undo) + 원상복구(revert) + 내보내기(export, 실제
ffmpeg+pycapcut) + 기존 기능 회귀까지 25개 테스트로 커버한다. 개별 모듈 세부 동작은 각
전용 테스트 파일이 담당하고, 이 파일은 **모듈 간 실제 연동**(하나의 파이프라인으로 이어
붙였을 때도 맞물리는지)에 집중한다. `EditHistory.revert_to_original()`이 "원상복구" 구현체이며
undo/redo와 같은 클래스에 있다 - 별도 API 엔드포인트는 없음(server.py에는 아직 미연결).

## MODE 1 ↔ MODE 2 인계 (촬영 계획 → 자동 편집)

`ProjectContext`(`src/state/ProjectContext.tsx`)가 `mode`/`category`뿐 아니라 `topic`, `shootingPlan`
(MODE 2가 만든 전체 `ShootingPlanDto`)까지 localStorage에 함께 저장한다. 흐름:

1. MODE 2에서 카테고리를 고르면 `ShootingGuideScreen`이 그 즉시 `setCategory`로 컨텍스트에 반영함
   (폼 제출 전에도 동기화됨 - AUTO_EDIT의 카테고리 선택과 같은 패턴).
2. 결과 화면의 **"이 계획으로 영상 편집 시작"** 버튼이 `continueToAutoEdit(plan)`을 호출 →
   `mode`를 `AUTO_EDIT`로, `topic`을 `plan.topic`으로, `shootingPlan`을 `plan`으로 한 번에 갱신.
   `App.tsx`의 `mode` 분기가 즉시 `AutoEditScreen`으로 전환시킨다(별도 라우팅 코드 불필요).
3. `AutoEditScreen`은 `shootingPlan`이 있으면 1단계부터 접힌 "촬영 계획 참고" `CollapsibleSection`을
   보여준다(카테고리·주제·앵글별 샷 순서 목록). 실제 편집 로직에는 관여하지 않는 순수 참고용 UI.
4. `Step6SubtitlesHook`은 로컬 `topic` state의 초기값을 `useProject().topic`으로 채워 MODE 2에서
   입력한 주제를 다시 타이핑하지 않게 하고, 입력이 바뀔 때마다 `setProjectTopic`으로 컨텍스트에도
   반영한다.

**실제 uvicorn+vite+Playwright로 전체 인계 흐름을 검증함**: MODE 2 폼 제출 → 실제 `/api/shooting-guide`
호출 → 결과 화면 → "이 계획으로 영상 편집 시작" → AUTO_EDIT 1단계에 "촬영 계획 참고" 패널이 실제
샷 6개(캠핑 카테고리, 5분 이상)를 정확히 표시 → 실제 합성 영상 업로드 → 2단계에 캠핑 카테고리가
이미 선택된 채로 도착 → 실제 `POST /api/projects` → 3단계 분석 시작까지 확인함. 3단계의
faster-whisper 모델 다운로드는 이 샌드박스에서 네트워크 차단으로 403이 나지만, 이는 에러로 정상
표시되고 앱이 죽지 않음("다시 시도" 버튼 노출) — 실사용자 PC에서는 문제 없을 것으로 예상.

## server.py REST API

MODE 1은 전부 `/api/projects/{id}/...` (project_store 상태 기반):

| 메서드/경로 | 용도 |
|---|---|
| `POST /api/projects` | multipart: video 파일 + category + topic → 프로젝트 생성 |
| `POST`/`GET .../analyze` | 3단계: 무음/필러/반복 탐지 + whisper 전사 (백그라운드 스레드+폴링) |
| `GET`/`PATCH .../cuts` | 4단계: 컷 후보 조회/토글 (토글 시 keep_intervals·자막 즉시 재계산) |
| `POST`/`GET .../correction` | 5단계: 화면 보정 (visual_correction.auto_correct, 폴링). **reframe_approved가 true면 auto_correct 호출 전에 render_static_crop()으로 9:16 크롭을 먼저 적용**(Phase 4) |
| `GET .../reframe-suggestion` | 5단계: 9:16 크롭 후보 계산(얼굴 검출 + compute_crop_window) + 실제 미리보기 이미지 렌더링. **이미 계산된 후보가 있으면 캐시를 그대로 반환**(재계산하면 사용자 승인이 초기화되는 문제를 실제 e2e 테스트로 발견해 고침) - `?recompute=true`로 강제 재계산 가능(Phase 4) |
| `PATCH .../reframe-approval` | 5단계: 9:16 크롭 후보 승인/취소 (Phase 4) |
| `GET .../reframe-preview` | 5단계: 크롭 미리보기 JPG 파일 응답 (Phase 4) |
| `GET`/`PATCH .../subtitles`, `GET .../hooks`, `PATCH .../hook` | 6단계: 자막 수정, 훅 문구 추천/선택 |
| `GET .../bgm-library`, `PATCH .../audio-settings`, `POST`/`GET .../audio` | 7단계: 배경음/효과음 (폴링). **오디오 작업이 bgm_recommend 추천 무드/덕킹비율과, project.words 기반 실제 발화구간으로 mix_bgm()에 음성중 자동 볼륨감소를 넘기고, 승인된 sfx_recommend 배치가 있으면 apply_multiple_sfx로 적용, 없으면 기존 컷마다 pop 방식으로 폴백**(Phase 4) |
| `GET .../bgm-recommendation` | 7단계: BGM 메타데이터 추천(무드/템포/에너지/키워드/덕킹) - 상업 정보 없음 (Phase 4) |
| `GET .../sfx-suggestions` | 7단계: 장면별 효과음 후보 추천(3단계 분석 완료 필요) (Phase 4) |
| `PATCH .../sfx-suggestions` | 7단계: 효과음 후보 승인/선택 (Phase 4) |
| `GET /api/sfx-preview/{assetId}` | 7단계: 효과음 미리듣기 오디오 파일 응답 (Phase 4) |
| `GET .../summary` | 8단계: 지금까지 선택 요약 |
| `POST`/`GET .../export` | 9단계: draft_builder.build_draft 호출 (폴링) |

MODE 2는 완전히 별도, **상태 없는(stateless) 단일 엔드포인트**(v1/v2 병행):

| 메서드/경로 | 용도 |
|---|---|
| `POST /api/shooting-guide` | topic/category/productOrSituation/targetDuration(필수) + location/equipment/faceOnCamera/mustShowScenes/availableTime/notes(선택) → `shooting_guide.generate_shooting_plan()` 호출, 앵글/촬영 순서(ShootingPlan) 즉시 반환. 빠른 순수 함수라 폴링 불필요. **MODE1 인계(continueToAutoEdit)는 이 v1 응답 스키마만 지원** |
| `POST /api/shooting-guide-v2` | topic/category/subject/targetDurationSeconds(필수) + location/equipment(배열)/showFace/availableShootingMinutes/mustShowSteps(배열)/additionalNotes(선택) → `shooting_guide_v2.generate_shooting_plan_v2()` 호출. 역할별 카메라 5요소/촬영권장시간/자막안전영역/필수여부가 담긴 ShootingPlanV2 반환(Phase 4). webapp의 ShootingGuideScreen "새 방식" 토글에서 쓰이며, **아직 MODE1로 인계되지 않고 열람/체크리스트 전용**(알려진 범위 제한) |

모든 "무거운" 단계(analyze/correction/audio/export)는 **같은 패턴**: POST가 스레드를 띄우고 즉시
`{"status":"running"}` 반환, 같은 경로 GET으로 `{status, log, error}`를 폴링. `Project.job(name)`이
`JobState`를 관리한다. 상태는 **프로세스 메모리에만** 있음 — 서버 재시작하면 진행 중이던 프로젝트가
사라진다 (의도된 범위 제한, 로컬 1인 도구라 DB 없이 시작함).

## 데스크톱 앱 (desktop/, Electron)

`capcut_auto/server.py`는 `webapp/dist`(빌드 결과물)가 있으면 자기 자신이 정적 파일로 함께
서빙하도록 구성돼 있다(`_maybe_mount_frontend`, 파일 맨 끝, 반드시 다른 `/api/...` 라우트보다
뒤에 마운트해야 `/`가 API를 가리지 않음). 이 덕분에 `desktop/main.js`(Electron 메인 프로세스)는
uvicorn 프로세스 하나만 자식으로 띄우고 그 주소(`http://127.0.0.1:<포트>/`)를 여는 창 하나만
보여주면 전체 화면이 뜬다 - 별도 vite 서버가 필요 없다.

사용자가 빌드하는 가장 쉬운 방법은 저장소 루트의 **`build-desktop.bat`을 더블클릭**하는 것이다
(Node.js가 PATH에 있어야 함, 없으면 nodejs.org에서 설치 안내 메시지를 띄우고 종료). webapp
빌드 → `desktop` npm install → `electron-builder`까지 한 번에 실행하고, 결과물은
`desktop/dist-electron/`에 생긴다. install.bat과 마찬가지로 CRLF 규칙을 지켜야 하고, echo
텍스트에 괄호를 넣지 않았다(위 "흔한 실패 지점" 1번 참고).

핵심 설계:
- **REPO_ROOT**(앱 코드 - `capcut_auto/`, `category-rules/`, `webapp/dist`)와 **DATA_DIR**
  (`app.getPath('userData')`, 사용자별 쓰기 가능한 위치)를 분리한다. 패키징된 앱은 REPO_ROOT가
  보통 Program Files 같은 읽기전용 위치이므로, `.venv`/ffmpeg 다운로드/서버 작업 폴더는 전부
  DATA_DIR 아래에 만든다. `server.py`는 `CAPCUT_AUTO_STATE_DIR`(작업 폴더)와
  `CAPCUT_AUTO_FFMPEG_DIR`(ffmpeg 번들 위치) 환경변수로 이 경로들을 오버라이드할 수 있게
  확장해뒀다(둘 다 기존 상대경로 기본값은 그대로라 CLI/GUI/테스트에 영향 없음).
- **`desktop/setup.js`**가 최초 실행 시 install.bat과 같은 일(venv 생성 → pip install,
  Windows는 ffmpeg 자동 다운로드)을 Node로 재현한다. 이미 준비돼 있으면(실제 import 가능 여부를
  서브프로세스로 확인) 매우 빠르게 건너뛴다. 이 파일은 **Electron API를 전혀 쓰지 않는 순수
  Node 코드**라 Electron 없이도 통째로 테스트할 수 있다.
- `resolvePythonExecutable`(setup.js 내부) 우선순위: DATA_DIR/.venv → REPO_ROOT/.venv(install.bat
  으로 이미 저장소에 세팅된 개발 체크아웃을 그대로 쓰는 경우) → 시스템 PATH의 python/python3.

**중요한 검증 한계**: 이 desktop/ 코드는 이번 세션에서 작성됐지만, `npm install`이 Electron
바이너리를 GitHub에서 받으려다 이 개발 샌드박스의 프록시 정책에 **403으로 막혀**(허용 목록에
`registry.npmjs.org`/`pypi.org`는 있지만 Electron이 실제 바이너리를 받아오는 별도 호스트는 없음)
Electron 자체를 설치/실행해본 적이 없다. 대신 다음은 실제로 검증했다:
1. `server.py`의 정적 파일 서빙(`_maybe_mount_frontend`) - 실제 `npm run build` + 실제 uvicorn +
   Playwright로 "/"가 실제 화면을 띄우고 `/api/...`가 안 가려지는지 확인함.
2. `desktop/setup.js`의 핵심 로직 - Electron 없이 순수 Node 스크립트로 실제 임시 디렉터리에
   진짜 venv를 만들고 진짜 `pip install -r requirements.txt`(faster-whisper 제외한 나머지 전부:
   fastapi/uvicorn/anthropic/jsonschema/opencv-python-headless/numpy/pycapcut)를 끝까지 실행해
   `import capcut_auto.server`가 실제로 성공하는지 확인했고, 재실행 시 약 1초 만에 "이미 준비됨"
   으로 건너뛰는 캐시 동작도 확인함.
3. `desktop/main.js`(창 생성/프로세스 관리/종료 처리)는 Electron 공식 API를 정확히 따랐는지
   코드 리뷰로만 확인했다 - **실제로 창이 뜨는지는 검증 못 함.**

사용자가 "데스크톱 앱이 실제로 되나요?"라고 물으면 위 내용을 정직하게 알려주고, 실제
Windows/Mac에서 `cd desktop && npm install && npm start`로 직접 확인해달라고 안내할 것.
문제가 있으면 정확한 오류 메시지를 받아서 고치면 된다(설치 자체가 안 되는 시나리오는
아직 아무도 겪어보지 못했다는 뜻이라 더더욱 실제 오류 메시지가 필요함).

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
- **server.py는 FastAPI TestClient로 221개 백엔드+엔진 테스트 중 23개(`tests/test_server.py`)를
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
- **pycapcut 0.0.3은 draft_content.json의 최상위 `id`와 draft_meta_info.json의 `draft_id`를 절대
  갱신하지 않는다** — 실제 설치된 패키지 소스(`script_file.py`의 `dumps()`, `draft_folder.py`의
  `create_draft()`)를 직접 읽어 확인함. `DraftFolder.create_draft()`는 `draft_meta_info.json`을
  번들 템플릿에서 그대로 복사만 하고, `ScriptFile.dumps()`도 fps/duration/canvas_config/materials/
  tracks만 갱신하지 `content["id"]`는 안 건드린다. 그 결과 같은 CapCut 드래프트 폴더에 이 파이프라인으로
  드래프트를 여러 개 만들면 **전부 동일한 id**(`91E08AC5-22FB-47e2-9AA0-7DC300FAEA2B`)를 갖고,
  `draft_meta_info.json`의 `draft_id`도 전부 동일(`792BD5DA-E961-4821-B10E-F51E4683DEC0`)했으며
  `draft_name`/`tm_duration`은 항상 빈 값/0이었음(실제로 재현해서 확인한 버그). CapCut이 내부적으로
  이 id를 키로 쓰면(썸네일 캐시, 최근 항목, 클라우드 동기화 등) 여러 드래프트가 서로 덮어쓸 위험이
  있어, `draft_builder.build_draft()`가 `script.save()` 직후 `_fix_draft_ids()`를 호출해 매 드래프트마다
  새 UUID를 부여하고 `draft_meta_info.json`의 `draft_name`/`tm_duration`도 실제 값으로 채우도록
  고쳤다(`tests/test_draft_builder_integration.py`로 실제 ffmpeg+pycapcut 검증, 두 드래프트를 같은
  폴더에 만들어 id 4개가 전부 서로 다른지 확인). `cover`/`static_cover_image_path`/`path` 등 나머지
  최상위 필드는 번들 템플릿의 빈 값 그대로 두었음 — CapCut이 처음 열 때 자체적으로 채우는 필드로
  추정되지만(일반적인 NLE 드래프트 포맷 관례), **실제 CapCut 앱으로 열어본 것은 아니라서 확정 검증은
  못함** (이 환경엔 CapCut이 설치 불가 - Linux 컨테이너, CapCut은 Windows/Mac/모바일 전용).

## 흔한 실패 지점과 원인 (실제로 겪은 버그들)

1. **install.bat/run.bat/build-desktop.bat 검은 창이 바로 사라짐** → LF 줄바꿈 문제. `file <파일명>`
   으로 CRLF 확인. `build-desktop.bat`(desktop/ 빌드 자동화, 이번 세션에 추가)도 같은 규칙 적용됨 -
   실제로 만들 때 echo 텍스트에서 `(exe)`처럼 괄호가 든 부분을 전부 제거해 이 문제를 피했다.
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
10. **`<ol>`/`<ul>`에 항목 순서를 문자열로 직접 써넣으면서(`{item.order}. ...`) 리스트의 CSS를
    `list-style: none`으로 안 지우면 브라우저 기본 번호("1.")와 직접 쓴 번호가 겹쳐서 "1. 1. 제목"처럼
    두 번 보인다. 실제로 `AutoEditScreen`의 "촬영 계획 참고" 패널에서 Playwright 스크린샷으로 발견함.
    순서를 텍스트로 직접 렌더링하는 리스트는 항상 `list-style: none`을 같이 넣을 것
    (`ShootingGuideScreen.module.css`의 `.shotList`가 이미 이렇게 하고 있었음 - 새 리스트 만들 때
    이 패턴을 그대로 베낄 것).
11. **`webapp` 유닛테스트를 실제 백엔드(uvicorn)가 8000번 포트에서 떠 있는 상태로 돌리면, `vi.mock`으로
    안 감싼 API 호출이 실제 네트워크 요청으로 진짜 서버를 때려서 테스트가 원래 기대하던 "요청 실패"
    경로 대신 진짜 데이터를 받아버려 다른 곳에서 실패가 난다** — 실제로 `accessibility.test.tsx`의
    "SHOOTING_GUIDE 빈 결과 화면" 테스트가 이걸로 실패함(이름 그대로 원래는 mock 없이 fetch 실패 →
    빈 화면을 기대했는데, 살아있는 백엔드가 진짜 샷 데이터를 반환해서 실제 헤딩 순서 버그(h1→h3,
    h2 없이 건너뜀)가 처음으로 드러남). `npx vitest run`은 항상 백엔드 서버를 끄고 돌릴 것
    (`lsof -i :8000`으로 확인). 이 김에 그 헤딩 버그(`ShootingGuideScreen.tsx`의 샷 제목 `<h3>`를
    `<h2>`로 수정)도 고쳤고, 실제 샷 데이터를 mock으로 넣어 axe를 돌리는 테스트를 추가해 백엔드가
    꺼져 있어도 이 회귀를 잡을 수 있게 했다.

## 코드를 고친 뒤 검증하는 방법

```bash
# 1. 파이썬 순수 로직 전체 (항상 통과해야 함, ffmpeg/whisper/pycapcut 불필요)
python3 -m unittest discover -s tests -v   # 407개 (opencv-python-headless==4.10.0.84 필요 -
                                            # visual/subject_detection.py용, 5.0.0은 cascade 데이터 없음)

# 2. .bat 파일을 건드렸다면 CRLF/괄호 이스케이프 재확인 (위 1, 2번 참고)

# 3. draft_builder/visual_correction/audio_mix를 건드렸다면 실제 ffmpeg+pycapcut으로 검증
#    (합성 테스트 영상: ffmpeg -f lavfi -i "color=..." + sine/anullsrc concat 조합, 이 파일들의
#    test_*_integration.py가 예시. ffmpeg 빌드에 --enable-libvidstab 있는지 `ffmpeg -filters | grep vidstab`)

# 4. server.py를 건드렸다면 FastAPI TestClient로 (실제 ffmpeg/whisper는 mock):
python3 -m unittest tests.test_server -v   # 23개, ProjectStore를 tempdir로 patch해서 격리

# 5. gui.py를 건드렸다면 Xvfb로 실제 렌더링 (apt-get install python3-tk x11-apps 최초 1회)

# 6. webapp/을 건드렸다면 (백엔드가 8000번 포트에서 떠 있으면 vitest 먼저 끌 것 - 위 "흔한 실패 지점" 11번 참고)
cd webapp && npx tsc -b && npm run build && npx vitest run   # 52개

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
- **`desktop/`(Electron 데스크톱 앱)는 이 개발 샌드박스가 Electron 바이너리 다운로드를 막고 있어서
  Electron이 실제로 뜨는지, `npm run dist`로 만든 설치 파일이 실제로 동작하는지 전혀 검증 못 했다**
  (위 "데스크톱 앱" 절 참고). 사용자가 물으면 이 사실을 그대로 알려주고, `cd desktop && npm install
  && npm start`를 실제 Windows/Mac에서 실행해 확인해달라고 요청할 것 - 문제가 생기면 정확한 오류
  메시지를 받아 그걸 근거로 고칠 것(추측으로 미리 고치지 말 것).
  (웹앱은 `pip install -r requirements.txt` + `uvicorn capcut_auto.server:app` + `npm install && npm run dev`
  둘 다 띄워야 함, 아직 원클릭 설치 스크립트 없음).
- CapCut 드래프트 폴더 기본 경로(`default_capcut_drafts_dir()`)는 추정치. 실제 폴더가 다르면
  9단계의 "CapCut 드래프트 폴더 경로" 고급 설정에 직접 입력하면 된다.
- 배경음(BGM)은 절차적으로 생성한 화음일 뿐 실제 음원이 아니고, 훅 문구/촬영 가이드 둘 다 템플릿
  기반이지 LLM이 아니라는 점을 사용자가 재차 물으면 솔직히 답할 것 (README/보고서에도 명시되어 있음).
- SHOOTING_GUIDE(MODE 2)의 촬영 계획 생성 로직은 이제 구현되어 있다(`shooting_guide.py` +
  `/api/shooting-guide`). 카테고리당 6~8개 앵글 템플릿만 정의돼 있어서, 정의되지 않은 세부 상황에는
  다소 일반적인 문구가 나올 수 있다는 점은 한계로 남아있음.
- **Phase 4 모듈(`visual/reframe.py`, `sfx_recommend.py`, `bgm_recommend.py`, `shooting_guide_v2.py`)은
  이제 전부 server.py/webapp에 실제로 연결되어 있다**(9:16 리프레이밍→Step5, 효과음/BGM 추천→Step7,
  촬영 가이드 v2→ShootingGuideScreen "새 방식" 토글) - 위 "server.py REST API" 표와 각 모듈 절에
  실제 엔드포인트가 기록되어 있다. 실제 uvicorn+vite+Playwright로 끝까지 클릭해 검증했다(스크린샷 확인함).
  다만 `visual/subject_detection.py`/`frame_extraction.py`는 reframe 엔드포인트 내부에서만 쓰이고
  단독 엔드포인트는 없으며, `ai/` 패키지(영상 구조 분석 등 LLM 기반 기능)는 여전히 미연결이다 -
  ANTHROPIC_API_KEY 인프라 자체가 없어서 다음 단계로 남아있음. shooting_guide_v2는 위에 적힌 대로
  MODE1 인계는 아직 지원하지 않는다.
- `subject_detection.py`는 얼굴만 실제 검출하고 나머지 카테고리(hand/product/tool/...)는 항상
  빈 리스트를 반환한다 - 검출기 자체가 없어서 지어내지 않기로 한 설계다. 실사용에 쓰려면 실제
  객체 검출 모델(YOLO 등)을 연결해야 하며, 그 전까지는 얼굴 기반 리프레이밍/자막 안전 영역만
  실질적으로 동작한다.
