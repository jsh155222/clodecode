"""FastAPI 백엔드(server.py) 오케스트레이션 테스트.

무거운 실제 처리(ffmpeg/whisper/pycapcut)는 모두 mock으로 대체해 빠르고
결정론적으로 검증한다. 각 하위 모듈(visual_correction/audio_mix/draft_builder 등)의
"진짜로 동작하는지"는 각자의 통합 테스트(test_*_integration.py)와 이번 세션에서
수행한 수동 end-to-end 검증에서 이미 확인했다.
"""

import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from capcut_auto import server as server_mod
from capcut_auto.project_store import ProjectStore
from capcut_auto.timeline import Interval
from capcut_auto.transcribe import Word
from capcut_auto.visual_correction import BrightnessStats, CorrectionParams, VisualCorrectionResult
from capcut_auto.audio_mix import BgmTrack


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self._store_patch = mock.patch.object(
            server_mod, "store", ProjectStore(str(Path(self.tmpdir.name) / "projects"))
        )
        self._state_dir_patch = mock.patch.object(server_mod, "APP_STATE_DIR", Path(self.tmpdir.name))
        self._store_patch.start()
        self._state_dir_patch.start()
        self.client = TestClient(server_mod.app)

    def tearDown(self):
        self._store_patch.stop()
        self._state_dir_patch.stop()
        self.tmpdir.cleanup()

    def _create_project(self, category="FOOD", topic="원룸 정리 루틴"):
        response = self.client.post(
            "/api/projects",
            files={"video": ("test.mp4", io.BytesIO(b"fake video bytes"), "video/mp4")},
            data={"category": category, "topic": topic},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class TestCreateProject(ServerTestCase):
    def test_create_project_returns_summary(self):
        data = self._create_project(category="FOOD", topic="원룸 정리")
        self.assertIn("id", data)
        self.assertEqual(data["category"], "FOOD")
        self.assertEqual(data["categoryLabel"], "음식")
        self.assertEqual(data["topic"], "원룸 정리")

    def test_invalid_category_returns_400(self):
        response = self.client.post(
            "/api/projects",
            files={"video": ("test.mp4", io.BytesIO(b"x"), "video/mp4")},
            data={"category": "NOT_A_CATEGORY"},
        )
        self.assertEqual(response.status_code, 400)

    def test_get_unknown_project_returns_404(self):
        response = self.client.get("/api/projects/does-not-exist")
        self.assertEqual(response.status_code, 404)


class TestAnalyzeFlow(ServerTestCase):
    def _mock_analyze_dependencies(self):
        words = [
            Word(0.5, 0.8, "어"),
            Word(1.0, 1.4, "안녕하세요"),
            Word(6.0, 6.5, "반갑습니다"),
        ]
        return [
            mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0),
            mock.patch.object(server_mod.silence_mod, "extract_audio", return_value="/tmp/fake_audio.wav"),
            mock.patch.object(server_mod.silence_mod, "detect_silence", return_value=[Interval(2.0, 5.0)]),
            mock.patch.object(server_mod, "transcribe_audio", return_value=words),
        ]

    def test_analyze_completes_and_produces_cut_candidates(self):
        project = self._create_project()
        patches = self._mock_analyze_dependencies()
        for p in patches:
            p.start()
        try:
            start_resp = self.client.post(f"/api/projects/{project['id']}/analyze")
            self.assertEqual(start_resp.status_code, 200)
            self.assertEqual(start_resp.json()["status"], "running")

            ok = _wait_until(
                lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] != "running"
            )
            self.assertTrue(ok)

            result = self.client.get(f"/api/projects/{project['id']}/analyze").json()
            self.assertEqual(result["status"], "done")
            self.assertAlmostEqual(result["totalDuration"], 10.0)
            self.assertGreaterEqual(len(result["cutCandidates"]), 1)
            self.assertLess(result["keptDuration"], 10.0)
        finally:
            for p in patches:
                p.stop()

    def test_analyze_conflict_returns_409_while_running(self):
        project = self._create_project()
        started = mock.Mock()

        def slow_get_duration(_path):
            started.set = True
            time.sleep(0.3)
            return 10.0

        with mock.patch.object(server_mod.silence_mod, "get_duration", side_effect=slow_get_duration), \
             mock.patch.object(server_mod.silence_mod, "extract_audio", return_value="/tmp/fake.wav"), \
             mock.patch.object(server_mod.silence_mod, "detect_silence", return_value=[]), \
             mock.patch.object(server_mod, "transcribe_audio", return_value=[]):
            self.client.post(f"/api/projects/{project['id']}/analyze")
            time.sleep(0.05)  # 백그라운드 스레드가 running으로 넘어갈 시간을 준다
            second = self.client.post(f"/api/projects/{project['id']}/analyze")
            self.assertEqual(second.status_code, 409)

            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] == "done")

    def test_analyze_failure_reports_error_status(self):
        project = self._create_project()
        with mock.patch.object(server_mod.silence_mod, "get_duration", side_effect=RuntimeError("ffmpeg 없음")):
            self.client.post(f"/api/projects/{project['id']}/analyze")
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] != "running")
            result = self.client.get(f"/api/projects/{project['id']}/analyze").json()
            self.assertEqual(result["status"], "error")
            self.assertIn("ffmpeg", result["error"])


class TestCutReview(ServerTestCase):
    def _analyzed_project(self):
        project = self._create_project()
        words = [Word(0.5, 0.8, "어"), Word(1.0, 1.4, "안녕하세요"), Word(6.0, 6.5, "반갑습니다")]
        with mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0), \
             mock.patch.object(server_mod.silence_mod, "extract_audio", return_value="/tmp/a.wav"), \
             mock.patch.object(server_mod.silence_mod, "detect_silence", return_value=[Interval(2.0, 5.0)]), \
             mock.patch.object(server_mod, "transcribe_audio", return_value=words):
            self.client.post(f"/api/projects/{project['id']}/analyze")
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] != "running")
        return project

    def test_toggling_off_a_cut_increases_kept_duration(self):
        project = self._analyzed_project()
        before = self.client.get(f"/api/projects/{project['id']}/cuts").json()
        candidate_id = before["cutCandidates"][0]["id"]
        kept_before = before["keptDuration"]

        after = self.client.patch(f"/api/projects/{project['id']}/cuts", json={"id": candidate_id, "enabled": False})
        self.assertEqual(after.status_code, 200)
        kept_after = after.json()["keptDuration"]

        self.assertGreater(kept_after, kept_before)

    def test_toggle_unknown_candidate_returns_404(self):
        project = self._analyzed_project()
        response = self.client.patch(f"/api/projects/{project['id']}/cuts", json={"id": "nope", "enabled": False})
        self.assertEqual(response.status_code, 404)


class TestVisualCorrection(ServerTestCase):
    def test_correction_flow(self):
        project = self._create_project()
        fake_result = VisualCorrectionResult(
            output_path="/tmp/corrected.mp4",
            brightness_stats=BrightnessStats(mean_luma=60.0, stddev_luma=10.0, sample_count=30),
            correction_params=CorrectionParams(brightness=0.1, contrast=1.1),
            stabilized=True,
        )
        with mock.patch.object(server_mod.visual_correction_mod, "auto_correct", return_value=fake_result):
            start = self.client.post(f"/api/projects/{project['id']}/correction", json={"stabilize": True})
            self.assertEqual(start.status_code, 200)
            _wait_until(
                lambda: self.client.get(f"/api/projects/{project['id']}/correction").json()["status"] != "running"
            )
            result = self.client.get(f"/api/projects/{project['id']}/correction").json()
            self.assertEqual(result["status"], "done")
            self.assertEqual(result["brightness"], 0.1)
            self.assertTrue(result["stabilized"])


class TestHooksAndSubtitles(ServerTestCase):
    def test_hooks_require_topic_and_category(self):
        response = self.client.post(
            "/api/projects",
            files={"video": ("t.mp4", io.BytesIO(b"x"), "video/mp4")},
            data={"topic": "주제"},  # 카테고리 없음
        )
        project = response.json()
        result = self.client.get(f"/api/projects/{project['id']}/hooks")
        self.assertEqual(result.status_code, 400)

    def test_hooks_returns_suggestions_including_topic(self):
        project = self._create_project(category="TRAVEL", topic="숨은 여행지")
        result = self.client.get(f"/api/projects/{project['id']}/hooks?max=2")
        self.assertEqual(result.status_code, 200)
        suggestions = result.json()["suggestions"]
        self.assertEqual(len(suggestions), 2)
        for s in suggestions:
            self.assertIn("숨은 여행지", s)

    def test_select_hook(self):
        project = self._create_project()
        response = self.client.patch(f"/api/projects/{project['id']}/hook", json={"hook": "이 영상 놓치지 마세요"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selectedHook"], "이 영상 놓치지 마세요")

    def test_update_subtitles(self):
        project = self._create_project()
        response = self.client.patch(
            f"/api/projects/{project['id']}/subtitles",
            json={"lines": [{"start": 0.0, "end": 1.0, "text": "수정된 자막"}]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lines"][0]["text"], "수정된 자막")


class TestAudio(ServerTestCase):
    def test_bgm_library_lists_tracks(self):
        project = self._create_project()
        fake_library = {
            "warm": BgmTrack(mood="warm", label="따뜻한", path="/tmp/warm.m4a"),
            "neutral": BgmTrack(mood="neutral", label="기본", path="/tmp/neutral.m4a"),
        }
        with mock.patch.object(server_mod.audio_mix_mod, "ensure_bgm_library", return_value=fake_library):
            response = self.client.get(f"/api/projects/{project['id']}/bgm-library")
            self.assertEqual(response.status_code, 200)
            moods = {t["mood"] for t in response.json()["tracks"]}
            self.assertEqual(moods, {"warm", "neutral"})

    def test_audio_settings_and_processing_flow(self):
        project = self._create_project(category="FOOD")
        settings_resp = self.client.patch(
            f"/api/projects/{project['id']}/audio-settings",
            json={"bgmMood": "warm", "bgmVolume": 0.25, "sfxEnabled": True},
        )
        self.assertEqual(settings_resp.status_code, 200)

        fake_library = {"warm": BgmTrack(mood="warm", label="따뜻한", path="/tmp/warm.m4a")}
        with mock.patch.object(server_mod.audio_mix_mod, "ensure_bgm_library", return_value=fake_library), \
             mock.patch.object(server_mod.audio_mix_mod, "mix_bgm", return_value="/tmp/mixed.mp4") as mix_mock, \
             mock.patch.object(server_mod.audio_mix_mod, "ensure_sfx_library", return_value={"pop": "/tmp/pop.m4a"}), \
             mock.patch.object(server_mod.audio_mix_mod, "apply_sfx_at_cuts", return_value="/tmp/final.mp4") as sfx_mock:
            start = self.client.post(f"/api/projects/{project['id']}/audio")
            self.assertEqual(start.status_code, 200)
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/audio").json()["status"] != "running")
            status = self.client.get(f"/api/projects/{project['id']}/audio").json()
            self.assertEqual(status["status"], "done")
            mix_mock.assert_called_once()
            sfx_mock.assert_called_once()


class TestExport(ServerTestCase):
    def test_export_calls_draft_builder_with_hook(self):
        project = self._create_project()
        self.client.patch(f"/api/projects/{project['id']}/hook", json={"hook": "훅 문구"})

        with mock.patch.object(server_mod.draft_builder, "build_draft", return_value="my_draft") as build_mock:
            start = self.client.post(
                f"/api/projects/{project['id']}/export",
                json={"draftName": "my_draft", "capcutDraftsDir": "/tmp/drafts"},
            )
            self.assertEqual(start.status_code, 200)
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/export").json()["status"] != "running")

            result = self.client.get(f"/api/projects/{project['id']}/export").json()
            self.assertEqual(result["status"], "done")
            self.assertEqual(result["draftName"], "my_draft")

            _, kwargs = build_mock.call_args
            self.assertEqual(kwargs["hook_text"], "훅 문구")

    def test_export_without_drafts_dir_reports_error(self):
        project = self._create_project()
        with mock.patch.object(server_mod.draft_builder, "default_capcut_drafts_dir", return_value=None):
            self.client.post(f"/api/projects/{project['id']}/export", json={"draftName": "d"})
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/export").json()["status"] != "running")
            result = self.client.get(f"/api/projects/{project['id']}/export").json()
            self.assertEqual(result["status"], "error")


class TestSummary(ServerTestCase):
    def test_summary_reflects_project_state(self):
        project = self._create_project(category="BEAUTY", topic="발색 테스트")
        response = self.client.get(f"/api/projects/{project['id']}/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["category"], "BEAUTY")
        self.assertEqual(data["categoryLabel"], "뷰티")
        self.assertFalse(data["correctionApplied"])
        self.assertFalse(data["audioApplied"])


class TestShootingGuideEndpoint(ServerTestCase):
    def test_generates_plan_for_valid_input(self):
        response = self.client.post(
            "/api/shooting-guide",
            json={
                "topic": "원룸 정리 루틴",
                "category": "LIVING",
                "productOrSituation": "옷장 정리",
                "targetDuration": "1_TO_3MIN",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["categoryLabel"], "살림")
        self.assertGreater(len(data["shots"]), 0)
        self.assertEqual(data["shots"][0]["order"], 1)
        self.assertIn("angleLabel", data["shots"][0])

    def test_optional_fields_affect_output(self):
        response = self.client.post(
            "/api/shooting-guide",
            json={
                "topic": "김치볶음밥 레시피",
                "category": "FOOD",
                "productOrSituation": "김치볶음밥",
                "targetDuration": "UNDER_1MIN",
                "equipment": "삼각대",
                "faceOnCamera": False,
                "mustShowScenes": "완성 후 한입 먹는 장면",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any("삼각대" in tip for tip in data["equipmentTips"]))
        self.assertTrue(any(s["description"] == "완성 후 한입 먹는 장면" for s in data["shots"]))
        self.assertNotIn("FACE_TALK", [s["angle"] for s in data["shots"]])

    def test_invalid_category_returns_400(self):
        response = self.client.post(
            "/api/shooting-guide",
            json={
                "topic": "주제",
                "category": "NOT_REAL",
                "productOrSituation": "상황",
                "targetDuration": "1_TO_3MIN",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_topic_returns_400(self):
        response = self.client.post(
            "/api/shooting-guide",
            json={
                "topic": "   ",
                "category": "TRAVEL",
                "productOrSituation": "상황",
                "targetDuration": "1_TO_3MIN",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_required_field_returns_422(self):
        response = self.client.post(
            "/api/shooting-guide",
            json={"topic": "주제", "category": "TRAVEL"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
