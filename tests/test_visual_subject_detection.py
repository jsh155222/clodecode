"""피사체 감지(capcut_auto/visual/subject_detection.py) 테스트.

실제 OpenCV Haar Cascade(오프라인)로 검증한다. 이 샌드박스에는 실사 얼굴 사진이 없어서
"진짜 얼굴을 정확히 찾아내는지"는 검증하지 못했고, 대신 다음을 실제로 검증한다:
- 얼굴이 없는 이미지에서 거짓 양성(false positive)이 나지 않는지
- 반환 타입/신뢰도 범위가 항상 올바른지
- face 외 카테고리는 좌표를 지어내지 않고 정직하게 감지 안 됨으로 보고하는지
"""

import contextlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from capcut_auto.visual.subject_detection import (
    SubjectType,
    UNSUPPORTED_WITHOUT_REAL_MODEL,
    detect_faces,
    detect_subjects,
    find_first_appearance_times,
    is_confident,
    DetectedSubject,
    BoundingBox,
)


def _write_noise_image(path: str, size=(320, 240)) -> None:
    rng = np.random.default_rng(42)
    arr = (rng.random((size[1], size[0], 3)) * 255).astype("uint8")
    Image.fromarray(arr).save(path)


def _write_flat_image(path: str, size=(320, 240), color=(128, 128, 128)) -> None:
    Image.new("RGB", size, color).save(path)


class TestDetectFaces(unittest.TestCase):
    def test_no_false_positive_on_random_noise(self):
        with _tmp_image(_write_noise_image) as path:
            result = detect_faces(path)
            self.assertEqual(result, [])

    def test_no_false_positive_on_flat_color_image(self):
        with _tmp_image(_write_flat_image) as path:
            result = detect_faces(path)
            self.assertEqual(result, [])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            detect_faces("/nonexistent/path/to/image.jpg")

    def test_return_type_and_confidence_range_are_valid(self):
        # 검출이 없더라도(빈 리스트) 함수가 항상 List[DetectedSubject] 계약을 지키는지 확인
        with _tmp_image(_write_noise_image) as path:
            result = detect_faces(path)
            self.assertIsInstance(result, list)
            for subject in result:
                self.assertIsInstance(subject, DetectedSubject)
                self.assertGreaterEqual(subject.confidence, 0.0)
                self.assertLessEqual(subject.confidence, 1.0)


class TestDetectSubjectsHonestyAboutUnsupportedCategories(unittest.TestCase):
    def test_detect_subjects_only_ever_returns_face_type(self):
        with _tmp_image(_write_noise_image) as path:
            result = detect_subjects(path)
            for subject in result:
                self.assertEqual(subject.subject_type, SubjectType.FACE)

    def test_unsupported_categories_are_never_fabricated(self):
        """hand/product/tool/... 카테고리는 실제 검출기가 없으므로 좌표를 절대 만들어내지 않는다."""
        with _tmp_image(_write_noise_image) as path:
            result = detect_subjects(path)
            detected_types = {s.subject_type for s in result}
            self.assertTrue(detected_types.isdisjoint(UNSUPPORTED_WITHOUT_REAL_MODEL))


class TestIsConfident(unittest.TestCase):
    def test_low_confidence_subject_is_not_confident(self):
        subject = DetectedSubject(SubjectType.FACE, BoundingBox(0, 0, 10, 10), confidence=0.2)
        self.assertFalse(is_confident(subject, threshold=0.5))

    def test_no_bbox_is_never_confident_regardless_of_score(self):
        subject = DetectedSubject(SubjectType.HAND, None, confidence=0.99)
        self.assertFalse(is_confident(subject))

    def test_high_confidence_with_bbox_is_confident(self):
        subject = DetectedSubject(SubjectType.FACE, BoundingBox(0, 0, 10, 10), confidence=0.9)
        self.assertTrue(is_confident(subject))


class TestFindFirstAppearanceTimes(unittest.TestCase):
    def test_finds_earliest_confident_appearance_per_type(self):
        face_a = DetectedSubject(SubjectType.FACE, BoundingBox(0, 0, 10, 10), 0.9)
        face_b = DetectedSubject(SubjectType.FACE, BoundingBox(5, 5, 10, 10), 0.9)
        detections = {
            2.0: [face_a],
            0.5: [],
            1.0: [face_b],
        }
        result = find_first_appearance_times(detections)
        self.assertEqual(result, {SubjectType.FACE: 1.0})

    def test_ignores_low_confidence_detections(self):
        low_conf = DetectedSubject(SubjectType.FACE, BoundingBox(0, 0, 10, 10), 0.1)
        detections = {0.5: [low_conf]}
        result = find_first_appearance_times(detections, confidence_threshold=0.5)
        self.assertEqual(result, {})


@contextlib.contextmanager
def _tmp_image(writer):
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "img.jpg")
        writer(path)
        yield path


if __name__ == "__main__":
    unittest.main()
