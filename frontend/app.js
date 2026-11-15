// ROUTE MATE 차량 화면 시뮬레이터 — Pleos Connect 차량용 앱의 화면 흐름을 웹으로 재현
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const S = {
  now: null, scenario: null, lots: [], lot: null,
  session: null, recs: null, gear: "P", lastAccept: null, resting: false,
};

const STATE_KO = { accepted: "수락함", in_progress: "진행 중", completed: "완료", cancelled: "취소됨" };

// ---------- 공통 ----------
const pad = (n) => String(n).padStart(2, "0");
function toIso(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
}
const hhmm = (iso) => iso.slice(11, 16);
const won = (n) => (n == null ? "-" : n.toLocaleString("ko-KR") + "원");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortName = (s) => s.replace(/^샘플 /, "").replace(/^\[샘플\] /, "");

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    let msg = "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.";
    if (typeof d === "string") msg = d;
    else if (d?.message) msg = `${d.message} (${(d.reasons || []).join(", ")})`;
    else if (res.status === 422) msg = "입력한 값을 다시 확인해 주세요.";
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
  } catch (_) { /* 음성 안내를 지원하지 않는 환경은 화면 문구만 표시 */ }
}

function showStep(n) {
  $$(".steps button").forEach((b) => b.classList.toggle("active", b.dataset.step == n));
  [1, 2, 3, 4].forEach((i) => $(`#panel${i}`).classList.toggle("hidden", i != n));
}

// ---------- 지도 ----------
function drawMap() {
  const pts = [];
  const add = (lat, lng, kind, label) => pts.push({ lat, lng, kind, label });
  const sc = S.scenario;
  add(sc.destination.lat, sc.destination.lng, "dest", "목적지");
  S.lots.forEach((l) => add(l.lat, l.lng, "lot", shortName(l.name)));
  if (!S.resting) (S.recs?.recommended || []).forEach((g) => add(g.lat, g.lng, "gig", shortName(g.partner)));
  const asg = S.recs?.assignment;
  if (asg && ["accepted", "in_progress"].includes(asg.state)) add(asg.evaluation.lat, asg.evaluation.lng, "gig", "진행 중인 업무");
  (S.recs?.radar?.organic || []).forEach((p) => add(p.lat, p.lng, "place", shortName(p.name)));
  (S.recs?.radar?.sponsored || []).forEach((p) => add(p.lat, p.lng, "place", "[광고] " + shortName(p.name)));
  const car = S.lot ? { lat: S.lot.lat, lng: S.lot.lng } : sc.vehicle_position;
  add(car.lat, car.lng, "car", "내 차");

  const lats = pts.map((p) => p.lat), lngs = pts.map((p) => p.lng);
  const span = Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lngs) - Math.min(...lngs), 0.004);
  const cx = (Math.min(...lngs) + Math.max(...lngs)) / 2, cy = (Math.min(...lats) + Math.max(...lats)) / 2;
  const X = (lng) => 260 + ((lng - cx) / span) * 400;
  const Y = (lat) => 260 - ((lat - cy) / span) * 400;
  const color = { car: "#fff", dest: "var(--dest)", lot: "var(--lot)", gig: "var(--gig)", place: "var(--place)" };

  let svg = "";
  for (let i = 0; i <= 520; i += 52) svg += `<line x1="${i}" y1="0" x2="${i}" y2="520" stroke="#1b2633"/><line x1="0" y1="${i}" x2="520" y2="${i}" stroke="#1b2633"/>`;
  if (asg && ["accepted", "in_progress"].includes(asg.state) && S.lastAccept) {
    const [w1, w2] = S.lastAccept.navigation.waypoints;
    svg += `<polyline points="${X(car.lng)},${Y(car.lat)} ${X(w1.lng)},${Y(w1.lat)} ${X(w2.lng)},${Y(w2.lat)}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-dasharray="8 6"/>`;
  }
  // 같은 위치에 겹치는 이름표는 아래로 비켜 쓴다
  const used = {};
  pts.forEach((p) => {
    const r = p.kind === "car" ? 9 : 6;
    const key = `${Math.round(X(p.lng) / 14)}:${Math.round(Y(p.lat) / 14)}`;
    const dy = (used[key] = (used[key] ?? -1) + 1) * 13;
    svg += `<circle cx="${X(p.lng)}" cy="${Y(p.lat)}" r="${r}" fill="${color[p.kind]}" stroke="#000" stroke-width="1.5"/>`;
    svg += `<text x="${X(p.lng) + 10}" y="${Y(p.lat) + 4 + dy}" fill="#c9d4e0" font-size="11">${esc(p.label)}</text>`;
  });
  svg += `<text x="10" y="510" fill="#5d6b7d" font-size="10">간략 지도 · 실제 차량에서는 내비게이션 지도로 표시</text>`;
  $("#map").innerHTML = svg;
}

// ---------- 1. 주차장 비교 ----------
async function loadParking() {
  const sc = S.scenario;
  const r = await api("/api/parking/search", {
    method: "POST",
    body: JSON.stringify({
      origin: sc.vehicle_position, destination: sc.destination, now: S.now, stay_until: sc.pickup_end,
      vehicle: sc.vehicle, pickup_only: $("#pickupOnly").checked, has_academy_receipt: $("#receipt").checked,
    }),
  });
  S.lots = r.recommended;
  $("#lots").innerHTML = r.recommended.map((l, i) => `
    <div class="card ${S.lot?.id === l.id ? "selected" : ""}">
      <div class="top"><span class="name">${esc(l.name)}</span><span class="big">${won(l.fee_estimate)}</span></div>
      <div class="meta">
        차로 ${l.drive_min}분 · 입구: ${esc(l.entrance)} · 목적지까지 걸어서 ${l.walk_to_destination_min}분 · 운영 ${l.hours} · ${l.stay_min}분 주차 기준
      </div>
      <div class="meta">
        ${l.discounts_applied.map((d) => `<span class="tag ok">할인 적용: ${esc(d)}</span>`).join("")}
        ${l.discounts_need_check.map((d) => `<span class="tag warn">확인 필요: ${esc(d)} (확인되면 ${won(l.fee_if_pending_discount_confirmed)})</span>`).join("")}
        <span class="tag ${l.realtime_spaces.status === "확인됨" ? "ok" : "warn"}">빈자리 ${l.realtime_spaces.value != null ? l.realtime_spaces.value + "면" : l.realtime_spaces.label}</span>
        <span class="tag warn">발레파킹 ${l.valet.value == null ? "미확인" : l.valet.value ? "가능" : "불가"}</span>
        ${l.pickup_zone_legal ? '<span class="tag ok">합법 승하차 가능</span>' : ""}
      </div>
      <div class="meta">출처: ${esc(l.source)} · ${l.updated_at.replace("T", " ").slice(5, 16)} 갱신 (${l.data_freshness})</div>
      <div class="row"><button class="primary" data-park="${i}">여기에 주차</button></div>
    </div>`).join("") || `<div class="card">조건에 맞는 주차장이 없어요.</div>`;
  $("#lotsExcluded").innerHTML = r.excluded.map((x) => `<div class="card"><b>${esc(x.name)}</b><div class="meta">${x.reasons.map(esc).join(" / ")}</div></div>`).join("") || "<div class='meta'>없음</div>";
  $$("[data-park]").forEach((b) => (b.onclick = () => park(S.lots[b.dataset.park])));
  drawMap();
}

function park(lot) {
  S.lot = lot;
  say(`${shortName(lot.name)}에 주차했어요. 돌아올 시각을 알려 주시면 남는 시간을 계획해 드릴게요.`);
  showStep(2);
  loadParking();
}

// ---------- 2. 여유 시간 설정 ----------
async function parseUtterance() {
  try {
    const r = await api("/api/intent", { method: "POST", body: JSON.stringify({ utterance: $("#utter").value, now: S.now }) });
    if (r.return_by) $("#returnBy").value = r.return_by;
    if (r.min_buffer_min != null) $("#buffer").value = r.min_buffer_min;
    if (r.max_drive_min != null) $("#maxDrive").value = r.max_drive_min;
    if (r.wants_work != null) $("#wantsWork").checked = r.wants_work;
    $$("input[name=kw]").forEach((c) => (c.checked = r.keywords.includes(c.value)));
    if (!r.return_by) return say("돌아올 시각을 알아듣지 못했어요. 시각을 직접 입력해 주세요.");
    const where = r.return_to_here ? "이 자리로 " : "";
    const work = r.wants_work === false ? "일감은 보지 않을게요" : r.wants_work ? "남는 시간에 일감도 찾아볼게요" : "일감 보기 여부를 골라 주세요";
    say(`${r.return_by}까지 ${where}돌아오고, ${work}. 내용을 확인한 뒤 시작을 눌러 주세요.`);
  } catch (e) { say(e.message); }
}

async function startWindow() {
  if (!S.lot) { showStep(1); return say("먼저 주차할 곳을 골라 주세요."); }
  const md = $("#maxDrive").value;
  try {
    const r = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        position: { lat: S.lot.lat, lng: S.lot.lng }, return_point: null,
        return_by: `${S.now.slice(0, 10)}T${$("#returnBy").value}:00`, now: S.now,
        min_buffer_min: Number($("#buffer").value), max_drive_min: md === "" ? null : Number(md),
        wants_work: $("#wantsWork").checked,
        radar_keywords: $$("input[name=kw]:checked").map((c) => c.value),
        driver: S.scenario.driver, consent_location: $("#consent").checked,
      }),
    });
    S.session = r.session_id; S.resting = false; S.lastAccept = null; S.returnBy = r.window.return_by;
    $("#guidance").innerHTML = "";
    say(`여유 시간 계획을 시작했어요. ${r.window.return_by}까지 ${r.window.available_min}분 남았어요.`);
    showStep(3);
    await loadRecs({ announce: false });
  } catch (e) { say(e.message); }
}

// ---------- 3. 추천 ----------
function timeBar(bd, available) {
  const go = bd.drive_to_site ?? bd.walk_to_site, back = bd.drive_back ?? bd.walk_back;
  const free = Math.max(available - bd.total, 0);
  const seg = (cls, v, label) => (v > 0 ? `<span class="${cls}" style="flex:${v}" title="${label} ${v}분">${label} ${v}</span>` : "");
  return `<div class="bar">${seg("go", go, "이동")}${seg("task", bd.task, "업무")}${seg("back", back, "복귀")}${seg("buf", bd.safety_buffer, "여유")}${seg("free", free, "남음")}</div>`;
}

async function loadRecs({ announce = true } = {}) {
  if (!S.session) return;
  if (!$("#gigs")) $("#panel3").innerHTML = S.panel3Html; // 주행 잠금 화면에서 복귀
  const q = new URLSearchParams({ now: S.now, gear: S.gear, speed_kmh: S.gear === "D" ? 30 : 0 });
  const r = await api(`/api/sessions/${S.session}/recommendations?${q}`);
  if (r.driving) {
    $("#panel3").innerHTML = `<div class="driving-lock">🚗 주행 중에는 일감을 보거나 수락할 수 없어요.<br><br><b>${esc(r.voice_brief)}</b></div>`;
    if (announce) say(r.voice_brief);
    return;
  }
  S.recs = r;
  const available = Math.max(r.remaining_min, 0);
  $("#recMsg").textContent = r.mode === "over" ? r.message : `${r.message} 돌아올 시각까지 ${available}분 남았어요.`;
  $("#chooseRest").textContent = S.resting ? "일감 다시 보기" : "쉬기";
  $("#gigs").innerHTML = S.resting ? "" : r.recommended.map((g) => `
    <div class="card">
      <div class="top"><span class="name">${esc(g.title)}</span><span class="big"><small>예상 순수익</small> ${won(g.net_profit)}</span></div>
      <div class="meta">${esc(g.partner)} · 보수 ${won(g.pay)} − 차량 비용 ${won(g.costs.vehicle)} − 주차비 ${won(g.costs.parking)} · 시간당 ${won(g.net_per_hour)}</div>
      ${timeBar(g.breakdown, available)}
      <div class="meta"><b>${g.finish_at}</b>에 복귀 (약속 시각보다 ${g.slack_min}분 일찍) · 업체 신뢰도 ${Math.round(g.trust * 100)}%</div>
      <div class="row"><button class="primary" data-accept="${g.gig_id}">수락하기</button><button data-decline="${g.gig_id}">거절</button></div>
    </div>`).join("");
  $("#gigsExcluded").innerHTML = r.excluded.map((g) => `<div class="card"><b>${esc(g.title)}</b><div class="meta">${g.reasons.map(esc).join(" / ")}</div></div>`).join("") || "<div class='meta'>없음</div>";
  $("#radar").innerHTML = r.radar.organic.map((p) => `
    <div class="card"><div class="top"><span class="name">${esc(p.name)}</span><span>걸어서 ${p.walk_min}분</span></div>
    <div class="meta">${p.keywords.map((k) => `<span class="tag">${esc(k)}</span>`).join("")} 영업 ${p.hours} · 출처: ${esc(p.source)}</div></div>`).join("") || "<div class='meta'>고른 항목에 맞는 곳이 근처에 없어요.</div>";
  $("#radarAds").innerHTML = r.radar.sponsored.length ? `<h3>광고·제휴</h3>` + r.radar.sponsored.map((p) => `
    <div class="card"><span class="tag ad">광고</span><b>${esc(p.name)}</b><div class="meta">걸어서 ${p.walk_min}분 · 출처: ${esc(p.source)}</div></div>`).join("") : "";
  $$("[data-accept]").forEach((b) => (b.onclick = () => accept(b.dataset.accept)));
  $$("[data-decline]").forEach((b) => (b.onclick = () => decline(b.dataset.decline)));
  if (announce && r.mode === "work" && !S.resting) say(r.recommended.length ? `${r.message} 물론 쉬셔도 괜찮아요.` : r.message);
  if (announce && r.mode === "over") say(r.message);
  else if (announce && available > 0 && available <= 10) say(`돌아갈 시각까지 ${available}분 남았어요. 슬슬 출발할 준비를 해 주세요.`);
  drawMap();
  renderAssignment();
}

async function decline(gigId) {
  try {
    await api(`/api/sessions/${S.session}/decline`, { method: "POST", body: JSON.stringify({ gig_id: gigId }) });
    say("거절했어요. 이 일감은 다시 추천하지 않을게요.");
    await loadRecs({ announce: false });
  } catch (e) { say(e.message); }
}

function toggleRest() {
  if (!S.session) return say("먼저 주차하고 여유 시간을 설정해 주세요.");
  S.resting = !S.resting;
  say(S.resting ? `편히 쉬세요. ${S.returnBy}에 돌아갈 시간이 되면 알려 드릴게요.` : "일감 추천을 다시 보여 드릴게요.");
  loadRecs({ announce: false });
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
    say(`수락했어요. ${w1.eta}쯤 업무지에 도착하고 ${w2.eta}쯤 이 자리로 돌아오도록 안내할게요.`);
    showStep(4);
    await loadRecs({ announce: false });
  } catch (e) { say(e.message); }
}

// ---------- 4. 진행 ----------
function renderAssignment() {
  const a = S.recs?.assignment;
  const st = a?.state;
  $("#startTask").disabled = st !== "accepted";
  $("#completeTask").disabled = st !== "in_progress";
  $("#cancelTask").disabled = !["accepted", "in_progress"].includes(st);
  if (!a) { $("#assignment").innerHTML = `<div class="notice">진행 중인 업무가 없어요.</div>`; return; }
  const ev = a.evaluation;
  const nav = S.lastAccept?.navigation;
  const cls = a.state === "cancelled" ? "bad" : a.state === "completed" ? "ok" : "warn";
  $("#assignment").innerHTML = `
    <div class="card"><div class="top"><span class="name">${esc(ev.title)}</span><span class="tag ${cls}">${STATE_KO[a.state] ?? a.state}</span></div>
    ${timeBar(ev.breakdown, ev.breakdown.total + ev.slack_min)}
    <div class="meta">${nav ? nav.waypoints.map((w) => `${esc(w.label)} ${w.eta}`).join(" → ") + ` · 약속 시각 ${nav.return_by}` : ""}</div>
    <div class="meta">예상 순수익 ${won(ev.net_profit)} · 길 안내: ${esc(nav?.provider ?? "내비게이션")}</div></div>`;
}

async function transition(action) {
  if (!S.session) return say("진행 중인 업무가 없어요.");
  try {
    await api(`/api/sessions/${S.session}/assignment/${action}`, { method: "POST" });
    say({ start: "업무를 시작해요. 돌아올 시각을 계속 확인할게요.", complete: "수고하셨어요. 돌아가는 길을 안내할게요.", cancel: "업무를 취소했어요. 조심히 돌아가세요." }[action]);
    await loadRecs({ announce: false });
  } catch (e) { say(e.message); }
}

async function sendEvent(type) {
  if (!S.session) return say("먼저 여유 시간 계획을 시작해 주세요.");
  try {
    const r = await api(`/api/sessions/${S.session}/events`, { method: "POST", body: JSON.stringify({ type, delay_min: type === "traffic_delay" ? 10 : 0, now: S.now }) });
    let html = r.guidance.map((g) => `<div class="notice">${esc(g)}</div>`).join("");
    if (r.alternatives) html += r.alternatives.map((l) => `<div class="card"><b>${esc(l.name)}</b><div class="meta">예상 요금 ${won(l.fee_estimate)} · 목적지까지 걸어서 ${l.walk_to_destination_min}분</div></div>`).join("");
    $("#guidance").innerHTML = html;
    say(r.guidance[0]);
    await loadRecs({ announce: false });
  } catch (e) { say(e.message); }
}

// ---------- 연결 ----------
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
  document.addEventListener("click", (e) => { if (e.target.id === "chooseRest") toggleRest(); });
  $("#resume").onclick = async () => {
    if (!S.session) return say("먼저 여유 시간 계획을 시작해 주세요.");
    await api(`/api/sessions/${S.session}/resume`, { method: "POST" });
    $("#guidance").innerHTML = "";
    say("일감 추천을 다시 시작했어요.");
    loadRecs({ announce: false });
  };
  $("#deleteSession").onclick = async () => {
    if (!S.session) return say("삭제할 이용 기록이 없어요.");
    await api(`/api/sessions/${S.session}`, { method: "DELETE" });
    S.session = null; S.recs = null; S.lastAccept = null; S.resting = false; S.lot = null;
    $("#panel3").innerHTML = S.panel3Html;
    $("#guidance").innerHTML = ""; renderAssignment();
    say("위치 정보와 이용 기록을 삭제했어요.");
    showStep(1); loadParking();
  };
  $("#tick").onclick = () => {
    const d = new Date(S.now); d.setMinutes(d.getMinutes() + 5);
    S.now = toIso(d); $("#clock").textContent = hhmm(S.now);
    loadRecs();
  };
  $("#toggleDrive").onclick = () => {
    S.gear = S.gear === "P" ? "D" : "P";
    const v = $("#vstate");
    v.textContent = S.gear === "P" ? "정차 중 (P)" : "주행 중 (D) · 30km/h";
    v.className = "pill " + (S.gear === "P" ? "parked" : "driving");
    if (!S.session) return say(S.gear === "P" ? "차를 세웠어요." : "주행 중에는 화면 조작을 줄여 주세요.");
    loadRecs();
  };
  setInterval(async () => { try { $("#audit").textContent = JSON.stringify(await api("/api/audit?limit=30"), null, 1); } catch (_) {} }, 3000);
  renderAssignment();
  await loadParking();
  say("안녕하세요. 목적지 근처 주차장을 비교해 봤어요.");
}
init();
