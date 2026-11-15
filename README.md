# ROUTE MATE — FLEX WINDOW

> 차량의 정차 위치·이동 경로와 사용자가 지정한 **복귀 시각**을 결합해 안전한 주차와 생활정보를 제공하고,
> 원하는 경우에만 주변 초단기 일감을 선택적으로 연결하는 **차량용 AI 생활동선 에이전트** — 현대자동차그룹 차량용 앱 개발 공모전 출품작 MVP

추천의 기본 단위는 주차장 검색이나 구인 목록이 아니라 **정차 세션 = 위치 × 체류시간 × 복귀 마감**입니다.
쉬기·볼일 보기·짧게 일하기는 동등한 선택지이며, 소득 활동을 강요하지 않습니다.

> ⚠️ **모든 주차장·일감·상점 데이터는 가상 샘플입니다.** 제휴가 확보되지 않은 MVP 이므로 실제 매장·보수·요금이 아니며, 화면에도 `[샘플]` 로 표기합니다.

---

## 이번 제출에서 실제로 동작하는 것

| 기획서 기능 | 구현 위치 | 상태 |
|---|---|---|
| ① **PARKING TRUTH** — 공식 요금표 기준 체류 총비용, 운영시간·차고 제한, 할인, 출처/갱신시각/미확인 표시 | `backend/app/engine/parking.py` | ✅ 동작 |
| ② **SAFE PICKUP** — 합법 승하차 장소만 필터, 목적지까지 도보 시간 | 같은 파일 (`pickup_only`) | ✅ 동작 |
| ③ **FLEX WINDOW** — 복귀 시각·복귀 기준점·최소 여유·최대 우회·희망 업무 설정, 일 끄기(휴식 모드) | `engine/flex_window.py`, `POST /api/sessions` | ✅ 동작 |
| ④ **ROUTE-FIT MATCH** — (A) 법적 적합성·자격·보험·주차 필수 필터 → (B) 이동·업무·복귀·안전여유 합산 → (C) 마감 초과 제외 → (D) 우회·순수익·신뢰도 정렬, 예상 순수익/시간당 순수익 | `engine/flex_window.py` | ✅ 동작 |
| ⑤ **차량 특화** — 주행 중 상세 조회·수락 차단(서버 423), 짧은 음성 브리핑(TTS), 수락 시 업무지→복귀지 경유 안내 | `engine/safety.py`, `frontend/` | ✅ 시뮬레이터에서 동작 |
| ⑥ **ROUTE RADAR** — 미리 고른 키워드만 경로 주변 생활정보와 연결, 광고/제휴 분리 표시 | `engine/radar.py` | ✅ 동작 |
| 음성 의도 해석 ("17:55까지 이곳에 돌아와야 해요…") | `engine/intent.py` | ✅ 규칙 기반 (LLM 교체 가능 인터페이스) |
| 원자적 수락 · 중복요청 방지(Idempotency-Key) · 상태 머신 · 감사 로그 | `backend/app/store.py` | ✅ 동작 (동시 8건 → 1건만 성공 테스트) |
| 교통 악화·업무 취소·주차 만차 → 추가 추천 중지, 안전 복귀/고객 지연 안내/합법 대체 주차 | `POST /api/sessions/{id}/events` | ✅ 동작 |
| 위치 동의·동의 철회 시 세션 삭제, 감사 로그 위치 약 100m 격자로 최소화 | `store.py` | ✅ 동작 |

### 아직 구현하지 않은 것 (허위 기재 방지)

- **Pleos Connect AAOS 네이티브 앱(APK)** — 개발 PC 에 Android SDK 가 없어 이번 제출에는 빌드하지 못했습니다. 대신 차량 중앙 디스플레이와 같은 흐름을 **웹 시뮬레이터**(`frontend/`)로 구현했고, 백엔드 API 는 AAOS 클라이언트가 그대로 호출할 수 있게 설계했습니다.
- **Pleos SDK 연동** (FusedLocation / Vehicle / NaviHelper / STT·TTS) — 현재는 `engine/geo.py` 의 보수적 거리 추정기와 브라우저 TTS 로 대체. 실제 API 메서드·권한·에뮬레이터 지원 범위는 Pleos 공식 문서로 검증 후 교체합니다.
- **PostgreSQL** — MVP 는 메모리 저장소 + 락. 같은 규칙을 `SELECT … FOR UPDATE` + idempotency key UNIQUE 제약으로 이전 예정.
- **실데이터** — 공공 주차시설 데이터·제휴 운영사/매장 피드 미연결. 잔여면·발렛·실시간 가격은 검증 가능한 API 가 없으면 "미확인"으로 표시하는 동작만 구현.
- **LLM** — 의도 해석만 LLM 으로 교체 가능하게 분리했고, 안전·계약 판단은 항상 규칙 기반 코드가 합니다.
- 실제 출시 전 **유상운송 보험·근로/중개 관련 법률 검토**가 선행되어야 합니다.

---

## 대표 시연 장면 (가상)

17:20, 보호자가 자녀의 18:00 학원 종료를 기다리며 도착합니다.

1. **주차** — 목적지 주변 검증된 주차장을 비교. 18:00 에 문 닫는 C, 높이 1.85m 인 D 는 *이유와 함께* 제외. 미검증 할인은 금액에 반영하지 않고 "확인 필요"로 별도 표시.
2. **FLEX WINDOW** — "주차 후 17:55까지 이곳에 돌아와야 해요. 시간이 남으면 가까운 일도 볼래요" → 해석 결과를 화면에서 확인 후 켬.
3. **추천** — `[샘플] 꽃집 소형 꽃다발 픽업·전달`: 이동 5분 + 업무 10분 + 복귀 5분 + 안전여유 8분 = 28분 → 17:48 복귀(마감까지 7분 여유), 예상 순수익 11,600원. 보험 미가입·마감 초과·미검증 공급자 일감은 사유와 함께 제외. "잠시 쉬기"는 항상 동등한 선택지.
4. **수락** — 정차(P) 상태에서만 가능. 업무지 → 복귀 기준점 경유 안내. 교통 악화·취소·만차 이벤트 시 추가 추천을 멈추고 복귀를 우선.
5. **복귀 후 픽업** — 세션 데이터 삭제(동의 철회) 가능.

---

## 실행 방법

요구사항: Python 3.11+

```bash
pip install -r requirements.txt
```

```bash
python -m uvicorn app.main:app --app-dir backend --port 8765
```

브라우저에서 <http://localhost:8765> 를 열면 차량 화면 시뮬레이터가 뜹니다. 상단의 `+5분`(시뮬레이션 시각), `주행 전환`(P↔D) 버튼으로 시간 경과와 주행 상태를 바꿔 볼 수 있습니다. API 문서는 <http://localhost:8765/docs>.

### 테스트

외부 패키지 없이 표준 라이브러리 `unittest` 로 실행합니다 (30개).

```bash
python -m unittest discover -s backend/tests -v
```

---

## 구조

```
backend/
  app/
    main.py              FastAPI 엔드포인트 (차량 클라이언트가 호출하는 외부 서비스)
    store.py             정차 세션 · 원자적 수락 · 멱등성 · 상태 머신 · 감사 로그
    engine/
      parking.py         PARKING TRUTH / SAFE PICKUP
      flex_window.py     FLEX WINDOW / ROUTE-FIT MATCH 핵심 알고리즘 (A→B→C→D)
      radar.py           ROUTE RADAR
      intent.py          음성 의도 해석 (규칙 기반, LLM 교체 가능)
      safety.py          주행 중 상호작용 제한
      geo.py             거리·ETA 추정 (NaviHelper/FusedLocation 대체 지점)
    data/                가상 샘플 데이터 (주차장·일감·생활정보)
  tests/                 엔진 단위 테스트 + API 시나리오 테스트
frontend/                차량 중앙 디스플레이 웹 시뮬레이터 (HTML/CSS/JS, 빌드 불필요)
```

### 주요 API

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/parking/search` | 주차장 비교 (예상 요금·도보·출처·미확인 상태, 제외 사유) |
| POST | `/api/intent` | 발화 → FLEX WINDOW 설정 제안 |
| POST | `/api/sessions` | FLEX WINDOW 켜기 (정차 세션 생성, 위치 동의 필수) |
| GET | `/api/sessions/{id}/recommendations` | 일감 추천 + 제외 사유 + ROUTE RADAR. 주행 중에는 음성 브리핑만 |
| POST | `/api/sessions/{id}/accept` | 일감 수락 (`Idempotency-Key` 헤더 필수, 정차 상태만, 수락 시점 재검증) |
| POST | `/api/sessions/{id}/assignment/{start\|complete\|cancel}` | 업무 상태 전이 |
| POST | `/api/sessions/{id}/events` | 교통 악화 / 업무 취소 / 주차 만차 |
| DELETE | `/api/sessions/{id}` | 동의 철회 · 세션 삭제 |

## 안전·품질 원칙

- 주정차 단속 회피 정보나 불법 정차 장소는 데이터 모델에 두지 않으며 추천하지 않습니다.
- 주행 중 긴 입력·상세 조회·수락을 차단합니다 (서버에서도 강제).
- 무보험·미검증·법적 검토 미완료 일감은 어떤 점수로도 추천되지 않습니다.
- 아동 신상·학원 정보는 수집하지 않습니다. 목적지는 사용자가 지정한 좌표만 받습니다.
- 확인할 수 없는 정보는 숨기거나 추정하지 않고 "미확인"으로 표시합니다.

## 단계별 로드맵

- **P0 (이번 MVP)** 주차 비교·예상 요금 · 가용시간 입력 · 복귀 마감 필터 · 경유 안내 데이터
- **P1** Pleos AAOS 클라이언트 · NaviHelper/Vehicle SDK 연동 · 승인된 일감 피드 · PostgreSQL
- **P2** Safe Pickup 고도화 · Route Radar 지역 가게 참여 · 파일럿(학원가 1개 생활권)
