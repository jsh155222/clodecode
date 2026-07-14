"""웹 프론트엔드(webapp/)가 호출하는 로컬 FastAPI 백엔드.

MODE 1(AI 자동 편집)의 3~9단계를 실제 capcut_auto 엔진(silence/transcribe/stutter/
cutlist/subtitles/visual_correction/audio_mix/hooks/draft_builder)에 연결한다.

실행:
    uvicorn capcut_auto.server:app --port 8000

로컬 1인 사용을 전제로 상태는 프로세스 메모리에만 둔다 (project_store.py 참고).
"""

from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import audio_mix as audio_mix_mod
from . import cutlist as cutlist_mod
from . import draft_builder
from . import silence as silence_mod
from . import stutter as stutter_mod
from . import subtitles as subtitles_mod
from . import visual_correction as visual_correction_mod
from .categories import CATEGORY_LABELS, ContentCategory, get_rule
from .hooks import generate_hook_suggestions
from .project_store import CutCandidate, Project, ProjectStore
from .shooting_guide import ShootingGuideInput, generate_shooting_plan
from .subtitles import SubtitleLine
from .timeline import Interval
from .transcribe import transcribe as transcribe_audio

APP_STATE_DIR = Path("capcut_auto_server_work")
store = ProjectStore(str(APP_STATE_DIR / "projects"))
_shared_bgm_dir = str(APP_STATE_DIR / "shared_bgm")
_shared_sfx_dir = str(APP_STATE_DIR / "shared_sfx")

app = FastAPI(title="capcut-auto backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- utils
def _get_project_or_404(project_id: str) -> Project:
    try:
        return store.get(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")


def _run_in_background(fn, *args) -> None:
    thread = threading.Thread(target=fn, args=args, daemon=True)
    thread.start()


def _recompute_keep_and_subtitles(project: Project) -> None:
    config = get_rule(project.category).cutlist_config if project.category else cutlist_mod.CutlistConfig()
    silence = [
        Interval(c.start, c.end) for c in project.cut_candidates if c.source == "silence" and c.enabled
    ]
    filler = [Interval(c.start, c.end) for c in project.cut_candidates if c.source == "filler" and c.enabled]
    repetition = [
        Interval(c.start, c.end) for c in project.cut_candidates if c.source == "repetition" and c.enabled
    ]
    result = cutlist_mod.build_cutlist(project.total_duration, silence, filler, repetition, config)
    project.keep_intervals = result.keep_intervals

    remapped = subtitles_mod.remap_words_to_new_timeline(project.words, project.keep_intervals)
    project.subtitle_lines = subtitles_mod.group_words_into_lines(remapped)


def _cut_transition_points(project: Project) -> List[float]:
    points: List[float] = []
    cursor = 0.0
    for iv in project.keep_intervals[:-1]:
        cursor += iv.duration
        points.append(cursor)
    return points


def _project_summary(project: Project) -> dict:
    return {
        "id": project.id,
        "originalFilename": project.original_filename,
        "category": project.category.value if project.category else None,
        "categoryLabel": CATEGORY_LABELS[project.category] if project.category else None,
        "topic": project.topic,
        "totalDuration": project.total_duration,
        "keptDuration": sum(iv.duration for iv in project.keep_intervals) if project.keep_intervals else None,
        "cutCount": len([c for c in project.cut_candidates if c.enabled]),
        "subtitleLineCount": len(project.subtitle_lines),
        "selectedHook": project.selected_hook,
        "stabilizeEnabled": project.stabilize_enabled,
        "correctionApplied": project.correction_result is not None,
        "bgmMood": project.bgm_mood,
        "bgmVolume": project.bgm_volume,
        "sfxEnabled": project.sfx_enabled,
        "audioApplied": project.audio_output_path is not None,
        "draftName": project.draft_name,
    }


# ---------------------------------------------------------------- 1. create
@app.post("/api/projects")
async def create_project(
    video: UploadFile = File(...),
    category: Optional[str] = Form(None),
    topic: str = Form(""),
):
    parsed_category: Optional[ContentCategory] = None
    if category:
        try:
            parsed_category = ContentCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"알 수 없는 카테고리: {category}")

    upload_id = uuid.uuid4().hex[:8]
    upload_dir = APP_STATE_DIR / "uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / (video.filename or "video.mp4")
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    project = store.create(
        video_path=str(dest_path), original_filename=video.filename or "video.mp4", category=parsed_category, topic=topic
    )
    return {"id": project.id, **_project_summary(project)}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = _get_project_or_404(project_id)
    return _project_summary(project)


# --------------------------------------------------------------- 2. analyze
def _run_analyze_job(project: Project) -> None:
    job = project.job("analyze")
    job.status = "running"
    job.log = []
    job.error = None
    try:
        def log(msg: str) -> None:
            job.log.append(msg)

        log("길이 확인 및 오디오 추출 중...")
        project.total_duration = silence_mod.get_duration(project.video_path)
        audio_path = silence_mod.extract_audio(project.video_path, str(Path(project.workdir) / "audio.wav"))

        log("무음 구간 탐지 중...")
        silence_intervals = silence_mod.detect_silence(audio_path, noise_db=-30.0, min_silence_duration=0.6)

        log("음성 인식 중 (faster-whisper)...")
        words = transcribe_audio(audio_path, model_size="small", language="ko")
        project.words = words

        log("필러워드/반복(말더듬) 탐지 중...")
        filler_intervals = stutter_mod.detect_filler_words(words)
        repetition_intervals = stutter_mod.detect_repetitions(words)

        candidates: List[CutCandidate] = []
        for iv in silence_intervals:
            candidates.append(CutCandidate(id=uuid.uuid4().hex[:8], start=iv.start, end=iv.end, source="silence"))
        for iv in filler_intervals:
            candidates.append(CutCandidate(id=uuid.uuid4().hex[:8], start=iv.start, end=iv.end, source="filler"))
        for iv in repetition_intervals:
            candidates.append(CutCandidate(id=uuid.uuid4().hex[:8], start=iv.start, end=iv.end, source="repetition"))
        candidates.sort(key=lambda c: c.start)
        project.cut_candidates = candidates

        log("컷 리스트 및 자막 초안 계산 중...")
        _recompute_keep_and_subtitles(project)

        log("완료")
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 - 오류 원인을 그대로 프론트엔드에 전달
        job.status = "error"
        job.error = str(exc)


@app.post("/api/projects/{project_id}/analyze")
def start_analyze(project_id: str):
    project = _get_project_or_404(project_id)
    job = project.job("analyze")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="이미 분석이 진행 중입니다.")
    _run_in_background(_run_analyze_job, project)
    return {"status": "running"}


@app.get("/api/projects/{project_id}/analyze")
def get_analyze_status(project_id: str):
    project = _get_project_or_404(project_id)
    job = project.job("analyze")
    response = job.to_dict()
    if job.status == "done":
        response["totalDuration"] = project.total_duration
        response["cutCandidates"] = [c.to_dict() for c in project.cut_candidates]
        response["keptDuration"] = sum(iv.duration for iv in project.keep_intervals)
        response["subtitleLines"] = [
            {"start": s.start, "end": s.end, "text": s.text} for s in project.subtitle_lines
        ]
    return response


# ------------------------------------------------------------- 3. cut review
class CutToggleRequest(BaseModel):
    id: str
    enabled: bool


@app.get("/api/projects/{project_id}/cuts")
def get_cuts(project_id: str):
    project = _get_project_or_404(project_id)
    return {
        "cutCandidates": [c.to_dict() for c in project.cut_candidates],
        "keptDuration": sum(iv.duration for iv in project.keep_intervals) if project.keep_intervals else 0,
        "totalDuration": project.total_duration,
    }


@app.patch("/api/projects/{project_id}/cuts")
def toggle_cut(project_id: str, body: CutToggleRequest):
    project = _get_project_or_404(project_id)
    for candidate in project.cut_candidates:
        if candidate.id == body.id:
            candidate.enabled = body.enabled
            break
    else:
        raise HTTPException(status_code=404, detail="해당 컷 후보를 찾을 수 없습니다.")

    _recompute_keep_and_subtitles(project)
    return {
        "cutCandidates": [c.to_dict() for c in project.cut_candidates],
        "keptDuration": sum(iv.duration for iv in project.keep_intervals),
        "totalDuration": project.total_duration,
    }


# --------------------------------------------------------- 4. visual correction
class CorrectionRequest(BaseModel):
    stabilize: bool = True


def _run_correction_job(project: Project) -> None:
    job = project.job("correction")
    job.status = "running"
    job.error = None
    try:
        result = visual_correction_mod.auto_correct(
            project.video_path, str(Path(project.workdir) / "correction"), stabilize_enabled=project.stabilize_enabled
        )
        project.correction_result = result
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.post("/api/projects/{project_id}/correction")
def start_correction(project_id: str, body: CorrectionRequest):
    project = _get_project_or_404(project_id)
    project.stabilize_enabled = body.stabilize
    job = project.job("correction")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="이미 보정이 진행 중입니다.")
    _run_in_background(_run_correction_job, project)
    return {"status": "running"}


@app.get("/api/projects/{project_id}/correction")
def get_correction_status(project_id: str):
    project = _get_project_or_404(project_id)
    job = project.job("correction")
    response = job.to_dict()
    if job.status == "done" and project.correction_result:
        response["brightness"] = project.correction_result.correction_params.brightness
        response["contrast"] = project.correction_result.correction_params.contrast
        response["meanLuma"] = project.correction_result.brightness_stats.mean_luma
        response["stabilized"] = project.correction_result.stabilized
    return response


# --------------------------------------------------------- 5. subtitles+hook
class SubtitleLinesRequest(BaseModel):
    lines: List[dict]


class HookSelectRequest(BaseModel):
    hook: str


@app.get("/api/projects/{project_id}/subtitles")
def get_subtitles(project_id: str):
    project = _get_project_or_404(project_id)
    return {"lines": [{"start": s.start, "end": s.end, "text": s.text} for s in project.subtitle_lines]}


@app.patch("/api/projects/{project_id}/subtitles")
def update_subtitles(project_id: str, body: SubtitleLinesRequest):
    project = _get_project_or_404(project_id)
    project.subtitle_lines = [SubtitleLine(l["start"], l["end"], l["text"]) for l in body.lines]
    return {"lines": [{"start": s.start, "end": s.end, "text": s.text} for s in project.subtitle_lines]}


@app.get("/api/projects/{project_id}/hooks")
def get_hook_suggestions(project_id: str, topic: Optional[str] = None, max: int = 3):
    project = _get_project_or_404(project_id)
    if not project.category:
        raise HTTPException(status_code=400, detail="카테고리가 먼저 선택되어야 합니다.")
    if topic is not None:
        project.topic = topic
    if not project.topic.strip():
        raise HTTPException(status_code=400, detail="주제(topic)가 설정되어 있지 않습니다.")
    suggestions = generate_hook_suggestions(project.topic, project.category, max_suggestions=max)
    project.hook_suggestions = suggestions
    return {"suggestions": suggestions, "topic": project.topic}


@app.patch("/api/projects/{project_id}/hook")
def select_hook(project_id: str, body: HookSelectRequest):
    project = _get_project_or_404(project_id)
    project.selected_hook = body.hook
    return {"selectedHook": project.selected_hook}


# ---------------------------------------------------------------- 6. audio
class AudioSettingsRequest(BaseModel):
    bgmMood: Optional[str] = None
    bgmVolume: float = 0.18
    sfxEnabled: bool = True


def _run_audio_job(project: Project) -> None:
    job = project.job("audio")
    job.status = "running"
    job.error = None
    try:
        base_video = project.correction_result.output_path if project.correction_result else project.video_path

        library = audio_mix_mod.ensure_bgm_library(_shared_bgm_dir)
        mood = project.bgm_mood or (get_rule(project.category).default_bgm_mood if project.category else "neutral")
        track = library.get(mood) or library.get("neutral") or next(iter(library.values()))

        mixed_path = str(Path(project.workdir) / "audio_bgm.mp4")
        audio_mix_mod.mix_bgm(base_video, track.path, mixed_path, bgm_volume=project.bgm_volume)

        final_path = mixed_path
        if project.sfx_enabled:
            sfx_lib = audio_mix_mod.ensure_sfx_library(_shared_sfx_dir)
            cut_points = _cut_transition_points(project)
            sfx_out = str(Path(project.workdir) / "audio_final.mp4")
            audio_mix_mod.apply_sfx_at_cuts(mixed_path, sfx_out, cut_points, sfx_lib["pop"])
            final_path = sfx_out

        project.audio_output_path = final_path
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.get("/api/projects/{project_id}/bgm-library")
def get_bgm_library(project_id: str):
    _get_project_or_404(project_id)
    library = audio_mix_mod.ensure_bgm_library(_shared_bgm_dir)
    return {"tracks": [{"mood": t.mood, "label": t.label} for t in library.values()]}


@app.patch("/api/projects/{project_id}/audio-settings")
def update_audio_settings(project_id: str, body: AudioSettingsRequest):
    project = _get_project_or_404(project_id)
    project.bgm_mood = body.bgmMood
    project.bgm_volume = body.bgmVolume
    project.sfx_enabled = body.sfxEnabled
    return {"bgmMood": project.bgm_mood, "bgmVolume": project.bgm_volume, "sfxEnabled": project.sfx_enabled}


@app.post("/api/projects/{project_id}/audio")
def start_audio(project_id: str):
    project = _get_project_or_404(project_id)
    job = project.job("audio")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="이미 오디오 처리가 진행 중입니다.")
    _run_in_background(_run_audio_job, project)
    return {"status": "running"}


@app.get("/api/projects/{project_id}/audio")
def get_audio_status(project_id: str):
    project = _get_project_or_404(project_id)
    return project.job("audio").to_dict()


# ------------------------------------------------------- 7-8. confirm/export
@app.get("/api/projects/{project_id}/summary")
def get_summary(project_id: str):
    project = _get_project_or_404(project_id)
    return _project_summary(project)


class ExportRequest(BaseModel):
    draftName: str
    capcutDraftsDir: Optional[str] = None
    width: int = 1920
    height: int = 1080


def _run_export_job(project: Project, draft_name: str, capcut_drafts_dir: Optional[str], width: int, height: int) -> None:
    job = project.job("export")
    job.status = "running"
    job.error = None
    try:
        drafts_dir = capcut_drafts_dir or draft_builder.default_capcut_drafts_dir()
        if not drafts_dir:
            raise RuntimeError("CapCut 드래프트 폴더 경로를 찾을 수 없습니다. 직접 지정해주세요.")

        video_for_export = project.audio_output_path or (
            project.correction_result.output_path if project.correction_result else project.video_path
        )

        result_name = draft_builder.build_draft(
            video_path=video_for_export,
            keep_intervals=project.keep_intervals,
            subtitle_lines=project.subtitle_lines,
            draft_name=draft_name,
            capcut_drafts_dir=drafts_dir,
            width=width,
            height=height,
            hook_text=project.selected_hook,
        )
        project.draft_name = result_name
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)


@app.post("/api/projects/{project_id}/export")
def start_export(project_id: str, body: ExportRequest):
    project = _get_project_or_404(project_id)
    job = project.job("export")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="이미 내보내기가 진행 중입니다.")
    _run_in_background(_run_export_job, project, body.draftName, body.capcutDraftsDir, body.width, body.height)
    return {"status": "running"}


@app.get("/api/projects/{project_id}/export")
def get_export_status(project_id: str):
    project = _get_project_or_404(project_id)
    response = project.job("export").to_dict()
    response["draftName"] = project.draft_name
    return response


# ------------------------------------------------- MODE 2: 촬영 가이드
# MODE 1과 입출력이 완전히 달라(영상 파일 없음, 텍스트만 입출력) project_store를
# 전혀 쓰지 않는 상태 없는(stateless) 엔드포인트로 분리한다. 생성이 빠르고
# 순수 함수라 백그라운드 작업/폴링도 필요 없다.
class ShootingGuideRequest(BaseModel):
    topic: str
    category: str
    productOrSituation: str
    targetDuration: str
    location: str = ""
    equipment: str = ""
    faceOnCamera: bool = False
    mustShowScenes: str = ""
    availableTime: str = ""
    notes: str = ""


@app.post("/api/shooting-guide")
def create_shooting_guide(body: ShootingGuideRequest):
    try:
        category = ContentCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 카테고리: {body.category}")

    guide_input = ShootingGuideInput(
        topic=body.topic,
        category=category,
        product_or_situation=body.productOrSituation,
        target_duration=body.targetDuration,
        location=body.location,
        equipment=body.equipment,
        face_on_camera=body.faceOnCamera,
        must_show_scenes=body.mustShowScenes,
        available_time=body.availableTime,
        notes=body.notes,
    )
    try:
        plan = generate_shooting_plan(guide_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "topic": plan.topic,
        "category": plan.category.value,
        "categoryLabel": plan.category_label,
        "targetDurationLabel": plan.target_duration_label,
        "totalEstimatedSeconds": plan.total_estimated_seconds,
        "equipmentTips": plan.equipment_tips,
        "warnings": plan.warnings,
        "shots": [
            {
                "order": s.order,
                "angle": s.angle,
                "angleLabel": s.angle_label,
                "title": s.title,
                "description": s.description,
                "estimatedSeconds": s.estimated_seconds,
                "tip": s.tip,
            }
            for s in plan.shots
        ],
    }
