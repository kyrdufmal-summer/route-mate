"""실시간 상황 판단(먼저 말 걸기) 시나리오 테스트."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as m  # noqa: E402
from app.engine import situation as sit  # noqa: E402
from app.engine.geo import Point  # noqa: E402
from app.store import Store  # noqa: E402

DRIVER = {"qualifications": ["driver_license"], "insurance": {"gig_delivery": "2027-03-31T23:59:00"}}
LOT_B = {"lat": 37.49975, "lng": 127.06350}
T = lambda hm: datetime.fromisoformat(f"2026-11-15T{hm}:00")  # noqa: E731


def session(**kw):
    body = dict(position=LOT_B, return_by="2026-11-15T17:55:00", now=T("17:20"), driver=DRIVER)
    body.update(kw)
    return m.create_session(m.SessionIn(**body))["session_id"]


def spoken_between(sid, start, end):
    out, t = [], T(start)
    while t <= T(end):
        out += [(t.strftime("%H:%M"), iv) for iv in m.situation(sid, now=t)["interventions"]]
        t += timedelta(minutes=1)
    return out


class GeometryTest(unittest.TestCase):
    def test_segment_distance(self):
        a, b = Point(37.5, 127.0), Point(37.51, 127.0)
        self.assertLess(sit.dist_to_segment_m(Point(37.505, 127.0), a, b), 1)
        self.assertGreater(sit.dist_to_segment_m(Point(37.505, 127.01), a, b), 800)

    def test_rain_counts_once(self):
        rain = {"id": "r", "type": "weather", "delay_min": 3}
        legs = [(Point(37.5, 127.0), Point(37.51, 127.0)), (Point(37.51, 127.0), Point(37.5, 127.0))]
        self.assertEqual(sit.route_delay([rain], legs)[0], 3)


class InterventionTest(unittest.TestCase):
    def setUp(self):
        m.store = Store()

    def test_accident_on_route_warns_once_then_escalates_to_late(self):
        sid = session()
        m.accept(sid, m.AcceptIn(gig_id="G-101", now=T("17:20")), idempotency_key="k")
        m.assignment_action(sid, "start")
        said = spoken_between(sid, "17:21", "17:40")
        kinds = [iv["kind"] for _, iv in said]
        self.assertEqual(said[0][0], "17:27")            # 사고가 난 그 순간 말한다
        self.assertIn(said[0][1]["kind"], ("tight", "info"))
        self.assertIn("late", kinds)                       # 비까지 오면 '늦어요'로 올라간다
        late = next(iv for _, iv in said if iv["kind"] == "late")
        self.assertIn("아이 픽업이 먼저", late["say"])
        self.assertTrue(late["actions"])
        self.assertEqual(len([k for k in kinds if k == "weather"]), 0)  # 비 안내는 늦음 안내에 합쳐 한 번만
        times = [t for t, _ in said]
        self.assertEqual(len(times), len(set(times)))    # 같은 순간에 두 번 말하지 않는다

    def test_no_talk_when_route_not_affected(self):
        sid = session(wants_work=False)
        said = spoken_between(sid, "17:21", "17:37")
        self.assertEqual(said, [])                         # 사고가 나도 걸어서 픽업하는 사람에겐 조용히

    def test_resting_user_gets_no_new_gig_but_gets_umbrella_tip(self):
        sid = session()
        said = [iv for _, iv in spoken_between(sid, "17:21", "17:40")]
        self.assertIn("new_gig", [iv["kind"] for iv in said])
        m.store = Store()
        sid = session()
        said = []
        t = T("17:21")
        while t <= T("17:40"):
            said += m.situation(sid, now=t, resting=True)["interventions"]
            t += timedelta(minutes=1)
        kinds = [iv["kind"] for iv in said]
        self.assertNotIn("new_gig", kinds)
        self.assertIn("우산", next(iv["say"] for iv in said if iv["kind"] == "weather"))

    def test_schedule_change_offers_extend(self):
        sid = session()
        m.add_incident(m.IncidentIn(type="schedule_change", now=T("17:30"), minutes=15), sid=sid)
        iv = next(iv for iv in m.situation(sid, now=T("17:30"))["interventions"] if iv["kind"] == "schedule")
        self.assertIn("18:10", iv["say"])
        r = m.situation_action(sid, m.InterventionAction(action="extend", minutes=15))
        self.assertEqual(r["return_by"], "18:10")
        self.assertEqual(m.recommendations(sid, now=T("17:30"))["remaining_min"], 40)

    def test_live_traffic_changes_recommendations(self):
        sid = session()
        before = [g["gig_id"] for g in m.recommendations(sid, now=T("17:20"))["recommended"]]
        after = m.recommendations(sid, now=T("17:28"))
        self.assertIn("G-101", before)
        reason = next(g["reasons"][0] for g in after["excluded"] if g["gig_id"] == "G-101")
        self.assertIn("교통 상황", reason)

    def test_new_gig_appears_only_after_posted(self):
        sid = session()
        self.assertNotIn("G-107", [g["gig_id"] for g in m.recommendations(sid, now=T("17:25"))["recommended"]])
        self.assertIn("G-107", [g["gig_id"] for g in m.recommendations(sid, now=T("17:33"))["recommended"]])

    def test_pickup_reminders(self):
        sid = session(wants_work=False)
        said = {iv["kind"] for _, iv in spoken_between(sid, "17:44", "17:56")}
        self.assertIn("remind", said)


class EnforcementTest(unittest.TestCase):
    def test_estimate_counter_and_no_schedule_leak(self):
        r = m.enforcement(lat=37.49985, lng=127.0633, now=T("17:20"))
        z = r["zones"][0]
        self.assertEqual(z["fine_car"], 120000)
        self.assertTrue(z["is_estimate"])
        self.assertLess(z["today_estimate_so_far"], z["today_estimate_total"])
        self.assertGreater(m.enforcement(lat=37.49985, lng=127.0633, now=T("18:20"))["zones"][0]["today_estimate_so_far"],
                           z["today_estimate_so_far"])
        for k in ("open", "close", "camera", "hours"):   # 단속 시간·카메라 위치는 내보내지 않는다
            self.assertNotIn(k, z)


if __name__ == "__main__":
    unittest.main()


class MarketAndSpotsTest(unittest.TestCase):
    def setUp(self):
        m.store = Store()

    def test_josa(self):
        self.assertEqual(sit.josa("카시트", "이", "가"), "가")
        self.assertEqual(sit.josa("책", "이", "가"), "이")
        self.assertEqual(sit.josa_ro("동네마트"), "로")
        self.assertEqual(sit.josa_ro("학원 정문"), "으로")
        self.assertEqual(sit.josa_ro("서울"), "로")

    def test_wishlist_item_announced_when_posted_and_fits(self):
        sid = session(wishlist=["유아 카시트"], wants_work=False)
        said = [(t, iv) for t, iv in spoken_between(sid, "17:21", "17:35") if iv["kind"] == "market"]
        self.assertEqual(said[0][0], "17:30")                   # 매물이 올라온 그 순간
        say = said[0][1]["say"]
        self.assertIn("유아 카시트가 근처에 올라왔어요", say)
        self.assertIn("4만 원", say)
        self.assertIn("구매 메시지", say)
        self.assertEqual(said[0][1]["actions"][0]["action"], "market_go")

    def test_far_or_late_listing_not_announced(self):
        sid = session(wishlist=["아이 자전거"])
        self.assertFalse([iv for _, iv in spoken_between(sid, "17:21", "17:35") if iv["kind"] == "market"])

    def test_market_go_sends_message_and_navigates(self):
        sid = session(wishlist=["유아 카시트"])
        r = m.market_go(sid, "L-1", m.MarketGoIn(now=T("17:31")))
        self.assertIn("메시지 보냈어요", r["say"])
        self.assertEqual(len(r["trip"]["waypoints"]), 2)
        self.assertIn("샘플아파트 정문으로 가면", r["trip"]["message"])
        with self.assertRaises(m.HTTPException) as cm:   # 주행 중에는 시작하지 않는다
            m.market_go(sid, "L-1", m.MarketGoIn(now=T("17:31"), vehicle_state={"gear": "D"}))
        self.assertEqual(cm.exception.status_code, 423)
        self.assertEqual(m.trip_action(sid, "done")["trip"], None)

    def test_rush_while_driving_suggests_loop_and_parking_spot(self):
        sid = session()
        ivs = m.situation(sid, now=T("17:48"), gear="D")["interventions"]
        rush = next(iv for iv in ivs if iv["kind"] == "rush")
        self.assertIn("한 바퀴", rush["say"])
        self.assertIn("무료 주차", rush["say"])
        self.assertEqual([a["action"] for a in rush["actions"]], ["loop_route", "go_spot"])

    def test_waiting_spots_only_with_parking(self):
        spots = m.waiting_spots(lat=37.49985, lng=127.0633, now=T("17:20"))["spots"]
        self.assertTrue(spots)
        self.assertTrue(all(s["parking"] for s in spots))
