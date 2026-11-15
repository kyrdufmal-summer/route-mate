// ROUTE MATE 차량 화면 시뮬레이터 — Pleos Connect(AAOS) 클라이언트의 화면 흐름을 웹으로 재현
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const S = {
  now: null, scenario: null, lots: [], lotsExcluded: [], lot: null,
  session: null, recs: null, gear: "P", lastAccept: null,
};

// ---------- utils ----------
const pad = (n) => String(n).padStart(2, "0");
function toIso(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
}
const hhmm = (iso) => iso.slice(11, 16);
const won = (n) => (n == null ? "-" : n.toLocaleString("ko-KR") + "원");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    const msg = typeof d === "string" ? d : d?.message ? `${d.message} ${(d.reasons || []).join(", ")}` : `오류 ${res.status}`;
    throw new Error(msg);
  }
  return body;
}

function say(text) {
  $("#voiceText").textContent = text;
  try {
    if ("speechSynthesis" in window) {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "ko-KR"; u.rate = 1.05;
      speechSynthesis.speak(u);
    }
  } catch (_) { /* TTS 미지원 환경 무시 */ }
}

function showStep(n) {
  $$(".steps button").forEach((b) => b.classList.toggle("active", b.dataset.step == n));
  [1, 2, 3, 4].forEach((i) => $(`#panel${i}`).classList.toggle("hidden", i != n));
}

// ---------- map ----------
function drawMap() {
  const pts = [];
  const add = (lat, lng, kind, label) => pts.push({ lat, lng, kind, label });
  const sc = S.scenario;
  add(sc.destination.lat, sc.destination.lng, "dest", "목적지");
  S.lots.forEach((l) => add(l.lat, l.lng, "lot", l.name.replace("샘플 ", "")));
  (S.recs?.recommended || []).forEach((g) => add(g.lat, g.lng, "gig", g.gig_id));
  const asg = S.recs?.assignment;
  if (asg && ["accepted", "in_progress"].includes(asg.state)) add(asg.evaluation.lat, asg.evaluation.lng, "gig", "진행 업무");
  (S.recs?.radar?.organic || []).forEach((p) => add(p.lat, p.lng, "place", p.name.replace("샘플 ", "")));
  (S.recs?.radar?.sponsored || []).forEach((p) => add(p.lat, p.lng, "place", "[광고] " + p.name.replace("샘플 ", "")));
  const car = S.lot ? { lat: S.lot.lat, lng: S.lot.lng } : sc.vehicle_position;
  add(car.lat, car.lng, "car", "내 차량");

  const lats = pts.map((p) => p.lat), lngs = pts.map((p) => p.lng);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const span = Math.max(maxLat - minLat, maxLng - minLng, 0.004);
  const cx = (minLng + maxLng) / 2, cy = (minLat + maxLat) / 2;
  const X = (lng) => 260 + ((lng - cx) / span) * 400;
  const Y = (lat) => 260 - ((lat - cy) / span) * 400;
  const color = { car: "#fff", dest: "var(--dest)", lot: "var(--lot)", gig: "var(--gig)", place: "var(--place)" };

  let svg = "";
  for (let i = 0; i <= 520; i += 52) svg += `<line x1="${i}" y1="0" x2="${i}" y2="520" stroke="#1b2633"/><line x1="0" y1="${i}" x2="520" y2="${i}" stroke="#1b2633"/>`;
  const a = S.recs?.assignment;
  if (a && ["accepted", "in_progress"].includes(a.state) && S.lastAccept) {
    const [w1, w2] = S.lastAccept.navigation.waypoints;
    svg += `<polyline points="${X(car.lng)},${Y(car.lat)} ${X(w1.lng)},${Y(w1.lat)} ${X(w2.lng)},${Y(w2.lat)}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-dasharray="8 6"/>`;
  }
  pts.forEach((p) => {
    const r = p.kind === "car" ? 9 : 6;
    svg += `<circle cx="${X(p.lng)}" cy="${Y(p.lat)}" r="${r}" fill="${color[p.kind]}" stroke="#000" stroke-width="1.5"/>`;
    svg += `<text x="${X(p.lng) + 10}" y="${Y(p.lat) + 4}" fill="#c9d4e0" font-size="11">${esc(p.label)}</text>`;
  });
  svg += `<text x="10" y="510" fill="#5d6b7d" font-size="10">도식 지도 · 실차에서는 내비게이션 지도 레이어로 대체</text>`;
  $("#map").innerHTML = svg;
}

// ---------- step 1: parking ----------
async function loadParking() {
  const sc = S.scenario;
  const r = await api("/api/parking/search", {
    method: "POST",
    body: JSON.stringify({
      origin: sc.vehicle_position, destination: sc.destination, now: S.now, stay_until: sc.pickup_end,
      vehicle: sc.vehicle, pickup_only: $("#pickupOnly").checked, has_academy_receipt: $("#receipt").checked,
    }),
  });
  S.lots = r.recommended; S.lotsExcluded = r.excluded;
  $("#lots").innerHTML = r.recommended.map((l, i) => `
    <div class="card ${S.lot?.id === l.id ? "selected" : ""}">
      <div class="top"><span class="name">${esc(l.name)}</span><span class="big">${won(l.fee_estimate)}</span></div>
      <div class="meta">
        차로 ${l.drive_min}분 · 입구: ${esc(l.entrance)} · 목적지까지 도보 ${l.walk_to_destination_min}분 · 운영 ${l.hours} · ${l.stay_min}분 체류 기준
      </div>
      <div class="meta">
        ${l.discounts_applied.map((d) => `<span class="tag ok">할인 적용: ${esc(d)}</span>`).join("")}
        ${l.discounts_need_check.map((d) => `<span class="tag warn">확인 필요: ${esc(d)} → ${won(l.fee_if_pending_discount_confirmed)}</span>`).join("")}
        <span class="tag ${l.realtime_spaces.status === "확인됨" ? "ok" : "warn"}">잔여면 ${l.realtime_spaces.value ?? l.realtime_spaces.label}</span>
        <span class="tag warn">발렛 ${l.valet.value ?? "미확인"}</span>
        ${l.pickup_zone_legal ? '<span class="tag ok">합법 승하차</span>' : ""}
      </div>
      <div class="meta">출처: ${esc(l.source)} · 갱신 ${l.updated_at.replace("T", " ").slice(0, 16)} (${l.data_freshness})</div>
      <div class="row"><button class="primary" data-park="${i}">여기에 주차</button></div>
    </div>`).join("") || `<div class="card">조건에 맞는 주차장이 없어요.</div>`;
  $("#lotsExcluded").innerHTML = r.excluded.map((x) => `<div class="card"><b>${esc(x.name)}</b><div class="meta">${x.reasons.map(esc).join(" / ")}</div></div>`).join("");
  $$("[data-park]").forEach((b) => (b.onclick = () => park(S.lots[b.dataset.park])));
  drawMap();
}

function park(lot) {
  S.lot = lot;
  say(`${lot.name.replace("샘플 ", "")}에 주차했어요. 돌아올 시각을 알려주시면 남는 시간을 계획해 드릴게요.`);
  showStep(2);
  drawMap();
}

// ---------- step 2: flex window ----------
async function parseUtterance() {
  const r = await api("/api/intent", { method: "POST", body: JSON.stringify({ utterance: $("#utter").value, now: S.now }) });
  if (r.return_by) $("#returnBy").value = r.return_by;
  if (r.min_buffer_min != null) $("#buffer").value = r.min_buffer_min;
  if (r.max_drive_min != null) $("#maxDrive").value = r.max_drive_min;
  if (r.wants_work != null) $("#wantsWork").checked = r.wants_work;
  $$("input[name=kw]").forEach((c) => (c.checked = r.keywords.includes(c.value)));
  say(`${r.return_by ?? "복귀 시각 미인식"}까지 ${r.return_to_here ? "이곳으로 복귀" : "복귀"}, 일감 ${r.wants_work ? "보기" : "끄기"}로 이해했어요. 확인 후 켜 주세요.`);
}

async function startWindow() {
  if (!S.lot) return say("먼저 주차할 곳을 골라 주세요.");
  const day = S.now.slice(0, 10);
  const md = $("#maxDrive").value;
  try {
    const r = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        position: { lat: S.lot.lat, lng: S.lot.lng }, return_point: null,
        return_by: `${day}T${$("#returnBy").value}:00`, now: S.now,
        min_buffer_min: Number($("#buffer").value), max_drive_min: md === "" ? null : Number(md),
        wants_work: $("#wantsWork").checked,
        radar_keywords: $$("input[name=kw]:checked").map((c) => c.value),
        driver: S.scenario.driver, consent_location: $("#consent").checked,
      }),
    });
    S.session = r.session_id;
    say(`FLEX WINDOW를 켰어요. ${r.window.return_by}까지 ${r.window.available_min}분이 있어요.`);
    await loadRecs();
    showStep(3);
  } catch (e) { say(e.message); }
}

// ---------- step 3: recommendations ----------
function timeBar(bd, available) {
  const go = bd.drive_to_site ?? bd.walk_to_site, back = bd.drive_back ?? bd.walk_back;
  const free = Math.max(available - bd.total, 0);
  const seg = (cls, v, label) => (v > 0 ? `<span class="${cls}" style="flex:${v}">${label} ${v}</span>` : "");
  return `<div class="bar">${seg("go", go, "이동")}${seg("task", bd.task, "업무")}${seg("back", back, "복귀")}${seg("buf", bd.safety_buffer, "여유")}${seg("free", free, "남음")}</div>`;
}

async function loadRecs() {
  if (!S.session) return;
  const q = new URLSearchParams({ now: S.now, gear: S.gear, speed_kmh: S.gear === "D" ? 30 : 0 });
  const r = await api(`/api/sessions/${S.session}/recommendations?${q}`);
  if (r.driving) {
    $("#panel3").innerHTML = `<div class="driving-lock">🚗 주행 중에는 상세 목록과 수락이 제한돼요.<br><br><b>${esc(r.voice_brief)}</b></div>`;
    say(r.voice_brief);
    return;
  }
  S.recs = r;
  const available = r.remaining_min;
  $("#recMsg").textContent = `${r.message} · 복귀까지 ${available}분`;
  $("#gigs").innerHTML = r.recommended.map((g) => `
    <div class="card">
      <div class="top"><span class="name">${esc(g.title)}</span><span class="big">${won(g.net_profit)}</span></div>
      <div class="meta">${esc(g.partner)} · 보수 ${won(g.pay)} − 차량비 ${won(g.costs.vehicle)} − 주차 ${won(g.costs.parking)} = 예상 순수익 · 시간당 ${won(g.net_per_hour)}</div>
      ${timeBar(g.breakdown, available)}
      <div class="meta">업무 마치고 <b>${g.finish_at}</b> 복귀 (마감까지 ${g.slack_min}분 여유) · 신뢰도 ${Math.round(g.trust * 100)}%</div>
      <div class="row"><button class="primary" data-accept="${g.gig_id}">정차 상태에서 수락</button><button data-decline="${g.gig_id}">거절</button></div>
    </div>`).join("");
  $("#gigsExcluded").innerHTML = r.excluded.map((g) => `<div class="card"><b>${esc(g.title)}</b><div class="meta">${g.reasons.map(esc).join(" / ")}</div></div>`).join("") || "<div class='meta'>없음</div>";
  $("#radar").innerHTML = r.radar.organic.map((p) => `
    <div class="card"><div class="top"><span class="name">${esc(p.name)}</span><span>도보 ${p.walk_min}분</span></div>
    <div class="meta">${p.keywords.map((k) => `<span class="tag">${esc(k)}</span>`).join("")} 영업 ${p.hours} · 출처 ${esc(p.source)}</div></div>`).join("") || "<div class='meta'>선택한 키워드에 맞는 곳이 없어요.</div>";
  $("#radarAds").innerHTML = r.radar.sponsored.length ? `<h3>광고 · 제휴</h3>` + r.radar.sponsored.map((p) => `
    <div class="card"><span class="tag ad">광고</span><b>${esc(p.name)}</b><div class="meta">도보 ${p.walk_min}분 · ${esc(p.source)}</div></div>`).join("") : "";
  $$("[data-accept]").forEach((b) => (b.onclick = () => accept(b.dataset.accept)));
  $$("[data-decline]").forEach((b) => (b.onclick = () => { b.closest(".card").remove(); say("거절했어요. 다른 선택지를 보여 드릴게요."); }));
  if (r.mode === "work") say(r.recommended.length ? `조건에 맞는 일감 ${r.recommended.length}건이 있어요. 쉬셔도 괜찮아요.` : r.message);
  drawMap();
  renderAssignment();
}

async function accept(gigId) {
  const key = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  try {
    const r = await api(`/api/sessions/${S.session}/accept`, {
      method: "POST", headers: { "Idempotency-Key": key },
      body: JSON.stringify({ gig_id: gigId, now: S.now, vehicle_state: { gear: S.gear, speed_kmh: S.gear === "D" ? 30 : 0 } }),
    });
    S.lastAccept = r;
    const [w1, w2] = r.navigation.waypoints;
    say(`수락했어요. ${w1.eta}에 업무지 도착, ${w2.eta}에 이곳으로 복귀하는 경로로 안내합니다.`);
    await loadRecs();
    showStep(4);
  } catch (e) { say(e.message); }
}

// ---------- step 4: progress ----------
function renderAssignment() {
  const a = S.recs?.assignment;
  if (!a) { $("#assignment").innerHTML = `<div class="notice">진행 중인 업무가 없어요.</div>`; return; }
  const ev = a.evaluation;
  const nav = S.lastAccept?.navigation;
  $("#assignment").innerHTML = `
    <div class="card"><div class="top"><span class="name">${esc(ev.title)}</span><span class="tag ${a.state === "cancelled" ? "bad" : "ok"}">${a.state}</span></div>
    ${timeBar(ev.breakdown, ev.breakdown.total + ev.slack_min)}
    <div class="meta">${nav ? nav.waypoints.map((w) => `${esc(w.label)} ${w.eta}`).join(" → ") + ` · 복귀 마감 ${nav.return_by}` : ""}</div>
    <div class="meta">예상 순수익 ${won(ev.net_profit)} · 내비게이션: ${esc(nav?.provider ?? "")}</div></div>`;
}

async function transition(action) {
  try {
    const a = await api(`/api/sessions/${S.session}/assignment/${action}`, { method: "POST" });
    say({ start: "업무를 시작해요. 복귀 시각을 계속 확인할게요.", complete: "수고하셨어요. 복귀 경로로 안내합니다.", cancel: "업무를 취소했어요. 안전하게 복귀하세요." }[action]);
    await loadRecs();
    if (a.state !== "in_progress") renderAssignment();
  } catch (e) { say(e.message); }
}

async function sendEvent(type) {
  try {
    const r = await api(`/api/sessions/${S.session}/events`, { method: "POST", body: JSON.stringify({ type, delay_min: type === "traffic_delay" ? 10 : 0, now: S.now }) });
    let html = r.guidance.map((g) => `<div class="notice">${esc(g)}</div>`).join("");
    if (r.alternatives) html += r.alternatives.map((l) => `<div class="card"><b>${esc(l.name)}</b><div class="meta">예상 ${won(l.fee_estimate)} · 도보 ${l.walk_to_destination_min}분</div></div>`).join("");
    $("#guidance").innerHTML = html;
    say(r.guidance[0]);
    await loadRecs();
  } catch (e) { say(e.message); }
}

// ---------- wiring ----------
async function init() {
  S.scenario = await api("/api/demo/scenario");
  S.now = S.scenario.now;
  S.panel3Html = $("#panel3").innerHTML;
  $("#clock").textContent = hhmm(S.now);
  $("#utter").value = S.scenario.utterance;
  $$(".steps button").forEach((b) => (b.onclick = () => showStep(b.dataset.step)));
  $("#pickupOnly").onchange = loadParking;
  $("#receipt").onchange = loadParking;
  $("#parse").onclick = parseUtterance;
  $("#startWindow").onclick = startWindow;
  $("#startTask").onclick = () => transition("start");
  $("#completeTask").onclick = () => transition("complete");
  $("#cancelTask").onclick = () => transition("cancel");
  $$("[data-event]").forEach((b) => (b.onclick = () => sendEvent(b.dataset.event)));
  $("#resume").onclick = async () => { await api(`/api/sessions/${S.session}/resume`, { method: "POST" }); $("#guidance").innerHTML = ""; say("추천을 다시 시작했어요."); loadRecs(); };
  $("#deleteSession").onclick = async () => {
    if (!S.session) return;
    await api(`/api/sessions/${S.session}`, { method: "DELETE" });
    S.session = null; S.recs = null; S.lastAccept = null;
    say("세션 데이터를 삭제했어요."); showStep(1); drawMap();
  };
  $("#tick").onclick = () => {
    const d = new Date(S.now); d.setMinutes(d.getMinutes() + 5);
    S.now = toIso(d); $("#clock").textContent = hhmm(S.now);
    loadRecs();
  };
  $("#toggleDrive").onclick = () => {
    S.gear = S.gear === "P" ? "D" : "P";
    const v = $("#vstate");
    v.textContent = S.gear === "P" ? "P · 정차" : "D · 주행 30km/h";
    v.className = "pill " + (S.gear === "P" ? "parked" : "driving");
    $$("[data-accept]").forEach((b) => (b.disabled = S.gear !== "P"));
    if (S.gear === "P" && $("#panel3").querySelector(".driving-lock")) $("#panel3").innerHTML = S.panel3Html;
    loadRecs();
  };
  setInterval(async () => { try { $("#audit").textContent = JSON.stringify(await api("/api/audit?limit=30"), null, 1); } catch (_) {} }, 3000);
  await loadParking();
  say("안녕하세요. 목적지 근처 검증된 주차장을 비교했어요.");
}
init();
