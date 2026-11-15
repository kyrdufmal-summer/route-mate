"""API 핸들러 시나리오 테스트 (HTTP 클라이언트 없이 핸들러를 직접 호출)."""
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from app import main as m  # noqa: E402
from app.store import Store  # noqa: E402

NOW = datetime(2026, 11, 15, 17, 20)
DRIVER = {"qualifications": ["driver_license"], "insurance": {"gig_delivery": "2027-03-31T23:59:00"}}
LOT_B = {"lat": 37.49975, "lng": 127.06350}


def new_session(**kw):
    body = dict(position=LOT_B, return_by="2026-11-15T17:55:00", now=NOW, driver=DRIVER, radar_keywords=["약국"])
    body.update(kw)
    return m.create_session(m.SessionIn(**body))["session_id"]


def accept(sid, gig="G-101", key="k1", gear="P"):
    return m.accept(sid, m.AcceptIn(gig_id=gig, now=NOW, vehicle_state={"gear": gear}), idempotency_key=key)


class ApiScenarioTest(unittest.TestCase):
    def setUp(self):
        m.store = Store()  # 테스트마다 깨끗한 저장소

    def test_full_scenario(self):
        sid = new_session()
        rec = m.recommendations(sid, now=NOW)
        self.assertFalse(rec["driving"])
        self.assertIn("G-101", [g["gig_id"] for g in rec["recommended"]])
        res = accept(sid)
        self.assertEqual(res["assignment"]["state"], "accepted")
        self.assertEqual(res["navigation"]["waypoints"][1]["eta"], "17:48")
        self.assertEqual(m.assignment_action(sid, "start")["state"], "in_progress")
        self.assertEqual(m.assignment_action(sid, "complete")["state"], "completed")
        # 완료된 일감은 다시 추천되지 않음
        self.assertNotIn("G-101", [g["gig_id"] for g in m.recommendations(sid, now=NOW)["recommended"]])

    def test_driving_blocks_details_and_accept(self):
        sid = new_session()
        r = m.recommendations(sid, now=NOW, gear="D", speed_kmh=40)
        self.assertTrue(r["driving"])
        self.assertNotIn("recommended", r)
        self.assertLessEqual(len(r["voice_brief"]), 40)
        with self.assertRaises(HTTPException) as cm:
            accept(sid, gear="D")
        self.assertEqual(cm.exception.status_code, 423)

    def test_idempotent_accept(self):
        sid = new_session()
        a = accept(sid, key="same")
        b = accept(sid, key="same")
        self.assertTrue(b.get("idempotent_replay"))
        self.assertEqual(a["assignment"]["accepted_at"], b["assignment"]["accepted_at"])
        self.assertEqual(sum(1 for e in m.store.audit if e["event"] == "gig_accepted"), 1)

    def test_atomic_accept_one_winner(self):
        sids = [new_session() for _ in range(8)]
        results = []

        def go(s):
            try:
                accept(s, key="k-" + s)
                results.append("ok")
            except HTTPException as e:
                results.append(e.status_code)

        ts = [threading.Thread(target=go, args=(s,)) for s in sids]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count(409), 7)

    def test_taken_gig_hidden_from_others(self):
        a, b = new_session(), new_session()
        accept(a)
        self.assertNotIn("G-101", [g["gig_id"] for g in m.recommendations(b, now=NOW)["recommended"]])

    def test_event_pauses_recommendations_and_cancel(self):
        sid = new_session()
        accept(sid)
        r = m.vehicle_event(sid, m.EventIn(type="gig_cancelled", now=NOW))
        self.assertTrue(r["paused"])
        self.assertEqual(r["assignment"]["state"], "cancelled")
        rec = m.recommendations(sid, now=NOW)
        self.assertEqual(rec["mode"], "paused")
        self.assertEqual(rec["recommended"], [])
        with self.assertRaises(HTTPException):
            accept(sid, gig="G-102", key="k2")

    def test_traffic_delay_warns_when_late(self):
        sid = new_session()
        accept(sid)
        r = m.vehicle_event(sid, m.EventIn(type="traffic_delay", delay_min=30, now=datetime(2026, 11, 15, 17, 30)))
        self.assertIn("늦는다고 알리고", r["guidance"][0])

    def test_traffic_delay_ok_when_on_time(self):
        sid = new_session()
        accept(sid)
        r = m.vehicle_event(sid, m.EventIn(type="traffic_delay", delay_min=2, now=NOW))
        self.assertIn("이면 돌아와요", r["guidance"][0])

    def test_parking_full_gives_legal_alternatives(self):
        sid = new_session()
        r = m.vehicle_event(sid, m.EventIn(type="parking_full", now=NOW))
        self.assertTrue(r["alternatives"])
        self.assertTrue(all(x["pickup_zone_legal"] for x in r["alternatives"]))
        self.assertNotIn("P-B", [x["id"] for x in r["alternatives"]])  # 꽉 찬 복귀 주차장은 대안에서 제외

    def test_consent_required_and_delete(self):
        with self.assertRaises(HTTPException):
            new_session(consent_location=False)
        sid = new_session()
        accept(sid)
        m.delete_session(sid)
        with self.assertRaises(HTTPException) as cm:
            m.recommendations(sid, now=NOW)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertNotIn("G-101", m.store.gig_owner)
        self.assertFalse(any("position" in e for e in m.store.audit if e.get("session") == sid))

    def test_declined_gig_not_recommended_again(self):
        sid = new_session()
        m.decline(sid, m.DeclineIn(gig_id="G-101"))
        self.assertNotIn("G-101", [g["gig_id"] for g in m.recommendations(sid, now=NOW)["recommended"]])
        other = new_session()  # 다른 사용자에게는 영향 없음
        self.assertIn("G-101", [g["gig_id"] for g in m.recommendations(other, now=NOW)["recommended"]])

    def test_invalid_transition_message_korean(self):
        sid = new_session()
        accept(sid)
        with self.assertRaises(HTTPException) as cm:
            m.assignment_action(sid, "complete")
        self.assertEqual(cm.exception.detail, "'수락' 상태에서는 '완료' 처리를 할 수 없어요.")

    def test_rejects_past_return_time(self):
        with self.assertRaises(HTTPException):
            new_session(return_by="2026-11-15T17:00:00")


if __name__ == "__main__":
    unittest.main()
