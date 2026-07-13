import unittest

from capcut_auto.timeline import (
    Interval,
    build_keep_intervals,
    invert_intervals,
    map_time_to_new_timeline,
    merge_intervals,
    pad_intervals,
    shrink_intervals,
    total_kept_duration,
)


class TestInterval(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(Interval(1.0, 3.5).duration, 2.5)

    def test_rejects_negative_duration(self):
        with self.assertRaises(ValueError):
            Interval(5.0, 1.0)


class TestMergeIntervals(unittest.TestCase):
    def test_merges_overlapping(self):
        result = merge_intervals([Interval(0, 5), Interval(3, 8), Interval(10, 12)])
        self.assertEqual(result, [Interval(0, 8), Interval(10, 12)])

    def test_merges_within_gap(self):
        result = merge_intervals([Interval(0, 5), Interval(5.2, 8)], gap=0.3)
        self.assertEqual(result, [Interval(0, 8)])

    def test_does_not_merge_beyond_gap(self):
        result = merge_intervals([Interval(0, 5), Interval(5.5, 8)], gap=0.3)
        self.assertEqual(result, [Interval(0, 5), Interval(5.5, 8)])

    def test_empty_input(self):
        self.assertEqual(merge_intervals([]), [])

    def test_drops_zero_length(self):
        self.assertEqual(merge_intervals([Interval(1, 1), Interval(2, 3)]), [Interval(2, 3)])


class TestPadShrink(unittest.TestCase):
    def test_pad_expands_and_clamps(self):
        result = pad_intervals([Interval(1, 2)], pad=0.5, total_duration=10)
        self.assertEqual(result, [Interval(0.5, 2.5)])

    def test_pad_clamps_to_bounds(self):
        result = pad_intervals([Interval(0, 1), Interval(9, 10)], pad=0.5, total_duration=10)
        self.assertEqual(result, [Interval(0, 1.5), Interval(8.5, 10)])

    def test_shrink_reduces_and_drops_tiny(self):
        result = shrink_intervals([Interval(0, 1), Interval(2, 2.1)], shrink=0.1)
        self.assertEqual(result, [Interval(0.1, 0.9)])


class TestInvertIntervals(unittest.TestCase):
    def test_basic_inversion(self):
        cuts = [Interval(1, 2), Interval(5, 6)]
        keep = invert_intervals(cuts, total_duration=10)
        self.assertEqual(keep, [Interval(0, 1), Interval(2, 5), Interval(6, 10)])

    def test_cut_covers_start_and_end(self):
        cuts = [Interval(0, 1), Interval(9, 10)]
        keep = invert_intervals(cuts, total_duration=10)
        self.assertEqual(keep, [Interval(1, 9)])

    def test_no_cuts(self):
        self.assertEqual(invert_intervals([], total_duration=5), [Interval(0, 5)])


class TestBuildKeepIntervals(unittest.TestCase):
    def test_absorbs_tiny_keep_slivers(self):
        # 두 컷 사이 0.05초 조각은 min_keep_duration=0.2보다 짧으므로 흡수되어야 함
        cuts = [Interval(1, 2), Interval(2.05, 3)]
        keep, final_cuts = build_keep_intervals(cuts, total_duration=5, min_keep_duration=0.2)
        self.assertEqual(keep, [Interval(0, 1), Interval(3, 5)])
        self.assertEqual(final_cuts, [Interval(1, 3)])

    def test_keeps_sufficiently_long_slivers(self):
        cuts = [Interval(1, 2), Interval(2.5, 3)]
        keep, _ = build_keep_intervals(cuts, total_duration=5, min_keep_duration=0.2)
        self.assertEqual(keep, [Interval(0, 1), Interval(2, 2.5), Interval(3, 5)])


class TestMapTimeToNewTimeline(unittest.TestCase):
    def test_maps_within_keep_interval(self):
        keep = [Interval(0, 2), Interval(5, 8)]
        self.assertAlmostEqual(map_time_to_new_timeline(1.0, keep), 1.0)
        self.assertAlmostEqual(map_time_to_new_timeline(6.0, keep), 3.0)

    def test_returns_none_inside_cut(self):
        keep = [Interval(0, 2), Interval(5, 8)]
        self.assertIsNone(map_time_to_new_timeline(3.0, keep))

    def test_total_kept_duration(self):
        self.assertEqual(total_kept_duration([Interval(0, 2), Interval(5, 8)]), 5.0)


if __name__ == "__main__":
    unittest.main()
