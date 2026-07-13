import unittest

from capcut_auto.cutlist import CutlistConfig, build_cutlist
from capcut_auto.timeline import Interval


class TestBuildCutlist(unittest.TestCase):
    def test_combines_all_sources(self):
        config = CutlistConfig(
            silence_edge_padding=0.1,
            filler_edge_expand=0.05,
            min_keep_duration=0.1,
            min_cut_duration=0.1,
        )
        result = build_cutlist(
            total_duration=20.0,
            silence_intervals=[Interval(5.0, 6.0)],
            filler_intervals=[Interval(10.0, 10.3)],
            repetition_intervals=[Interval(15.0, 15.2)],
            config=config,
        )
        self.assertAlmostEqual(result.total_duration, 20.0)
        # 무음(shrink 0.1 양쪽): 5.1-5.9, 필러(expand 0.05): 9.95-10.35, 반복: 14.95-15.25
        self.assertEqual(len(result.cut_intervals), 3)
        self.assertLess(result.kept_duration, 20.0)
        self.assertAlmostEqual(result.kept_duration + result.removed_duration, 20.0)

    def test_short_silence_fully_absorbed_by_padding(self):
        # 무음이 edge_padding*2보다 짧으면 shrink 후 사라짐 -> 컷 없음
        config = CutlistConfig(silence_edge_padding=0.5)
        result = build_cutlist(
            total_duration=10.0, silence_intervals=[Interval(4.0, 4.3)], config=config
        )
        self.assertEqual(result.cut_intervals, [])
        self.assertEqual(result.keep_intervals, [Interval(0, 10.0)])

    def test_default_config_used_when_none(self):
        result = build_cutlist(total_duration=5.0, silence_intervals=[Interval(1.0, 3.0)])
        self.assertGreater(len(result.cut_intervals), 0)
        self.assertLess(result.kept_duration, 5.0)


if __name__ == "__main__":
    unittest.main()
