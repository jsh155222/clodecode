"""웹 프론트엔드(webapp/)가 호출하는 로컬 FastAPI 백엔드.

MODE 1(AI 자동 편집)의 3~9단계를 실제 capcut_auto 엔진(silence/transcribe/stutter/
cutlist/subtitles/visual_correction/audio_mix/hooks/draft_builder)에 연결한다.

실행:
    uvicorn capcut_auto.server:app --port 8000

로컬 1인 사용을 전제로 상태는 프로세스 메모리에만 둔다 (project_store.py 참고).
"""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audio_mix as audio_mix_mod
from . import bgm_recommend as bgm_recommend_mod
from . import category_rules as category_rules_mod
from . import cutlist as cutlist_mod
from . import draft_builder
from . import sfx_recommend as sfx_recommend_mod
from . import silence as silence_mod
from . import stutter as stutter_mod
from . import subtitles as subtitles_mod
from . import visual_correction as visual_correction_mod
from .ai.video_structure import VideoSection, VideoSectionRole
from .categories import CATEGORY_LABELS, ContentCategory, get_rule
from .hooks import generate_hook_suggestions
from .project_store import CutCandidate, Project, ProjectStore
from .shooting_guide import ShootingGuideInput, generate_shooting_plan
from .shooting_guide_v2 import ShootingGuideInputV2, generate_shooting_plan_v2
from .subtitles import SubtitleLine
from .timeline import Interval
from .transcribe import transcribe as transcribe_audio
from .visual import reframe as reframe_mod
from .visual import subject_detection as subject_detection_mod
from .visual.frame_extraction import extract_frame_at


# CWD 상대 경로가 기본값이지만(기존 동작 그대로), 데스크톱 앱(desktop/main.js)처럼
# 실행 파일이 있는 위치(예: Program Files, 쓰기 권한 없음)와 실제로 쓰기 가능한 위치가
# 다른 경우를 위해 환경변수로 덮어쓸 수 있게 한다.
APP_STATE_DIR = Path(os.environ.get("CAPCUT_AUTO_STATE_DIR", "capcut_auto_server_work"))
store = ProjectStore(str(APP_STATE_DIR / "projects"))
_shared_bgm_dir = str(APP_STATE_DIR / "shared_bgm")
_shared_sfx_dir = str(APP_STATE_DIR / "shared_sfx")
_shared_sfx_v2_dir = str(APP_STATE_DIR / "shared_sfx_v2")

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


def _original_timeline_cut_boundaries(project: Project) -> List[float]:
    """원본(컷 반영 전) 영상 시간 기준 컷 경계.

    _cut_transition_points()는 압축된(컷 이후) 타임라인 기준 누적 길이라서, 이 단계의
    오디오 작업이 실제로 다루는 원본 길이 그대로의 비디오 파일(visual_correction 결과 -
    CapCut 드래프트만 keep_intervals로 실제 트리밍하고, 그 전 단계 mp4들은 전부 원본
    길이 그대로다)에 그 값을 그대로 쓰면 두 번째 컷부터 위치가 어긋난다. 효과음 추천
    섹션은 원본 시간 기준이어야 하므로 별도로 계산한다.
    """
    return [iv.end for iv in project.keep_intervals[:-1]]


def _heuristic_video_sections(project: Project) -> List[VideoSection]:
    """실제 AI 영상 구조 분석(ai/video_structure.py) 없이도 효과음 추천이 동작하도록 만든
    규칙 기반 근사치. HOOK/RESULT는 영상 처음·끝 일부, TRANSITION은 각 컷 경계다.
    ANTHROPIC_API_KEY가 없어도 항상 동작하도록 이 서버의 다른 3/4/6단계와 같은 방식
    (규칙 기반)으로 만들었다 - "영상 내용을 이해해서" 정확히 분류한 것은 아니라는 한계가 있다.
    """
    duration = project.total_duration or 0.0
    if duration <= 0:
        return []
    edge = min(3.0, duration / 3)
    sections = [
        VideoSection(0.0, edge, VideoSectionRole.HOOK, ""),
        VideoSection(max(edge, duration - edge), duration, VideoSectionRole.RESULT, ""),
    ]
    for t in _original_timeline_cut_boundaries(project):
        sections.append(VideoSection(max(0.0, t - 0.2), min(duration, t + 0.2), VideoSectionRole.TRANSITION, ""))
    return sections


def _sfx_recommendation_to_dict(rec: "sfx_recommend_mod.SfxRecommendation") -> dict:
    return {
        "time": rec.time,
        "purpose": rec.purpose.value,
        "purposeLabel": rec.purpose.label,
        "candidates": [
            {
                "assetId": c.asset.id,
                "label": c.asset.label,
                "reason": c.reason,
                "previewUrl": f"/api/sfx-preview/{c.asset.id}",
            }
            for c in rec.candidates
        ],
        "selectedAssetId": rec.selected_asset_id,
        "approved": rec.approved,
    }


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
        video_path = project.video_path
        if project.reframe_approved and project.reframe_crop is not None:
            cropped_path = str(Path(project.workdir) / "reframed.mp4")
            reframe_mod.render_static_crop(project.video_path, project.reframe_crop, cropped_path)
            video_path = cropped_path

        result = visual_correction_mod.auto_correct(
            video_path, str(Path(project.workdir) / "correction"), stabilize_enabled=project.stabilize_enabled
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


def _crop_to_dict(crop: "reframe_mod.CropWindow") -> dict:
    return {
        "x": crop.x,
        "y": crop.y,
        "width": crop.width,
        "height": crop.height,
        "zoom": crop.zoom,
        "subjectFullyContained": crop.subject_fully_contained,
    }


@app.get("/api/projects/{project_id}/reframe-suggestion")
def get_reframe_suggestion(project_id: str, recompute: bool = False):
    """9:16 크롭 후보를 계산하고, 승인 전 미리보기 이미지까지 렌더링해둔다.

    이미 계산된 후보가 있으면(예: 화면을 벗어났다가 다시 돌아오거나, React가 effect를
    두 번 실행하는 경우) 그걸 그대로 반환한다 - 매번 새로 계산하면 사용자가 이미 승인한
    상태(reframe_approved)를 조용히 되돌려버리는 문제가 생긴다. recompute=true로 명시적
    요청할 때만 다시 계산한다("다시 분석" 같은 사용자 액션용).
    """
    project = _get_project_or_404(project_id)

    if project.reframe_crop is not None and not recompute:
        return {
            "crop": _crop_to_dict(project.reframe_crop),
            "faceDetected": project.reframe_face_detected,
            "previewUrl": f"/api/projects/{project_id}/reframe-preview",
            "approved": project.reframe_approved,
        }

    try:
        width, height = silence_mod.get_video_resolution(project.video_path)
        duration = project.total_duration or silence_mod.get_duration(project.video_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    sample_time = duration * 0.4
    reframe_dir = Path(project.workdir) / "reframe"
    reframe_dir.mkdir(parents=True, exist_ok=True)
    sample_frame_path = str(reframe_dir / "sample.jpg")
    extract_frame_at(project.video_path, sample_time, sample_frame_path)

    faces = subject_detection_mod.detect_faces(sample_frame_path)
    confident_face = next((f for f in faces if subject_detection_mod.is_confident(f)), None)
    bbox = confident_face.bbox if confident_face else None

    crop = reframe_mod.compute_crop_window(width, height, bbox)
    project.reframe_crop = crop
    project.reframe_face_detected = bbox is not None
    project.reframe_approved = False  # 새로 계산되면 다시 승인받아야 한다

    preview_path = str(reframe_dir / "preview.jpg")
    reframe_mod.render_crop_preview_image(project.video_path, crop, preview_path, sample_time)
    project.reframe_preview_path = preview_path

    return {
        "crop": _crop_to_dict(crop),
        "faceDetected": project.reframe_face_detected,
        "previewUrl": f"/api/projects/{project_id}/reframe-preview",
        "approved": project.reframe_approved,
    }


class ReframeApprovalRequest(BaseModel):
    approved: bool


@app.patch("/api/projects/{project_id}/reframe-approval")
def update_reframe_approval(project_id: str, body: ReframeApprovalRequest):
    project = _get_project_or_404(project_id)
    if body.approved and project.reframe_crop is None:
        raise HTTPException(status_code=400, detail="먼저 리프레이밍 후보를 계산해야 합니다.")
    project.reframe_approved = body.approved
    return {"approved": project.reframe_approved}


@app.get("/api/projects/{project_id}/reframe-preview")
def get_reframe_preview(project_id: str):
    project = _get_project_or_404(project_id)
    if not project.reframe_preview_path or not Path(project.reframe_preview_path).exists():
        raise HTTPException(status_code=404, detail="미리보기 이미지가 아직 없습니다.")
    return FileResponse(project.reframe_preview_path, media_type="image/jpeg")


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
        rule_set = category_rules_mod.load_category_rule_set(project.category) if project.category else None
        bgm_rec = project.bgm_recommendation or bgm_recommend_mod.recommend_bgm_metadata(project.category, rule_set)
        mood = project.bgm_mood or bgm_rec.mood
        track = library.get(mood) or library.get("neutral") or next(iter(library.values()))

        # project.words는 컷 반영 전(원본) 타임라인 그대로다 - 이 단계에서 다루는 mp4도
        # 항상 원본 길이 그대로(실제 트리밍은 마지막 CapCut 내보내기에서만 일어남)라서
        # 발화 구간 좌표가 그대로 맞는다.
        voice_intervals = [Interval(w.start, w.end) for w in project.words] if project.words else []

        mixed_path = str(Path(project.workdir) / "audio_bgm.mp4")
        audio_mix_mod.mix_bgm(
            base_video,
            track.path,
            mixed_path,
            bgm_volume=project.bgm_volume,
            voice_intervals=voice_intervals,
            duck_volume_ratio=bgm_rec.duck_volume_ratio,
        )

        final_path = mixed_path
        if project.sfx_enabled:
            sfx_out = str(Path(project.workdir) / "audio_final.mp4")
            approved_placements = sfx_recommend_mod.apply_approved_sfx(project.sfx_recommendations)
            if approved_placements:
                placements = [
                    (p.time, str(Path(_shared_sfx_v2_dir) / f"{p.asset_id}.m4a")) for p in approved_placements
                ]
                audio_mix_mod.apply_multiple_sfx(mixed_path, sfx_out, placements)
            else:
                # 아직 효과음 추천을 받지 않았거나 하나도 승인하지 않았다면 기존 방식대로
                # 컷 전환마다 짧은 pop 소리를 넣는다 (하위 호환 기본 동작).
                sfx_lib = audio_mix_mod.ensure_sfx_library(_shared_sfx_dir)
                cut_points = _cut_transition_points(project)
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


@app.get("/api/projects/{project_id}/bgm-recommendation")
def get_bgm_recommendation(project_id: str):
    project = _get_project_or_404(project_id)
    rule_set = category_rules_mod.load_category_rule_set(project.category) if project.category else None
    rec = bgm_recommend_mod.recommend_bgm_metadata(project.category, rule_set)
    project.bgm_recommendation = rec
    return {
        "mood": rec.mood,
        "moodLabel": rec.mood_label,
        "tempoRangeBpm": list(rec.tempo_range_bpm),
        "energy": rec.energy.value,
        "energyLabel": rec.energy.label,
        "hasVocals": rec.has_vocals,
        "searchKeywords": rec.search_keywords,
        "duckDuringVoice": rec.duck_during_voice,
        "duckVolumeRatio": rec.duck_volume_ratio,
    }


@app.get("/api/projects/{project_id}/sfx-suggestions")
def get_sfx_suggestions(project_id: str):
    project = _get_project_or_404(project_id)
    if project.total_duration is None:
        raise HTTPException(status_code=400, detail="먼저 3단계 분석을 완료해야 합니다.")

    rule_set = category_rules_mod.load_category_rule_set(project.category) if project.category else None
    sections = _heuristic_video_sections(project)
    library = sfx_recommend_mod.ensure_sfx_asset_library(_shared_sfx_v2_dir)
    recommendations = sfx_recommend_mod.recommend_sfx_for_scenes(
        sections,
        project.words,
        protected_intervals=[],
        category=project.category,
        category_rule_set=rule_set,
        library=library,
    )
    project.sfx_recommendations = recommendations
    return {"recommendations": [_sfx_recommendation_to_dict(r) for r in recommendations]}


class SfxDecisionRequest(BaseModel):
    time: float
    approved: bool
    selectedAssetId: Optional[str] = None


@app.patch("/api/projects/{project_id}/sfx-suggestions")
def update_sfx_decision(project_id: str, body: SfxDecisionRequest):
    project = _get_project_or_404(project_id)
    for rec in project.sfx_recommendations:
        if abs(rec.time - body.time) < 1e-6:
            rec.approved = body.approved
            rec.selected_asset_id = body.selectedAssetId
            break
    else:
        raise HTTPException(status_code=404, detail="해당 효과음 추천을 찾을 수 없습니다.")
    return {"recommendations": [_sfx_recommendation_to_dict(r) for r in project.sfx_recommendations]}


@app.get("/api/sfx-preview/{asset_id}")
def get_sfx_preview(asset_id: str):
    path = Path(_shared_sfx_v2_dir) / f"{asset_id}.m4a"
    if not path.exists():
        raise HTTPException(status_code=404, detail="효과음 파일을 찾을 수 없습니다.")
    return FileResponse(str(path), media_type="audio/mp4")


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


# ---------------------------------------------------- MODE 2 v2: 확장 촬영 가이드
# 새 ShootingGuideInput 스키마(topic/category/subject/targetDurationSeconds/...)를 그대로
# 반영한 별도 엔드포인트. 기존 /api/shooting-guide(v1)는 그대로 두고 병행 제공한다 -
# MODE1 인계(continueToAutoEdit)는 아직 v1 스키마만 지원하므로 v2는 계획 열람/체크리스트
# 전용으로 쓰인다(알려진 범위 제한, README/보고서에 명시).
class ShootingGuideRequestV2(BaseModel):
    topic: str
    category: str
    subject: str
    targetDurationSeconds: int
    location: Optional[str] = None
    equipment: Optional[List[str]] = None
    showFace: Optional[bool] = None
    availableShootingMinutes: Optional[int] = None
    mustShowSteps: Optional[List[str]] = None
    additionalNotes: Optional[str] = None


@app.post("/api/shooting-guide-v2")
def create_shooting_guide_v2(body: ShootingGuideRequestV2):
    try:
        category = ContentCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 카테고리: {body.category}")

    guide_input = ShootingGuideInputV2(
        topic=body.topic,
        category=category,
        subject=body.subject,
        target_duration_seconds=body.targetDurationSeconds,
        location=body.location,
        equipment=body.equipment,
        show_face=body.showFace,
        available_shooting_minutes=body.availableShootingMinutes,
        must_show_steps=body.mustShowSteps,
        additional_notes=body.additionalNotes,
    )
    try:
        plan = generate_shooting_plan_v2(guide_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "topic": plan.topic,
        "category": plan.category.value,
        "categoryLabel": plan.category_label,
        "subject": plan.subject,
        "targetDurationSeconds": plan.target_duration_seconds,
        "cutCountRange": list(plan.cut_count_range),
        "shotCount": plan.shot_count,
        "equipment": plan.equipment,
        "totalRecommendedShootingSeconds": plan.total_recommended_shooting_seconds,
        "warnings": plan.warnings,
        "shots": [
            {
                "order": s.order,
                "role": s.role,
                "roleLabel": s.role_label,
                "description": s.description,
                "camera": {
                    "angle": s.camera.angle,
                    "distance": s.camera.distance,
                    "height": s.camera.height,
                    "direction": s.camera.direction,
                    "movement": s.camera.movement,
                },
                "recommendedShootingSeconds": s.recommended_shooting_seconds,
                "subtitleSafeZoneHint": s.subtitle_safe_zone_hint,
                "mandatory": s.mandatory,
            }
            for s in plan.shots
        ],
    }


# ------------------------------------------------------- 정적 빌드 프론트엔드 서빙
# `npm run build`로 만든 webapp/dist가 있으면 같은 프로세스가 API + 화면을 함께 서빙한다.
# 데스크톱 앱(desktop/)이 uvicorn 하나만 띄우면 되도록 하기 위함 - 개발 중에는(vite dev
# 서버를 따로 띄우는 워크플로) dist가 없을 수 있으므로 있을 때만 마운트한다. 반드시 다른
# 모든 /api/... 라우트보다 뒤에(파일 맨 끝에) 마운트해야 "/"가 API 경로를 가리지 않는다.
def _maybe_mount_frontend(fastapi_app: FastAPI, dist_dir: Path) -> bool:
    if not (dist_dir / "index.html").is_file():
        return False
    fastapi_app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    return True


_frontend_dist_dir = Path(__file__).resolve().parent.parent / "webapp" / "dist"
_maybe_mount_frontend(app, _frontend_dist_dir)
