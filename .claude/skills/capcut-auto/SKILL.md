---
name: capcut-auto
description: Use when working on this repo's capcut_auto/ pycapcut-based CapCut auto-editing pipeline (silence/filler-word/stutter auto-cut + auto-subtitles), its Tkinter GUI, its CLI, or its Windows install.bat/run.bat installer. Also use when the user asks in Korean or English to build/extend/debug "CapCut 자동 편집", "무음 컷", "버벅임/필러워드 컷", "자막 자동 생성", or a "pycapcut" automation, or reports install.bat/run.bat errors (black window closes instantly, encoding garbage, pip install failures). Trigger even if they don't name the file paths directly - match on the task shape (CapCut + automation/scripting), not just exact keywords.
---

# capcut-auto: pycapcut CapCut 자동 컷/자막 파이프라인

이 저장소의 `capcut_auto/` 는 무음 구간·필러워드(어/음/그...)·즉시 반복(말더듬)을 자동으로
탐지해 컷 편집하고, 압축된 새 타임라인에 맞춰 자막을 재정렬해 [pycapcut](https://github.com/GuanYixuan/pyCapCut)으로
CapCut 드래프트를 생성하는 파이썬 프로젝트다. CLI와 Tkinter GUI가 있고, Windows용
원클릭 설치 스크립트(`install.bat`/`run.bat`)가 있다.

이 스킬은 이 프로젝트를 다루는 모든 세션에서 반복 조사를 피하기 위해, 이미 검증된
사실과 흔한 실패 지점을 요약한다. **아래 내용을 다시 처음부터 조사하지 말고 그대로 신뢰할 것.**

## 아키텍처 (한눈에)

```
capcut_auto/
  timeline.py     구간(Interval) 병합/패딩/역산 - 순수 함수, 외부 의존성 없음
  silence.py      ffmpeg 오디오 추출 + silencedetect 파싱, ffmpeg/ffprobe 바이너리 탐지
  transcribe.py   faster-whisper 단어 단위 음성 인식 (지연 import)
  stutter.py      필러워드/반복(말더듬) 탐지 - 순수 함수
  cutlist.py      위 세 소스를 합쳐 최종 keep/cut 구간 계산
  subtitles.py    컷 반영 자막 리타이밍 + SRT 생성 - 순수 함수
  draft_builder.py  pycapcut으로 실제 CapCut 드래프트 생성 (video/text 트랙)
  pipeline.py     PipelineOptions/PipelineResult/run_pipeline() - CLI/GUI 공유 오케스트레이션
  cli.py          얇은 argparse 래퍼, run_pipeline 호출
  gui.py          Tkinter GUI, 백그라운드 스레드 + queue로 run_pipeline 실행
tests/            42~45개 유닛테스트. ffmpeg/whisper/pycapcut 없이도 전부 통과해야 함
install.bat       Windows 원클릭 설치 (venv, pip install, ffmpeg 번들 다운로드, 바탕화면 바로가기)
run.bat           설치 후 pythonw로 GUI 실행 (콘솔 창 없음)
```

## 이미 검증된 사실 (재조사 불필요)

- **pycapcut 실제 API는 draft_builder.py의 코드와 정확히 일치함을 실제 설치해서 확인함**
  (`DraftFolder(folder_path)`, `create_draft(draft_name, width, height, fps=30, *, allow_replace=False)`,
  `add_track(track_type, track_name=None, ...)`, `add_segment(segment, track_name=None)`,
  `VideoSegment(material, target_timerange, *, source_timerange=None, ...)`,
  `TextSegment(text, timerange, *, style=None, ...)`, `TextStyle(*, size=8.0, bold=False, color=(1,1,1), align=0, ...)`,
  `Timerange(start, duration)`, `.save()`). PyPI의 pycapcut 최신 버전은 **0.0.3**이 최대치임
  (`>=0.1.0`처럼 존재하지 않는 버전을 요구하면 `pip install`이 그 자리에서 실패한다 - 실제로 겪은 버그).
- **real ffmpeg + real pycapcut로 end-to-end 검증 완료**: 6초짜리(2초 톤 + 4초 무음) 합성 영상으로
  `get_duration` → `extract_audio` → `detect_silence` → `build_draft`까지 실제로 돌려서
  올바른 `draft_content.json`(video 트랙 1개, text 트랙 1개, 정확한 duration/스타일)이 생성됨을 확인함.
- **GUI는 Xvfb 가상 디스플레이 + `apt-get install python3-tk`로 실제 창을 띄워 검증함**
  (기본 파이썬 인터프리터엔 tkinter가 없을 수 있으니 `python3.12` 등 tk가 포함된 버전을 따로 써야 함).
  위젯 생성, 옵션 수집(`_collect_options`), 실행→백그라운드 스레드→큐→UI 갱신 전체 흐름,
  `ttk.Button`의 `["state"]` 값은 `str()`로 감싸야 `"disabled"`/`"normal"`과 비교 가능함(Tcl 객체라 `==` 직접 비교 실패).
- **faster-whisper 모델 다운로드(huggingface.co)만 미검증** - 개발 샌드박스의 아웃바운드 프록시 정책이
  gyan.dev, huggingface.co를 차단해서 이 두 가지(ffmpeg zip 다운로드, whisper 모델 다운로드)는
  실사용자 PC에서만 확인 가능. 코드 자체는 표준적인 `huggingface_hub.snapshot_download` /
  `Invoke-WebRequest` 사용이라 인터넷 연결이 있는 일반 환경에서는 정상 동작할 것으로 신뢰해도 됨.

## 흔한 실패 지점과 원인 (실제로 겪은 버그들)

1. **`install.bat`/`run.bat`을 더블클릭하면 검은 창이 잠깐 떴다가 바로 사라짐**
   → 거의 항상 파일이 LF(유닉스) 줄바꿈으로 저장돼서 cmd.exe가 파싱 중 즉사하는 문제.
   `file install.bat`로 `CRLF line terminators`인지 반드시 확인할 것. 리눅스에서 이 프로젝트의
   .bat 파일을 수정한 뒤에는 항상 아래로 CRLF 무결성을 검증한다:
   ```bash
   python3 -c "
   data = open('install.bat','rb').read()
   bad = sum(1 for i in range(len(data)) if data[i:i+1]==b'\n' and (i==0 or data[i-1:i]!=b'\r'))
   print('lone LF count:', bad)  # 0이어야 함
   "
   ```
2. **cmd.exe가 `echo` 텍스트 일부를 명령어로 착각해 `'...' is not recognized as an internal or external command` 에러**
   → 배치 파일에서 괄호 `(` `)` 가 포함된 한글/영문 텍스트를 최상위(또는 `if`/`for` 블록 내부)
   `echo`나 문자열에 쓸 때 이스케이프(`^(` `^(`)를 빠뜨린 경우. 특히 블록 안에서는 **따옴표로 감싸도**
   내부 괄호가 블록 중첩 카운터를 깨뜨릴 수 있으니 항상 `^(...^)` 로 이스케이프하거나 아예 괄호를
   빼고 문장을 바꿔쓴다. 새 echo 줄을 추가할 때마다 `grep -n "echo.*(" install.bat run.bat` 로
   미이스케이프 괄호가 없는지 확인할 것.
3. **`pip install -r requirements.txt` 가 `No matching distribution found for pycapcut>=X.Y.Z`로 실패**
   → requirements.txt/pyproject.toml의 버전 상한을 PyPI 실제 최신 버전보다 높게 잡은 경우.
   `pip index versions pycapcut` (또는 `faster-whisper`)로 실제 존재하는 버전을 먼저 확인하고 맞출 것.
4. **바탕화면 바로가기 파일명에 한글을 쓰면 인코딩 깨짐 위험** → PowerShell이 UTF-8 BOM 없는
   .bat에서 echo로 흘려보낸 텍스트를 시스템 기본 코드페이지로 잘못 읽을 수 있음. 바로가기 파일명은
   ASCII로 유지(`CapCut Auto Editor.lnk`), 콘솔에 보여주는 안내 메시지만 한글 사용.

## 코드를 고친 뒤 검증하는 방법

```bash
# 1. 순수 로직 전체 (항상 통과해야 함, ffmpeg/whisper/pycapcut 불필요)
python3 -m unittest discover -s tests -v

# 2. .bat 파일을 건드렸다면 CRLF/괄호 이스케이프 재확인 (위 "흔한 실패 지점" 1, 2번 참고)

# 3. draft_builder.py나 pycapcut 연동 코드를 건드렸다면, 실제 설치해서 검증 (신뢰할 수 없는 추측 금지):
python3 -m venv /tmp/pycapcut_check && /tmp/pycapcut_check/bin/pip install pycapcut
# 그 다음 6초짜리 합성 테스트 영상(ffmpeg lavfi sine+anullsrc+concat)으로 build_draft()를 실제로 호출해
# draft_content.json에 올바른 트랙/자막이 들어갔는지 확인한다.

# 4. gui.py를 건드렸다면 Xvfb로 실제 렌더링:
apt-get install -y python3-tk x11-apps   # 최초 1회
xvfb-run -a /usr/bin/python3.12 -c "... CapCutAutoApp 인스턴스화 후 위젯/스레드 흐름 점검 ..."
```

## 남은 사용자 미확인 사항 (질문 오면 이렇게 답할 것)

- Windows에서 `install.bat`이 ffmpeg 다운로드 → GUI 실행까지 **완전히 끝까지 성공**한 것은 아직 사용자가
  확인해주지 않았다. CRLF/괄호/버전 핀 버그는 고쳤지만, "다 됐다"고 단정하지 말고 다음 단계에서
  막히면 화면/에러 메시지를 요청해 하나씩 대응하는 식으로 안내할 것.
- CapCut 드래프트 폴더 기본 경로(`default_capcut_drafts_dir()`)는 CapCut 버전/지역에 따라 다를 수 있어
  추정치일 뿐이다. 실제 폴더가 다르면 사용자가 GUI의 "찾아보기"로 직접 지정하면 된다.
