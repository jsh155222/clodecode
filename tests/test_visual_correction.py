import unittest

from capcut_auto.visual_correction import BrightnessStats, compute_correction_params


class TestComputeCorrectionParams(unittest.TestCase):
    def test_dark_video_gets_brightened(self):
        stats = BrightnessStats(mean_luma=60.0, stddev_luma=50.0, sample_count=10)
        params = compute_correction_params(stats)
        self.assertGreater(params.brightness, 0)

    def test_bright_video_gets_darkened(self):
        stats = BrightnessStats(mean_luma=200.0, stddev_luma=50.0, sample_count=10)
        params = compute_correction_params(stats)
        self.assertLess(params.brightness, 0)

    def test_ideal_brightness_needs_no_change(self):
        stats = BrightnessStats(mean_luma=128.0, stddev_luma=50.0, sample_count=10)
        params = compute_correction_params(stats)
        self.assertAlmostEqual(params.brightness, 0.0, places=3)
        self.assertAlmostEqual(params.contrast, 1.0, places=3)

    def test_brightness_adjustment_is_clamped(self):
        stats = BrightnessStats(mean_luma=0.0, stddev_luma=50.0, sample_count=10)
        params = compute_correction_params(stats, max_brightness_adjust=0.15)
        self.assertLessEqual(params.brightness, 0.15)

    def test_low_stddev_flat_video_gets_contrast_boost(self):
        stats = BrightnessStats(mean_luma=128.0, stddev_luma=10.0, sample_count=10)
        params = compute_correction_params(stats)
        self.assertGreater(params.contrast, 1.0)

    def test_contrast_boost_is_clamped(self):
        stats = BrightnessStats(mean_luma=128.0, stddev_luma=0.1, sample_count=10)
        params = compute_correction_params(stats)
        self.assertLessEqual(params.contrast, 1.3)

    def test_zero_stddev_defaults_to_no_contrast_change(self):
        stats = BrightnessStats(mean_luma=128.0, stddev_luma=0.0, sample_count=1)
        params = compute_correction_params(stats)
        self.assertEqual(params.contrast, 1.0)


if __name__ == "__main__":
    unittest.main()
