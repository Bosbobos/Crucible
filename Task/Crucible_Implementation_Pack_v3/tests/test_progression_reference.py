import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from progression_reference import Part, candidate_xp, repeat_amount, total_xp, level_for_xp, chronicles, compensation, elapsed_gate

class ProgressionReferenceTests(unittest.TestCase):
    def test_all_thresholds_and_costs(self):
        self.assertEqual(total_xp(60), 33276)
        for level in range(1, 60):
            self.assertEqual(total_xp(level + 1) - total_xp(level), 100 + 16 * (level - 1))
    def test_known_thresholds(self):
        for level, xp in {1:0,5:496,10:1476,20:4636,30:9396,40:15756,50:23716,55:28296,60:33276}.items():
            self.assertEqual(total_xp(level), xp)
    def test_level_boundaries(self):
        for level in range(2,61):
            self.assertEqual(level_for_xp(total_xp(level)), level)
            self.assertEqual(level_for_xp(total_xp(level)-1), level-1)
    def test_cap(self): self.assertEqual(level_for_xp(10**6),60)
    def test_chronicles(self):
        self.assertEqual(chronicles(35275),0)
        self.assertEqual(chronicles(35276),1)
        self.assertEqual(chronicles(37276),2)
    def test_full_prices(self):
        for d,n in {"A":40,"B":80,"C":120}.items(): self.assertEqual(candidate_xp(d,[Part("a",1,"independent",1)]),n)
    def test_partial_example_68(self): self.assertEqual(candidate_xp("B",[Part("a",1,"independent",1),Part("b",1,"assisted",1)]),68)
    def test_quality_90(self): self.assertEqual(candidate_xp("B",[Part("a",1,"independent",.9)]),72)
    def test_review_note(self): self.assertEqual(candidate_xp("B",[Part("a",1,"reviewed",0,True)]),28)
    def test_review_no_note(self): self.assertEqual(candidate_xp("B",[Part("a",1,"reviewed",1,False)]),0)
    def test_skipped(self): self.assertEqual(candidate_xp("C",[Part("a",1,"skipped",1)]),0)
    def test_round_once(self): self.assertEqual(candidate_xp("A",[Part("a",1,"independent",1),Part("b",2,"assisted",.5)]),22)
    def test_exact_decimal(self): self.assertEqual(candidate_xp("B",[Part("a",1,"reviewed",0,True)]),28)
    def test_primary_sequence(self):
        self.assertEqual([compensation([], [28]),compensation([28],[28,56]),compensation([28,56],[28,56,80])],[28,28,24])
    def test_duplicate_candidate(self): self.assertEqual(compensation([80],[80,80]),0)
    def test_correction(self): self.assertEqual(compensation([80],[56]),-24)
    def test_other_attempt_preserves_max(self): self.assertEqual(compensation([80,80],[56,80]),0)
    def test_revoked(self): self.assertEqual(compensation([80],[]),-80)
    def test_repeat_full(self):
        for d,n in {"A":12,"B":24,"C":36}.items(): self.assertEqual(repeat_amount(d,[Part("a",1,"independent",1)]),n)
    def test_repeat_assisted(self): self.assertEqual(repeat_amount("B",[Part("a",1,"assisted",1)]),16)
    def test_repeat_no_review_contribution(self): self.assertEqual(repeat_amount("B",[Part("a",1,"reviewed",1,True)]),0)
    def test_timing(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc);due=start+timedelta(days=7)
        self.assertTrue(elapsed_gate(due,due,start))
        self.assertFalse(elapsed_gate(due-timedelta(seconds=1),start,start))
        self.assertFalse(elapsed_gate(due,due+timedelta(hours=1),start))
    def test_dst_elapsed_hours(self):
        zone=ZoneInfo("Europe/Amsterdam")
        start=datetime(2026,3,23,12,tzinfo=zone);end=datetime(2026,3,30,12,tzinfo=zone)
        self.assertFalse(elapsed_gate(end,start,start))  # 167 elapsed hours, not 168.
        self.assertTrue(elapsed_gate(end+timedelta(hours=1),start,start))
    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):elapsed_gate(datetime(2026,1,1),datetime(2026,1,1),datetime(2026,1,1))
    def test_invalid_parts(self):
        bad=[[Part("a",0,"independent",1)],[Part("a",-1,"independent",1)],[Part("a",1,"wrong",1)],[Part("a",1,"independent",1.1)],[Part("a",1,"independent",float("nan"))],[Part("a",1,"independent",float("inf"))],[Part("a",True,"independent",1)],[Part("a",1,"independent",1),Part("a",1,"independent",1)],[]]
        for parts in bad:
            with self.subTest(parts=parts), self.assertRaises(ValueError):candidate_xp("B",parts)
    def test_invalid_level_inputs(self):
        for v in [-1,61,True,1.5]:
            with self.assertRaises(ValueError):total_xp(v)
        for v in [-1,True,1.5]:
            with self.assertRaises(ValueError):level_for_xp(v)
    def test_unknown_difficulty(self):
        with self.assertRaises(ValueError):candidate_xp("B+",[Part("a",1,"independent",1)])
    def test_all_seal_bonus(self): self.assertEqual(25*40+25*80+25*80+5*160+3*200,6400)

if __name__ == "__main__": unittest.main()
