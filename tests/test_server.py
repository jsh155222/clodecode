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
from capcut_auto.sfx_recommend import SfxAsset, SfxPurpose
from capcut_auto.visual.reframe import CropWindow


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

    def test_correction_applies_approved_crop_before_auto_correct(self):
        project = self._create_project()
        crop = CropWindow(x=10.0, y=0.0, width=600.0, height=1080.0, zoom=1.0, subject_fully_contained=True)
        proj_obj = server_mod.store.get(project["id"])
        proj_obj.reframe_crop = crop
        proj_obj.reframe_approved = True

        fake_result = VisualCorrectionResult(
            output_path="/tmp/corrected.mp4",
            brightness_stats=BrightnessStats(mean_luma=60.0, stddev_luma=10.0, sample_count=30),
            correction_params=CorrectionParams(brightness=0.0, contrast=1.0),
            stabilized=False,
        )
        with mock.patch.object(server_mod.reframe_mod, "render_static_crop", return_value="/tmp/reframed.mp4") as crop_mock, \
             mock.patch.object(server_mod.visual_correction_mod, "auto_correct", return_value=fake_result) as correct_mock:
            self.client.post(f"/api/projects/{project['id']}/correction", json={"stabilize": False})
            _wait_until(
                lambda: self.client.get(f"/api/projects/{project['id']}/correction").json()["status"] != "running"
            )
            crop_mock.assert_called_once()
            self.assertEqual(crop_mock.call_args[0][0], proj_obj.video_path)
            self.assertEqual(crop_mock.call_args[0][1], crop)
            correct_mock.assert_called_once()
            expected_cropped_path = str(Path(proj_obj.workdir) / "reframed.mp4")
            self.assertEqual(correct_mock.call_args[0][0], expected_cropped_path)


class TestReframeEndpoints(ServerTestCase):
    def test_suggestion_returns_crop_and_preview_url(self):
        project = self._create_project()
        with mock.patch.object(server_mod.silence_mod, "get_video_resolution", return_value=(1920, 1080)), \
             mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0), \
             mock.patch.object(server_mod, "extract_frame_at"), \
             mock.patch.object(server_mod.subject_detection_mod, "detect_faces", return_value=[]), \
             mock.patch.object(server_mod.reframe_mod, "render_crop_preview_image", return_value="/tmp/preview.jpg"):
            response = self.client.get(f"/api/projects/{project['id']}/reframe-suggestion")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("crop", body)
        self.assertFalse(body["faceDetected"])
        self.assertFalse(body["approved"])
        self.assertTrue(body["previewUrl"].endswith("/reframe-preview"))

    def test_second_fetch_reuses_cached_suggestion_and_does_not_reset_approval(self):
        """React StrictMode 등으로 GET이 두 번 불려도 이미 승인한 상태를 되돌리면 안 된다."""
        project = self._create_project()
        with mock.patch.object(server_mod.silence_mod, "get_video_resolution", return_value=(1920, 1080)) as res_mock, \
             mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0), \
             mock.patch.object(server_mod, "extract_frame_at"), \
             mock.patch.object(server_mod.subject_detection_mod, "detect_faces", return_value=[]), \
             mock.patch.object(server_mod.reframe_mod, "render_crop_preview_image", return_value="/tmp/preview.jpg"):
            first = self.client.get(f"/api/projects/{project['id']}/reframe-suggestion").json()
            self.client.patch(f"/api/projects/{project['id']}/reframe-approval", json={"approved": True})

            second = self.client.get(f"/api/projects/{project['id']}/reframe-suggestion").json()

            self.assertTrue(second["approved"])
            self.assertEqual(second["crop"], first["crop"])
            res_mock.assert_called_once()  # 두 번째 호출에서는 재계산하지 않음

    def test_recompute_true_forces_fresh_calculation_and_resets_approval(self):
        project = self._create_project()
        with mock.patch.object(server_mod.silence_mod, "get_video_resolution", return_value=(1920, 1080)), \
             mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0), \
             mock.patch.object(server_mod, "extract_frame_at"), \
             mock.patch.object(server_mod.subject_detection_mod, "detect_faces", return_value=[]), \
             mock.patch.object(server_mod.reframe_mod, "render_crop_preview_image", return_value="/tmp/preview.jpg"):
            self.client.get(f"/api/projects/{project['id']}/reframe-suggestion")
            self.client.patch(f"/api/projects/{project['id']}/reframe-approval", json={"approved": True})

            response = self.client.get(f"/api/projects/{project['id']}/reframe-suggestion?recompute=true").json()
            self.assertFalse(response["approved"])

    def test_approval_requires_suggestion_first(self):
        project = self._create_project()
        response = self.client.patch(f"/api/projects/{project['id']}/reframe-approval", json={"approved": True})
        self.assertEqual(response.status_code, 400)

    def test_approval_toggle_after_suggestion(self):
        project = self._create_project()
        proj_obj = server_mod.store.get(project["id"])
        proj_obj.reframe_crop = CropWindow(x=0.0, y=0.0, width=600.0, height=1080.0, zoom=1.0, subject_fully_contained=True)

        response = self.client.patch(f"/api/projects/{project['id']}/reframe-approval", json={"approved": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["approved"])
        self.assertTrue(proj_obj.reframe_approved)

        response = self.client.patch(f"/api/projects/{project['id']}/reframe-approval", json={"approved": False})
        self.assertFalse(response.json()["approved"])

    def test_preview_missing_returns_404(self):
        project = self._create_project()
        response = self.client.get(f"/api/projects/{project['id']}/reframe-preview")
        self.assertEqual(response.status_code, 404)

    def test_preview_serves_existing_file(self):
        project = self._create_project()
        proj_obj = server_mod.store.get(project["id"])
        preview_dir = Path(proj_obj.workdir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / "preview.jpg"
        preview_path.write_bytes(b"fake jpeg bytes")
        proj_obj.reframe_preview_path = str(preview_path)

        response = self.client.get(f"/api/projects/{project['id']}/reframe-preview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"fake jpeg bytes")


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
    def _analyzed_project(self, words=None):
        project = self._create_project(category="FOOD")
        words = words if words is not None else [Word(0.5, 0.8, "어"), Word(1.0, 1.4, "안녕하세요")]
        with mock.patch.object(server_mod.silence_mod, "get_duration", return_value=10.0), \
             mock.patch.object(server_mod.silence_mod, "extract_audio", return_value="/tmp/a.wav"), \
             mock.patch.object(server_mod.silence_mod, "detect_silence", return_value=[Interval(2.0, 5.0)]), \
             mock.patch.object(server_mod, "transcribe_audio", return_value=words):
            self.client.post(f"/api/projects/{project['id']}/analyze")
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] != "running")
        return project

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

    def test_mix_bgm_receives_voice_intervals_and_duck_ratio_from_recommendation(self):
        project = self._analyzed_project(words=[Word(1.0, 1.5, "안녕"), Word(2.0, 2.4, "하세요")])
        fake_library = {"neutral": BgmTrack(mood="neutral", label="기본", path="/tmp/neutral.m4a")}
        with mock.patch.object(server_mod.audio_mix_mod, "ensure_bgm_library", return_value=fake_library), \
             mock.patch.object(server_mod.audio_mix_mod, "mix_bgm", return_value="/tmp/mixed.mp4") as mix_mock, \
             mock.patch.object(server_mod.audio_mix_mod, "ensure_sfx_library", return_value={"pop": "/tmp/pop.m4a"}), \
             mock.patch.object(server_mod.audio_mix_mod, "apply_sfx_at_cuts", return_value="/tmp/final.mp4"):
            start = self.client.post(f"/api/projects/{project['id']}/audio")
            self.assertEqual(start.status_code, 200)
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/audio").json()["status"] != "running")

            mix_mock.assert_called_once()
            _args, kwargs = mix_mock.call_args
            self.assertIn(Interval(1.0, 1.5), kwargs["voice_intervals"])
            self.assertIn(Interval(2.0, 2.4), kwargs["voice_intervals"])
            self.assertGreater(kwargs["duck_volume_ratio"], 0)

    def test_audio_job_uses_approved_sfx_placements_instead_of_flat_pop(self):
        project = self._analyzed_project()
        proj_obj = server_mod.store.get(project["id"])
        proj_obj.sfx_recommendations = [
            _make_sfx_recommendation(time=1.0, asset_id="soft_reveal_1", approved=True),
            _make_sfx_recommendation(time=4.0, asset_id="soft_whoosh_1", approved=False),  # 미승인 - 제외되어야 함
        ]

        fake_library = {"neutral": BgmTrack(mood="neutral", label="기본", path="/tmp/neutral.m4a")}
        with mock.patch.object(server_mod.audio_mix_mod, "ensure_bgm_library", return_value=fake_library), \
             mock.patch.object(server_mod.audio_mix_mod, "mix_bgm", return_value="/tmp/mixed.mp4"), \
             mock.patch.object(server_mod.audio_mix_mod, "apply_sfx_at_cuts") as flat_sfx_mock, \
             mock.patch.object(server_mod.audio_mix_mod, "apply_multiple_sfx", return_value="/tmp/final.mp4") as multi_mock:
            start = self.client.post(f"/api/projects/{project['id']}/audio")
            self.assertEqual(start.status_code, 200)
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/audio").json()["status"] != "running")

            multi_mock.assert_called_once()
            placements = multi_mock.call_args[0][2]
            self.assertEqual(len(placements), 1)  # 승인된 것 하나만
            self.assertEqual(placements[0][0], 1.0)
            self.assertIn("soft_reveal_1", placements[0][1])
            flat_sfx_mock.assert_not_called()


def _make_sfx_recommendation(time, asset_id, approved):
    from capcut_auto.sfx_recommend import SfxCandidate, SfxRecommendation

    asset = SfxAsset(id=asset_id, purpose=SfxPurpose.RESULT_REVEAL, label=asset_id, path=f"/tmp/{asset_id}.m4a")
    rec = SfxRecommendation(
        time=time,
        purpose=SfxPurpose.RESULT_REVEAL,
        candidates=[SfxCandidate(asset=asset, reason="테스트")],
    )
    rec.approved = approved
    rec.selected_asset_id = asset_id if approved else None
    return rec


class TestBgmRecommendationEndpoint(ServerTestCase):
    def test_bgm_recommendation_has_no_fabricated_commercial_info(self):
        project = self._create_project(category="FOOD")
        response = self.client.get(f"/api/projects/{project['id']}/bgm-recommendation")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for forbidden in ("title", "artist", "copyright", "trending"):
            self.assertNotIn(forbidden, "".join(body.keys()).lower())
        self.assertFalse(body["hasVocals"])
        self.assertTrue(body["duckDuringVoice"])
        self.assertGreater(len(body["searchKeywords"]), 0)

    def test_preserve_natural_audio_category_gets_lower_energy(self):
        project = self._create_project(category="FOOD")  # food.json: preserveNaturalAudio=true
        response = self.client.get(f"/api/projects/{project['id']}/bgm-recommendation").json()
        self.assertEqual(response["energy"], "LOW")

    def test_no_category_falls_back_to_neutral(self):
        project = self._create_project(category=None)
        response = self.client.get(f"/api/projects/{project['id']}/bgm-recommendation").json()
        self.assertEqual(response["mood"], "neutral")


class TestSfxSuggestionsEndpoint(ServerTestCase):
    def _analyzed_project(self):
        project = self._create_project(category="LIVING")
        words = [Word(0.5, 0.8, "어"), Word(1.0, 1.4, "안녕하세요")]
        with mock.patch.object(server_mod.silence_mod, "get_duration", return_value=20.0), \
             mock.patch.object(server_mod.silence_mod, "extract_audio", return_value="/tmp/a.wav"), \
             mock.patch.object(server_mod.silence_mod, "detect_silence", return_value=[]), \
             mock.patch.object(server_mod, "transcribe_audio", return_value=words):
            self.client.post(f"/api/projects/{project['id']}/analyze")
            _wait_until(lambda: self.client.get(f"/api/projects/{project['id']}/analyze").json()["status"] != "running")
        return project

    def _fake_sfx_library(self):
        return {
            SfxPurpose.RESULT_REVEAL: [SfxAsset("soft_reveal_1", SfxPurpose.RESULT_REVEAL, "결과 공개음", "/tmp/r1.m4a")],
            SfxPurpose.BUILD_UP: [SfxAsset("build_up_1", SfxPurpose.BUILD_UP, "궁금증 유발음", "/tmp/b1.m4a")],
        }

    def test_requires_analysis_before_suggesting(self):
        project = self._create_project()
        response = self.client.get(f"/api/projects/{project['id']}/sfx-suggestions")
        self.assertEqual(response.status_code, 400)

    def test_returns_recommendations_after_analysis(self):
        project = self._analyzed_project()
        with mock.patch.object(server_mod.sfx_recommend_mod, "ensure_sfx_asset_library", return_value=self._fake_sfx_library()):
            response = self.client.get(f"/api/projects/{project['id']}/sfx-suggestions")
        self.assertEqual(response.status_code, 200)
        recs = response.json()["recommendations"]
        self.assertGreater(len(recs), 0)
        self.assertTrue(all("candidates" in r and len(r["candidates"]) > 0 for r in recs))
        self.assertTrue(all(r["candidates"][0]["previewUrl"].startswith("/api/sfx-preview/") for r in recs))

    def test_decision_patch_updates_approval_and_selection(self):
        project = self._analyzed_project()
        with mock.patch.object(server_mod.sfx_recommend_mod, "ensure_sfx_asset_library", return_value=self._fake_sfx_library()):
            recs = self.client.get(f"/api/projects/{project['id']}/sfx-suggestions").json()["recommendations"]
        self.assertGreater(len(recs), 0)
        target = recs[0]
        asset_id = target["candidates"][0]["assetId"]

        response = self.client.patch(
            f"/api/projects/{project['id']}/sfx-suggestions",
            json={"time": target["time"], "approved": True, "selectedAssetId": asset_id},
        )
        self.assertEqual(response.status_code, 200)
        updated = next(r for r in response.json()["recommendations"] if r["time"] == target["time"])
        self.assertTrue(updated["approved"])
        self.assertEqual(updated["selectedAssetId"], asset_id)

    def test_decision_patch_unknown_time_returns_404(self):
        project = self._analyzed_project()
        response = self.client.patch(
            f"/api/projects/{project['id']}/sfx-suggestions",
            json={"time": 9999.0, "approved": True, "selectedAssetId": "x"},
        )
        self.assertEqual(response.status_code, 404)


class TestSfxPreviewEndpoint(ServerTestCase):
    def test_missing_asset_returns_404(self):
        response = self.client.get("/api/sfx-preview/does_not_exist")
        self.assertEqual(response.status_code, 404)

    def test_existing_asset_is_served(self):
        preview_dir = Path(server_mod._shared_sfx_v2_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        (preview_dir / "fake_asset.m4a").write_bytes(b"fake audio bytes")
        try:
            response = self.client.get("/api/sfx-preview/fake_asset")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake audio bytes")
        finally:
            (preview_dir / "fake_asset.m4a").unlink(missing_ok=True)


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
