"""웹 백엔드(server.py)가 사용하는 인메모리 프로젝트 상태 저장소.

주의: 이 프로젝트는 로컬 1인 사용을 전제로 한 도구라 DB 없이 프로세스 메모리에만
상태를 둔다. 서버를 재시작하면 진행 중이던 프로젝트는 사라진다 (이번 단계의
의도적인 범위 제한 — 필요해지면 JSON 파일 저장으로 쉽게 확장 가능한 구조로 분리해 둠).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .bgm_recommend import BgmMetadataRecommendation
from .categories import ContentCategory
from .sfx_recommend import SfxRecommendation
from .subtitles import SubtitleLine
from .timeline import Interval
from .transcribe import Word
from .visual_correction import VisualCorrectionResult


@dataclass
class JobState:
    status: str = "idle"  # idle | running | done | error
    log: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"status": self.status, "log": list(self.log), "error": self.error}


@dataclass
class CutCandidate:
    id: str
    start: float
    end: float
    source: str  # "silence" | "filler" | "repetition"
    enabled: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "start": self.start, "end": self.end, "source": self.source, "enabled": self.enabled}


@dataclass
class Project:
    id: str
    video_path: str
    original_filename: str
    workdir: str
    category: Optional[ContentCategory] = None
    topic: str = ""

    total_duration: Optional[float] = None
    words: List[Word] = field(default_factory=list)
    cut_candidates: List[CutCandidate] = field(default_factory=list)
    keep_intervals: List[Interval] = field(default_factory=list)

    subtitle_lines: List[SubtitleLine] = field(default_factory=list)
    hook_suggestions: List[str] = field(default_factory=list)
    selected_hook: Optional[str] = None

    correction_result: Optional[VisualCorrectionResult] = None
    stabilize_enabled: bool = True

    bgm_mood: Optional[str] = None
    bgm_volume: float = 0.18
    sfx_enabled: bool = True
    audio_output_path: Optional[str] = None
    sfx_recommendations: List[SfxRecommendation] = field(default_factory=list)
    bgm_recommendation: Optional[BgmMetadataRecommendation] = None

    draft_name: Optional[str] = None

    jobs: Dict[str, JobState] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def job(self, name: str) -> JobState:
        with self.lock:
            if name not in self.jobs:
                self.jobs[name] = JobState()
            return self.jobs[name]


class ProjectStore:
    def __init__(self, base_workdir: str):
        self._lock = threading.Lock()
        self._projects: Dict[str, Project] = {}
        self.base_workdir = Path(base_workdir)
        self.base_workdir.mkdir(parents=True, exist_ok=True)

    def create(
        self, video_path: str, original_filename: str, category: Optional[ContentCategory], topic: str = ""
    ) -> Project:
        project_id = uuid.uuid4().hex[:12]
        workdir = str(self.base_workdir / project_id)
        Path(workdir).mkdir(parents=True, exist_ok=True)
        project = Project(
            id=project_id,
            video_path=video_path,
            original_filename=original_filename,
            workdir=workdir,
            category=category,
            topic=topic,
        )
        with self._lock:
            self._projects[project_id] = project
        return project

    def get(self, project_id: str) -> Project:
        with self._lock:
            project = self._projects.get(project_id)
        if project is None:
            raise KeyError(project_id)
        return project
