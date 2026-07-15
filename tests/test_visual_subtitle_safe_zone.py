"""자막 안전 영역(capcut_auto/visual/subtitle_safe_zone.py) 테스트."""

import unittest

from capcut_auto.visual.reframe import CropWindow
from capcut_auto.visual.subject_detection import BoundingBox, DetectedSubject, SubjectType
from capcut_auto.visual.subtitle_safe_zone import bbox_relative_to_crop, compute_subtitle_safe_zone


def _crop(x=0, y=0, w=600, h=1080):
    return CropWindow(x=x, y=y, width=w, height=h, zoom=1.0, subject_fully_contained=True)


class TestBboxRelativeToCrop(unittest.TestCase):
    def test_bbox_inside_crop_converts_correctly(self):
        crop = _crop(x=100, y=100, w=600, h=1080)
        bbox = BoundingBox(150, 200, 50, 50)
        rel = bbox_relative_to_crop(bbox, crop)
        self.assertEqual(rel, BoundingBox(50, 100, 50, 50))

    def test_bbox_entirely_outside_crop_returns_none(self):
        crop = _crop(x=0, y=0, w=600, h=1080)
        bbox = BoundingBox(2000, 2000, 50, 50)
        self.assertIsNone(bbox_relative_to_crop(bbox, crop))


class TestComputeSubtitleSafeZone(unittest.TestCase):
    def test_defaults_to_bottom_band_when_no_subjects(self):
        crop = _crop()
        zone = compute_subtitle_safe_zone(crop, [])
        self.assertEqual(zone.band, "bottom")
        self.assertFalse(zone.overlaps_subject)

    def test_moves_to_top_band_when_face_overlaps_bottom(self):
        crop = _crop()
        # 얼굴이 화면 하단에 위치 (자막 밴드와 겹침)
        face = DetectedSubject(SubjectType.FACE, BoundingBox(200, 950, 100, 100), 0.9)
        zone = compute_subtitle_safe_zone(crop, [face])
        self.assertEqual(zone.band, "top")
        self.assertFalse(zone.overlaps_subject)

    def test_low_confidence_face_is_ignored_for_safe_zone(self):
        crop = _crop()
        low_conf_face = DetectedSubject(SubjectType.FACE, BoundingBox(200, 950, 100, 100), 0.1)
        zone = compute_subtitle_safe_zone(crop, [low_conf_face])
        self.assertEqual(zone.band, "bottom")

    def test_honestly_flags_overlap_when_both_bands_occupied(self):
        crop = _crop()
        face_bottom = DetectedSubject(SubjectType.FACE, BoundingBox(0, 850, 600, 230), 0.9)
        face_top = DetectedSubject(SubjectType.FACE, BoundingBox(0, 0, 600, 230), 0.9)
        zone = compute_subtitle_safe_zone(crop, [face_bottom, face_top])
        self.assertTrue(zone.overlaps_subject)

    def test_safe_zone_stays_within_crop_bounds(self):
        crop = _crop()
        zone = compute_subtitle_safe_zone(crop, [])
        self.assertGreaterEqual(zone.x, 0)
        self.assertGreaterEqual(zone.y, 0)
        self.assertLessEqual(zone.x + zone.width, crop.width)
        self.assertLessEqual(zone.y + zone.height, crop.height)


if __name__ == "__main__":
    unittest.main()
