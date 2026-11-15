"""핵심 알고리즘 단위 테스트 — 실행: python -m unittest discover -s backend/tests"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.flex_window import DriverProfile, FlexWindow, evaluate_gig, match  # noqa: E402
from app.engine.geo import HeuristicEstimator, Point  # noqa: E402
from app.engine.intent import parse  # noqa: E402
from app.engine.parking import ParkingQuery, Vehicle, base_fee, evaluate_lots  # noqa: E402
from app.engine.radar import radar  # noqa: E402
from app.store import load  # noqa: E402

NOW = datetime(2026, 11, 15, 17, 20)
LOT_B = Point(37.49975, 127.06350)
DRIVER = DriverProfile(qualifications=["driver_license"], insurance={"gig_delivery": "2027-03-31T23:59:00"})
EST = HeuristicEstimator()


def fw(**kw):
    base = dict(now=NOW, position=LOT_B, return_point=LOT_B, return_by=datetime(2026, 11, 15, 17, 55))
    base.update(kw)
    return FlexWindow(**base)


def gig(gid):
    return next(g for g in load("gigs.json", "gigs") if g["id"] == gid)


class ParkingFeeTest(unittest.TestCase):
    def test_fee_table(self):
        fee = {"free_min": 10, "base_min": 30, "base_fee": 3000, "unit_min": 10, "unit_fee": 1000, "daily_max": 30000}
        self.assertEqual(base_fee(fee, 10), 0)          # 무료 회차
        self.assertEqual(base_fee(fee, 30), 3000)
        self.assertEqual(base_fee(fee, 31), 4000)       # 초과분은 올림 과금
        self.assertEqual(base_fee(fee, 50), 5000)
        self.assertEqual(base_fee(fee, 60 * 24), 30000)  # 일 최대

    def test_extra_free_minutes(self):
        fee = {"free_min": 0, "base_min": 30, "base_fee": 3000, "unit_min": 10, "unit_fee": 1000}
        self.assertEqual(base_fee(fee, 50, extra_free_min=60), 0)


class ParkingFilterTest(unittest.TestCase):
    def setUp(self):
        self.q = ParkingQuery(origin=Point(37.4988, 127.0623), destination=Point(37.49985, 127.0633), now=NOW,
                              stay_until=datetime(2026, 11, 15, 18, 10), vehicle=Vehicle(height_m=1.98),
                              pickup_only=True)
        self.r = evaluate_lots(load("parking_lots.json", "lots"), self.q, EST)

    def test_excludes_closing_and_height_and_illegal(self):
        ex = {x["id"]: x["reasons"] for x in self.r["excluded"]}
        self.assertIn("P-C", ex)  # 18:00 마감
        self.assertIn("P-D", ex)  # 높이 1.85m
        self.assertTrue(any("높이" in s for s in ex["P-D"]))

    def test_unknown_data_marked_not_hidden(self):
        a = next(x for x in self.r["recommended"] if x["id"] == "P-A")
        self.assertEqual(a["realtime_spaces"]["status"], "미확인")
        self.assertIsNone(a["realtime_spaces"]["value"])
        self.assertTrue(a["source"])

    def test_unverified_discount_not_applied(self):
        q = ParkingQuery(**{**self.q.__dict__, "has_academy_receipt": True})
        b = next(x for x in evaluate_lots(load("parking_lots.json", "lots"), q, EST)["recommended"] if x["id"] == "P-B")
        self.assertEqual(b["fee_estimate"], b["fee_without_discount"])
        self.assertEqual(b["discounts_need_check"], ["같은 건물 학원 영수증 제시 시 1시간 무료"])
        self.assertEqual(b["fee_if_pending_discount_confirmed"], 0)


class FlexWindowTest(unittest.TestCase):
    def test_proposal_example_breakdown(self):
        """기획서 STEP 3: 이동 5 + 업무 10 + 복귀 + 안전여유 8"""
        ev = evaluate_gig(gig("G-101"), fw(), DRIVER, EST)
        self.assertTrue(ev.eligible, ev.reasons)
        self.assertEqual(ev.breakdown["drive_to_site"], 5)
        self.assertEqual(ev.breakdown["task"], 10)
        self.assertEqual(ev.breakdown["safety_buffer"], 8)
        self.assertEqual(ev.finish_at, "17:48")
        self.assertEqual(ev.net_profit, 12000 - ev.costs["vehicle"] - ev.costs["parking"])

    def test_deadline_exceeded_excluded(self):
        ev = evaluate_gig(gig("G-103"), fw(), DRIVER, EST)
        self.assertFalse(ev.eligible)
        self.assertIn("복귀 시각", ev.reasons[0])

    def test_hard_filters(self):
        self.assertIn("필수 보험 미가입: 유상운송 보험", evaluate_gig(gig("G-104"), fw(), DRIVER, EST).reasons)
        self.assertIn("제휴·검증되지 않은 업체", evaluate_gig(gig("G-105"), fw(), DRIVER, EST).reasons)
        self.assertIn("모집이 마감된 일감", evaluate_gig(gig("G-106"), fw(), DRIVER, EST).reasons)

    def test_no_insurance_blocks_insured_gig(self):
        ev = evaluate_gig(gig("G-101"), fw(), DriverProfile(), EST)
        self.assertFalse(ev.eligible)

    def test_insurance_expiring_before_return_blocks(self):
        d = DriverProfile(insurance={"gig_delivery": "2026-11-15T17:30:00"})
        self.assertFalse(evaluate_gig(gig("G-101"), fw(), d, EST).eligible)

    def test_max_detour(self):
        ev = evaluate_gig(gig("G-101"), fw(max_drive_min=8), DRIVER, EST)
        self.assertFalse(ev.eligible)
        self.assertIn("상한", ev.reasons[0])

    def test_user_buffer_raises_total(self):
        a = evaluate_gig(gig("G-101"), fw(min_buffer_min=5), DRIVER, EST)
        b = evaluate_gig(gig("G-101"), fw(min_buffer_min=15), DRIVER, EST)
        self.assertEqual(b.breakdown["safety_buffer"] - a.breakdown["safety_buffer"], 10)
        self.assertFalse(b.eligible)  # 여유를 늘리면 마감 초과

    def test_rest_mode_recommends_nothing(self):
        r = match(load("gigs.json", "gigs"), fw(wants_work=False), DRIVER, EST)
        self.assertEqual(r["mode"], "rest")
        self.assertEqual(r["recommended"], [])

    def test_no_recommendation_after_return_time(self):
        r = match(load("gigs.json", "gigs"), fw(now=datetime(2026, 11, 15, 17, 55)), DRIVER, EST)
        self.assertEqual(r["mode"], "over")
        self.assertEqual(r["recommended"], [])

    def test_reasons_are_korean(self):
        """제외 사유에 내부 코드(영문)가 그대로 노출되지 않아야 한다."""
        import re
        r = match(load("gigs.json", "gigs"), fw(), DriverProfile(qualifications=[]), EST)
        for g in r["excluded"]:
            for reason in g["reasons"]:
                self.assertIsNone(re.search(r"[a-z_]{3,}", reason), reason)

    def test_match_sorted_and_taken_excluded(self):
        gigs = load("gigs.json", "gigs")
        r = match(gigs, fw(), DRIVER, EST)
        scores = [g["score"] for g in r["recommended"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual({g["gig_id"] for g in r["recommended"]}, {"G-101", "G-102"})
        r2 = match(gigs, fw(), DRIVER, EST, taken={"G-101"})
        self.assertNotIn("G-101", [g["gig_id"] for g in r2["recommended"]])

    def test_traffic_multiplier_can_push_past_deadline(self):
        slow = HeuristicEstimator(traffic_multiplier=2.0)
        self.assertFalse(evaluate_gig(gig("G-101"), fw(), DRIVER, slow).eligible)


class RadarTest(unittest.TestCase):
    def test_only_selected_keywords_and_ads_separated(self):
        places = load("places.json", "places")
        r = radar(places, ["약국", "아이 동반 식당"], LOT_B, NOW, datetime(2026, 11, 15, 17, 55), EST)
        self.assertTrue(all(set(p["keywords"]) <= {"약국", "아이 동반 식당"} for p in r["organic"] + r["sponsored"]))
        self.assertEqual([p["id"] for p in r["sponsored"]], ["R-3"])
        self.assertNotIn("R-5", [p["id"] for p in r["organic"]])  # 도보 10분 초과


class IntentTest(unittest.TestCase):
    def test_scenario_utterance(self):
        r = parse("주차 후 17:55까지 이곳에 돌아와야 해요. 시간이 남으면 가까운 일도 볼래요. 5분 이상 여유", NOW)
        self.assertEqual(r.return_by, "17:55")
        self.assertTrue(r.return_to_here)
        self.assertTrue(r.wants_work)
        self.assertEqual(r.min_buffer_min, 5)
        self.assertTrue(r.needs_confirmation)

    def test_korean_clock_afternoon(self):
        self.assertEqual(parse("5시 55분까지 여기 돌아와야 해", NOW).return_by, "17:55")
        self.assertEqual(parse("오후 6시까지", datetime(2026, 11, 15, 9, 0)).return_by, "18:00")

    def test_spaced_keywords(self):
        self.assertEqual(parse("아이동반식당이랑 주차 편한 상점 알려줘", NOW).keywords, ["아이 동반 식당", "주차 편한 상점"])

    def test_rest_only(self):
        r = parse("오늘은 쉬고싶어요", NOW)
        self.assertFalse(r.wants_work)


if __name__ == "__main__":
    unittest.main()
