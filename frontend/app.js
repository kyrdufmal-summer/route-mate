// ROUTE MATE 차량 화면 — Pleos Connect 차량용 앱의 화면 흐름을 웹으로 재현
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const STAGES = ["park", "time", "pick", "go"];
const S = {
  stage: "park", now: null, scenario: null,
  lots: [], lotsExcluded: [], lot: null, showLotsExcluded: false,
  filters: { pickupOnly: true, receipt: false },
  plan: { returnBy: "17:55", wantsWork: true, keywords: [], buffer: 5, maxDrive: "", consent: true, heard: "", purpose: "pickup" },
  session: null, recs: null, driveBrief: null, gear: "P",
  lastAccept: null, resting: false, showGigsExcluded: false, guidance: [], alternatives: [],
  lastSpoken: "", alerts: [], live: [], enf: null, enfBase: 0, enfAt: 0, auto: null, left: "glance",
};
const PURPOSE = { pickup: ["아이 픽업", "🏫", "학원"], hospital: ["진료", "🏥", "병원"], other: ["약속", "📍", "목적지"] };

// ---------- 아이콘 ----------
const I = {
  logo: `<svg width="26" height="26" viewBox="0 0 26 26"><circle cx="13" cy="13" r="12" fill="#5b8cff"/><path d="M7 16c2-5 4-7 6-7s3 2 3 4-1 3 3 3" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round"/><circle cx="7" cy="16" r="1.8" fill="#fff"/><circle cx="19" cy="16" r="1.8" fill="#fff"/></svg>`,
  gear: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>`,
  replay: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>`,
  wave: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M5 10v4M9 7v10M13 5v14M17 8v8M21 11v2"/></svg>`,
  mic: `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/></svg>`,
  walk: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="13" cy="4" r="2"/><path d="m9 20 3-6 3 3v4M7 12l3-4 4 1 2 3"/></svg>`,
  car: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 17h14v-5l-2-5H7l-2 5z"/><circle cx="8" cy="17" r="2"/><circle cx="16" cy="17" r="2"/></svg>`,
  clock: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
  spot: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M10 16V8h3a2.5 2.5 0 0 1 0 5h-3"/></svg>`,
  coffee: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#34d3a0" stroke-width="2" stroke-linecap="round"><path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M17 11h1.5a2.5 2.5 0 0 1 0 5H17M8 3v3M12 3v3"/></svg>`,
  bigCar: `<svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#ffb84d" stroke-width="1.8" stroke-linecap="round"><path d="M5 17h14v-5l-2-5H7l-2 5z"/><circle cx="8" cy="17" r="2"/><circle cx="16" cy="17" r="2"/></svg>`,
};

// ---------- 공통 ----------
const pad = (n) => String(n).padStart(2, "0");
const toIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
const hhmm = (iso) => iso.slice(11, 16);
const won = (n) => (n == null ? "-" : n.toLocaleString("ko-KR") + "원");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clean = (s) => String(s).replace(/^\[샘플\]\s*/, "").replace(/^샘플\s*/, "");
const minutesUntil = (hm) => {
  const [h, m] = hm.split(":").map(Number); const [nh, nm] = hhmm(S.now).split(":").map(Number);
  return h * 60 + m - (nh * 60 + nm);
};
const shiftTime = (hm, d) => {
  const [h, m] = hm.split(":").map(Number); const t = Math.max(0, Math.min(23 * 60 + 55, h * 60 + m + d));
  return `${pad(Math.floor(t / 60))}:${pad(t % 60)}`;
};

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
  S.lastSpoken = text;
  $("#bubbleText").textContent = text;
  const av = $("#avatar");
  Voice.speak(text, { onstart: () => av.classList.add("talking"), onend: () => av.classList.remove("talking") });
  setTimeout(() => av.classList.remove("talking"), 12000);
}

function go(stage) { S.stage = stage; render(); $("#stage").scrollTop = 0; }

// ---------- 지도 ----------
const ROADS = [
  "M-10 140 C 120 150, 220 120, 540 160", "M-10 330 C 160 320, 300 350, 540 320", "M-10 470 C 180 480, 320 450, 540 490",
  "M120 -10 C 130 160, 100 360, 130 580", "M300 -10 C 290 200, 330 380, 310 580", "M440 -10 C 450 180, 420 400, 450 580",
];
function pin(x, y, color, glyph, size = 1) {
  const s = size;
  return `<g transform="translate(${x},${y}) scale(${s})"><path d="M0 0 C -10 -12 -14 -18 -14 -24 a14 14 0 1 1 28 0 c0 6 -4 12 -14 24z" fill="${color}" stroke="#0b1220" stroke-width="2"/><text x="0" y="-19" text-anchor="middle" font-size="13" font-weight="800" fill="#0b1220">${glyph}</text></g>`;
}
let placed = [];
function label(x, y, text, strong) {
  const w = Math.min(170, 12 + text.length * 11.5);
  let lx = x + 16, ly = y - 34;
  if (lx + w > 515) lx = x - 16 - w; // 오른쪽 끝이면 왼쪽에 붙인다
  // 다른 이름표와 겹치면 아래로 비켜 놓는다
  for (let tries = 0; tries < 6 && placed.some((b) => lx < b.x + b.w && lx + w > b.x && ly < b.y + 24 && ly + 24 > b.y); tries++) ly += 26;
  placed.push({ x: lx, y: ly, w });
  return `<g transform="translate(${lx},${ly})"><rect width="${w}" height="22" rx="11" fill="rgba(12,18,32,.85)"/><text x="10" y="15" font-size="12" font-weight="${strong ? 700 : 500}" fill="${strong ? "#eef2f8" : "#b6c2d6"}">${esc(text)}</text></g>`;
}
function drawMap() {
  if (S.left !== "map") return;
  const sc = S.scenario;
  const pts = [];
  const add = (lat, lng, kind, text, extra = {}) => pts.push({ lat, lng, kind, text, ...extra });
  add(sc.destination.lat, sc.destination.lng, "dest", "목적지");
  const showLots = S.stage === "park" || S.lot;
  if (showLots) (S.lot ? [S.lot] : S.lots).forEach((l, i) => add(l.lat, l.lng, "lot", clean(l.name).replace(/\s*\(.*\)/, ""), { best: i === 0 }));
  const asg = S.recs?.assignment;
  const active = asg && ["accepted", "in_progress"].includes(asg.state);
  if (active) add(asg.evaluation.lat, asg.evaluation.lng, "gig", "업무지");
  else if (S.stage === "pick" && !S.resting) (S.recs?.recommended || []).forEach((g) => add(g.lat, g.lng, "gig", clean(g.partner)));
  if (S.stage === "pick") [...(S.recs?.radar?.organic || []), ...(S.recs?.radar?.sponsored || [])].forEach((p) => add(p.lat, p.lng, "place", clean(p.name)));
  const car = S.lot ? { lat: S.lot.lat, lng: S.lot.lng } : sc.vehicle_position;

  const all = [...pts, { ...car }];
  const lats = all.map((p) => p.lat), lngs = all.map((p) => p.lng);
  const span = Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lngs) - Math.min(...lngs), 0.003) * 1.25;
  const cx = (Math.min(...lngs) + Math.max(...lngs)) / 2, cy = (Math.min(...lats) + Math.max(...lats)) / 2;
  const X = (lng) => 260 + ((lng - cx) / span) * 440;
  const Y = (lat) => 300 - ((lat - cy) / span) * 440;

  placed = [];
  let svg = `<defs><filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
  // 블록과 도로 (장식용 간략 지도)
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) svg += `<rect x="${c * 145 - 20}" y="${r * 160 - 10}" width="110" height="120" rx="14" fill="#131e33"/>`;
  svg += `<rect x="330" y="20" width="120" height="90" rx="20" fill="#12261f"/>`; // 공원
  ROADS.forEach((d) => (svg += `<path d="${d}" stroke="#1d2a44" stroke-width="16" fill="none" stroke-linecap="round"/>`));
  if (active && S.lastAccept) {
    const [w1, w2] = S.lastAccept.navigation.waypoints;
    const d = `M${X(car.lng)} ${Y(car.lat)} L${X(w1.lng)} ${Y(w1.lat)} L${X(w2.lng)} ${Y(w2.lat)}`;
    svg += `<path d="${d}" stroke="#5b8cff" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)" opacity=".9"/>`;
  }
  const order = { place: 0, lot: 1, gig: 2, dest: 3 };
  // 이름표는 중요한 것(목적지 → 일감 → 주차장 → 생활정보)부터 자리를 잡는다
  const labels = [];
  pts.sort((a, b) => order[a.kind] - order[b.kind]).forEach((p) => {
    const x = X(p.lng), y = Y(p.lat);
    if (p.kind === "place") { svg += `<circle cx="${x}" cy="${y}" r="7" fill="#ffd66b" stroke="#0b1220" stroke-width="2"/>`; labels.push([x - 8, y + 26, p.text, false, 0]); return; }
    const style = { lot: ["#5b8cff", "P"], gig: ["#b48cff", "★"], dest: ["#ff8fab", "⚑"] }[p.kind];
    svg += pin(x, y, style[0], style[1], p.best || p.kind === "dest" ? 1.1 : 0.9);
    labels.push([x, y, p.text, p.kind === "dest" || p.best, order[p.kind] + (p.best ? 0.5 : 0)]);
  });
  svg += `<g transform="translate(${X(car.lng)},${Y(car.lat)})"><circle r="16" fill="rgba(91,140,255,.25)"/><circle r="10" fill="#fff" stroke="#5b8cff" stroke-width="3"/></g>`;
  labels.sort((a, b) => b[4] - a[4]).forEach(([x, y, t, strong]) => (svg += label(x, y, t, strong)));
  $("#map").innerHTML = svg;
  $("#mapCaption").textContent = { park: "목적지 주변 주차장", time: S.lot ? clean(S.lot.name) + "에 주차 중" : "", pick: "걸어서 또는 차로 가까운 곳", go: "업무지를 거쳐 돌아오는 길" }[S.stage];
}

// ---------- 상단 ----------
function renderTop() {
  $("#clock").textContent = hhmm(S.now);
  const g = $("#gearChip");
  g.className = "chip gear " + (S.gear === "P" ? "parked" : "driving");
  g.textContent = S.gear === "P" ? "정차 중" : "주행 중";
  const cd = $("#countdown");
  if (S.session && S.plan.returnBy) {
    const left = minutesUntil(S.plan.returnBy);
    cd.classList.remove("hidden");
    cd.classList.toggle("warn", left <= 10);
    cd.textContent = left > 0 ? `${S.plan.returnBy} 복귀까지 ${left}분` : "복귀할 시간이에요";
  } else cd.classList.add("hidden");
  const idx = STAGES.indexOf(S.stage);
  $$("#progress li").forEach((li, i) => { li.className = i < idx ? "done" : i === idx ? "now" : ""; });
}

// ---------- 1. 주차 ----------
async function loadParking() {
  const sc = S.scenario;
  const r = await api("/api/parking/search", {
    method: "POST",
    body: JSON.stringify({ origin: sc.vehicle_position, destination: sc.destination, now: S.now, stay_until: sc.pickup_end,
      vehicle: sc.vehicle, pickup_only: S.filters.pickupOnly, has_academy_receipt: S.filters.receipt }),
  });
  S.lots = r.recommended; S.lotsExcluded = r.excluded;
}

function renderPark() {
  const lots = S.lots;
  return `
    <h2>목적지 근처 주차장 ${lots.length}곳</h2>
    <p class="lead">${hhmm(S.now)}에 도착해 ${hhmm(S.scenario.pickup_end)}까지 머무는 기준으로 비교했어요.</p>
    <div class="chips">
      <button class="chip-toggle ${S.filters.pickupOnly ? "on" : ""}" data-filter="pickupOnly">합법 승하차 가능한 곳만</button>
      <button class="chip-toggle ${S.filters.receipt ? "on" : ""}" data-filter="receipt">학원 영수증 있어요</button>
    </div>
    ${lots.map((l, i) => `
      <div class="card ${i === 0 ? "best" : ""}">
        <div class="head">
          <div>
            ${i === 0 ? '<span class="badge blue">가장 가까워요</span>' : ""}
            ${l.pickup_zone_legal ? '<span class="badge mint">합법 승하차</span>' : ""}
            ${l.discounts_need_check.length ? '<span class="badge amber">할인 확인 필요</span>' : ""}
            <div class="title">${esc(clean(l.name))}</div>
          </div>
          <div class="price">${won(l.fee_estimate)}<small>예상 요금</small></div>
        </div>
        <div class="facts">
          <span>${I.walk} 목적지까지 걸어서 <b>${l.walk_to_destination_min}분</b></span>
          <span>${I.car} 차로 <b>${l.drive_min}분</b></span>
          <span>${I.spot} 빈자리 <b>${l.realtime_spaces.value != null ? l.realtime_spaces.value + "면" : "미확인"}</b></span>
        </div>
        <div class="row">
          <button class="btn ${i === 0 ? "primary" : ""}" data-park="${i}">여기에 주차할게요</button>
        </div>
        <details class="more"><summary></summary><div class="detail">
          입구: ${esc(l.entrance)}<br>
          운영 시간: ${l.hours} · ${l.stay_min}분 주차 기준<br>
          ${l.discounts_applied.map((d) => `할인 적용: ${esc(d)}<br>`).join("")}
          ${l.discounts_need_check.map((d) => `확인이 필요한 할인: ${esc(d)} → 확인되면 ${won(l.fee_if_pending_discount_confirmed)}<br>`).join("")}
          발레파킹: ${l.valet.value == null ? "미확인" : l.valet.value ? "가능" : "불가"}<br>
          정보 출처: ${esc(l.source)} · ${l.updated_at.slice(5, 16).replace("T", " ")} 갱신 (${l.data_freshness})
        </div></details>
      </div>`).join("") || `<div class="card">조건에 맞는 주차장이 없어요. 필터를 바꿔 보세요.</div>`}
    ${S.lotsExcluded.length ? `<button class="link-more" data-toggle="lotsExcluded">${S.showLotsExcluded ? "접기" : `추천하지 않은 ${S.lotsExcluded.length}곳과 이유 보기`}</button>` : ""}
    ${S.showLotsExcluded ? `<div class="excluded-list">${S.lotsExcluded.map((x) => `<div class="card"><div class="title">${esc(clean(x.name))}</div><div class="why">${x.reasons.map(esc).join(" · ")}</div></div>`).join("")}</div>` : ""}
  `;
}

// ---------- 2. 시간 설정 ----------
const KEYWORDS = ["약국", "반찬가게", "아이 동반 식당", "주차 편한 상점", "카페"];
function renderTime() {
  const p = S.plan;
  const left = minutesUntil(p.returnBy);
  return `
    <h2>언제까지 돌아와야 하나요?</h2>
    <p class="lead">${S.lot ? esc(clean(S.lot.name)) + "에 세웠어요. " : ""}무엇을 기다리시는지, 언제까지 오면 되는지 알려 주세요.</p>
    <div class="purpose">${Object.entries(PURPOSE).map(([k, v]) => `<button class="chip-toggle ${p.purpose === k ? "on" : ""}" data-purpose="${k}">${v[1]} ${v[0]}</button>`).join("")}</div>
    <div class="time-picker">
      <button class="round" data-shift="-5" aria-label="5분 앞으로">−</button>
      <div><div class="t">${p.returnBy}</div><div class="sub">${left > 0 ? `지금부터 ${left}분` : "지금보다 늦은 시각을 골라 주세요"}</div></div>
      <button class="round" data-shift="5" aria-label="5분 뒤로">+</button>
    </div>
    <div class="voice-ask">
      <button class="mic" id="mic" aria-label="말로 설정하기">${I.mic}</button>
      <div class="q">${p.heard ? `<b>“${esc(p.heard)}”</b><br>이렇게 이해했어요. 아래 내용을 확인해 주세요.` : "버튼을 누르고 말해 보세요.<br><b>“17:55까지 여기로 돌아와야 해. 시간 남으면 가까운 일도 볼래.”</b>"}</div>
    </div>
    <div class="segmented">
      <button class="${!p.wantsWork ? "on restful" : ""}" data-work="0">쉬면서 기다릴게요<small>주차·쉼터·생활정보만 안내</small></button>
      <button class="${p.wantsWork ? "on" : ""}" data-work="1">가까운 일도 볼래요<small>돌아올 시각 안에 끝나는 일만</small></button>
    </div>
    <h4>근처에서 찾아볼 곳</h4>
    <div class="chips">${KEYWORDS.map((k) => `<button class="chip-toggle ${p.keywords.includes(k) ? "on" : ""}" data-kw="${k}">${k}</button>`).join("")}</div>
    <details class="adv"><summary>세부 설정</summary>
      <label>돌아오기 전 최소 여유 <span><input type="number" id="buffer" min="0" max="60" value="${p.buffer}"> 분</span></label>
      <label>운전 시간 상한 <span><input type="number" id="maxDrive" min="0" placeholder="제한 없음" value="${p.maxDrive}"> 분</span></label>
      <label>말 대신 글로 입력 <span><input id="utterText" style="width:220px;text-align:left" placeholder="예: 6시까지 돌아올게"></span></label>
    </details>
    <label class="consent"><input type="checkbox" id="consent" ${p.consent ? "checked" : ""}> 이번 이용 동안 위치 정보를 쓰는 데 동의해요. 이용이 끝나면 바로 지워요.</label>
    <div class="sticky-cta"><button class="btn primary big wide" id="startPlan" ${left > 0 ? "" : "disabled"}>${left > 0 ? `${p.returnBy}까지 ${left}분 계획 시작` : "돌아올 시각을 다시 골라 주세요"}</button></div>
  `;
}

async function listen(textOverride) {
  // 실제 차량: Pleos STT SDK. 시연: 미리 준비한 발화를 인식한 것으로 처리
  const utter = textOverride || S.scenario.utterance;
  try {
    const r = await api("/api/intent", { method: "POST", body: JSON.stringify({ utterance: utter, now: S.now }) });
    S.plan.heard = utter;
    if (r.return_by) S.plan.returnBy = r.return_by;
    if (r.min_buffer_min != null) S.plan.buffer = r.min_buffer_min;
    if (r.max_drive_min != null) S.plan.maxDrive = r.max_drive_min;
    if (r.wants_work != null) S.plan.wantsWork = r.wants_work;
    if (r.keywords.length) S.plan.keywords = r.keywords;
    render();
    if (!r.return_by) return say("시간을 못 알아들었어요. 화면에서 골라 주세요.");
    const where = r.return_to_here ? "여기로 " : "";
    say(r.wants_work === false
      ? `${r.return_by}까지 ${where}오시는 거죠? 그때까지 쉬시면 돼요. 맞으면 시작 눌러 주세요.`
      : `${r.return_by}까지 ${where}오시는 거죠? 그 안에 끝나는 일도 같이 찾아볼게요. 맞으면 시작 눌러 주세요.`);
  } catch (e) { say(e.message); }
}

async function startPlan() {
  const p = S.plan;
  p.buffer = Number($("#buffer")?.value ?? p.buffer);
  p.maxDrive = $("#maxDrive")?.value ?? p.maxDrive;
  p.consent = $("#consent")?.checked ?? p.consent;
  try {
    const r = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        position: { lat: S.lot.lat, lng: S.lot.lng }, return_point: null,
        return_by: `${S.now.slice(0, 10)}T${p.returnBy}:00`, now: S.now,
        min_buffer_min: p.buffer, max_drive_min: p.maxDrive === "" ? null : Number(p.maxDrive),
        wants_work: p.wantsWork, radar_keywords: p.keywords, driver: S.scenario.driver, consent_location: p.consent, purpose: p.purpose,
      }),
    });
    S.session = r.session_id; S.resting = !p.wantsWork;
    try { localStorage.setItem("routemate.session", r.session_id); } catch (_) {} S.lastAccept = null; S.guidance = []; S.alternatives = [];
    await loadRecs();
    go("pick");
    const n = S.recs?.recommended?.length || 0;
    say(p.wantsWork
      ? (n ? `${r.window.available_min}분 있어요. 시간 맞는 일이 ${n}개 있는데, 그냥 쉬셔도 돼요.` : "지금은 시간 맞는 일이 없네요. 편히 쉬세요.")
      : "네, 쉬세요. 나갈 때 되면 말씀드릴게요.");
  } catch (e) { say(e.message); }
}

// ---------- 3. 선택 ----------
async function loadRecs() {
  if (!S.session) return;
  const q = new URLSearchParams({ now: S.now, gear: S.gear, speed_kmh: S.gear === "D" ? 30 : 0 });
  const r = await api(`/api/sessions/${S.session}/recommendations?${q}`);
  if (r.driving) { S.driveBrief = r.voice_brief; return; }
  S.driveBrief = null; S.recs = r;
}

function ring(left, total) {
  const R = 36, C = 2 * Math.PI * R, ratio = total > 0 ? Math.max(0, Math.min(1, left / total)) : 0;
  return `<div class="ring"><svg width="84" height="84"><circle cx="42" cy="42" r="${R}" stroke="#22324f" stroke-width="8" fill="none"/>
    <circle cx="42" cy="42" r="${R}" stroke="${left <= 10 ? "#ffb84d" : "#5b8cff"}" stroke-width="8" fill="none" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - ratio)}"/></svg>
    <div class="v"><div>${Math.max(left, 0)}<small>분 남음</small></div></div></div>`;
}

function bar(bd, total) {
  const go = bd.drive_to_site ?? bd.walk_to_site, back = bd.drive_back ?? bd.walk_back;
  const free = Math.max(total - bd.total, 0);
  const seg = (c, v) => (v > 0 ? `<i class="${c}" style="flex:${v}"></i>` : "");
  return `<div class="timeline">${seg("go", go)}${seg("task", bd.task)}${seg("back", back)}${seg("buf", bd.safety_buffer)}${seg("free", free)}</div>`;
}

function renderPick() {
  const r = S.recs;
  if (!r) return `<p class="lead">잠시만요, 불러오고 있어요.</p>`;
  const left = minutesUntil(S.plan.returnBy);
  const total = Math.max(r.window?.available_min ?? left, left, 1);
  const gigs = S.resting ? [] : r.recommended;
  const onFoot = (g) => g.breakdown.walk_to_site != null;

  let top = "";
  if (r.mode === "over") top = `<div class="card"><div class="title">돌아갈 시간이에요</div><div class="facts">새 일감은 추천하지 않아요. 조심히 복귀하세요.</div></div>`;
  if (r.mode === "paused") top = `<div class="notice">${esc(r.message)}</div>`;
  if (r.mode === "assigned") top = `<div class="card best"><div class="title">진행 중인 업무가 있어요</div><div class="facts">${esc(clean(r.assignment.evaluation.title))}</div><button class="btn primary" data-goto="go">진행 화면 보기</button></div>`;

  const restCard = `
    <div class="card rest">
      <div class="head"><div><span class="badge mint">언제든 괜찮아요</span><div class="title">${S.resting ? "편히 쉬는 중이에요" : "잠시 쉬기"}</div></div>${I.coffee}</div>
      <div class="facts">${S.resting ? `${S.plan.returnBy}에 맞춰 출발할 때가 되면 알려 드릴게요.` : "일감을 고르지 않아도 돼요. 돌아올 시각만 챙겨 드릴게요."}</div>
      <button class="btn ${S.resting ? "ghost" : "mint"}" id="restToggle">${S.resting ? "가까운 일감 다시 보기" : "쉴게요"}</button>
    </div>`;

  const gigCards = gigs.map((g, i) => `
    <div class="card ${i === 0 ? "best" : ""}">
      <div class="head">
        <div><span class="badge gray">샘플</span>${i === 0 ? '<span class="badge blue">시간 대비 가장 좋아요</span>' : ""}<div class="title">${esc(clean(g.title))}</div></div>
        <div class="price plus">+${won(g.net_profit)}<small>예상 순수익</small></div>
      </div>
      <div class="facts">
        <span>${I.clock} <b>${g.finish_at}</b> 복귀</span>
        <span>약속보다 <b>${g.slack_min}분</b> 여유</span>
        <span>${onFoot(g) ? I.walk + " 걸어서" : I.car + " 차로"} <b>${g.breakdown.drive_to_site ?? g.breakdown.walk_to_site}분</b> · 업무 <b>${g.breakdown.task}분</b></span>
      </div>
      ${bar(g.breakdown, total)}
      <div class="row" style="margin-top:12px">
        <button class="btn ${i === 0 ? "primary" : ""}" data-accept="${g.gig_id}">수락하기</button>
        <button class="btn ghost" data-decline="${g.gig_id}">괜찮아요</button>
      </div>
      <details class="more"><summary></summary><div class="detail">
        업체: ${esc(g.partner)} (신뢰도 ${Math.round(g.trust * 100)}%)<br>
        보수 ${won(g.pay)} − 차량 비용 ${won(g.costs.vehicle)} − 주차비 ${won(g.costs.parking)} = ${won(g.net_profit)}<br>
        시간당 약 ${won(g.net_per_hour)} · 안전 여유 ${g.breakdown.safety_buffer}분 포함
      </div></details>
    </div>`).join("");

  const radar = r.radar ? [...r.radar.organic.map((p) => ({ ...p, ad: false })), ...r.radar.sponsored.map((p) => ({ ...p, ad: true }))] : [];
  const excluded = r.excluded || [];

  return `
    <div class="ring-row">
      ${ring(left, total)}
      <div><h2>${left > 0 ? `${S.plan.returnBy}까지 ${left}분 있어요` : "돌아갈 시간이에요"}</h2>
      <p class="lead" style="margin:0">${S.resting ? "쉬는 동안 근처 생활정보만 알려 드릴게요." : "쉬어도 좋고, 시간 안에 끝나는 일을 골라도 좋아요."}</p></div>
    </div>
    ${top}
    ${r.mode !== "over" ? restCard : ""}
    ${gigCards}
    ${!S.resting && r.mode === "work" && !gigs.length ? `<div class="card"><div class="title">지금은 맞는 일감이 없어요</div><div class="facts">돌아올 시각 안에 끝나는 일이 생기면 알려 드릴게요.</div></div>` : ""}
    ${gigs.length ? `<div class="legend-line"><span><i style="background:#5b8cff"></i>이동</span><span><i style="background:#b48cff"></i>업무</span><span><i style="background:#8fb3ff"></i>복귀</span><span><i style="background:#34d3a0"></i>안전 여유</span><span><i style="background:#2a3a58"></i>남는 시간</span></div>` : ""}
    ${!S.resting && excluded.length ? `<button class="link-more" data-toggle="gigsExcluded">${S.showGigsExcluded ? "접기" : `추천하지 않은 일감 ${excluded.length}건과 이유 보기`}</button>` : ""}
    ${S.showGigsExcluded && !S.resting ? `<div class="excluded-list">${excluded.map((g) => `<div class="card"><div class="title">${esc(clean(g.title))}</div><div class="why">${g.reasons.map(esc).join(" · ")}</div></div>`).join("")}</div>` : ""}
    ${radar.length ? `<h4>근처에 들를 만한 곳</h4><div class="hscroll">${radar.map((p) => `
      <div class="place">${p.ad ? '<span class="badge ad">광고</span>' : p.keywords.map((k) => `<span class="badge gray">${esc(k)}</span>`).join("")}
        <div class="n">${esc(clean(p.name))}</div><div class="m">걸어서 ${p.walk_min}분 · ${p.hours}</div></div>`).join("")}</div>` : ""}
  `;
}

async function accept(gigId) {
  const key = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  try {
    const r = await api(`/api/sessions/${S.session}/accept`, {
      method: "POST", headers: { "Idempotency-Key": key },
      body: JSON.stringify({ gig_id: gigId, now: S.now, vehicle_state: { gear: S.gear, speed_kmh: S.gear === "D" ? 30 : 0 } }),
    });
    S.lastAccept = r; S.guidance = []; S.alternatives = [];
    await loadRecs();
    go("go");
    const [w1, w2] = r.navigation.waypoints;
    const shop = clean(S.recs?.assignment?.evaluation?.partner || "").replace("제휴 ", "");
    say(`${shop} 일 잡았어요. ${w1.eta}쯤 도착하고, ${w2.eta}이면 여기로 돌아와요.`);
  } catch (e) { say(e.message); }
}

async function decline(gigId) {
  try {
    await api(`/api/sessions/${S.session}/decline`, { method: "POST", body: JSON.stringify({ gig_id: gigId }) });
    await loadRecs(); render();
    say("네, 이건 다시 안 띄울게요.");
  } catch (e) { say(e.message); }
}

// ---------- 4. 진행 ----------
function renderGo() {
  const a = S.recs?.assignment;
  const notes = S.guidance.map((g) => `<div class="notice">${esc(g)}</div>`).join("")
    + S.alternatives.map((l) => `<div class="card"><div class="head"><div class="title">${esc(clean(l.name))}</div><div class="price">${won(l.fee_estimate)}<small>예상 요금</small></div></div><div class="facts"><span>${I.walk} 목적지까지 걸어서 <b>${l.walk_to_destination_min}분</b></span></div></div>`).join("");
  if (!a) return `<h2>진행 중인 업무가 없어요</h2>${notes}<button class="btn primary" data-goto="pick">선택 화면으로</button>`;
  const ev = a.evaluation, nav = S.lastAccept?.navigation;
  if (a.state === "completed") return `
    <div class="card done-card"><div class="title">수고하셨어요!</div><div class="amt">+${won(ev.net_profit)}</div>
    <div class="facts" style="justify-content:center">예상 순수익이에요. ${ev.finish_at}까지 복귀 지점으로 돌아가세요.</div>
    <button class="btn primary" data-goto="pick">남은 시간 다시 보기</button></div>${notes}`;
  if (a.state === "cancelled") return `<h2>업무를 취소했어요</h2><p class="lead">복귀 지점으로 안전하게 돌아가세요.</p>${notes}<button class="btn" data-goto="pick">선택 화면으로</button>`;
  const step = a.state === "accepted" ? 0 : 1;
  const bd = ev.breakdown;
  // 실시간 상황으로 늘어난 시간을 도착 예정에 반영해 보여 준다
  const late = delayNow(a);
  const adj = (hm, d) => (d ? `<s style="opacity:.5">${hm}</s> → <b style="color:var(--red)">${shiftTime(hm, d)}</b>` : hm);
  const items = [
    ["업무지로 이동", nav?.waypoints[0].eta ?? ""],
    [`업무 진행 (${bd.task}분)`, ""],
    ["복귀 지점 도착", adj(ev.finish_at, late)],
    ["약속 시각", S.plan.returnBy],
  ];
  return `
    <h2>${esc(clean(ev.title))}</h2>
    <p class="lead">예상 순수익 ${won(ev.net_profit)} · ${ev.slack_min - late >= 0 ? `약속 시각보다 ${ev.slack_min - late}분 일찍 돌아와요.` : `지금 상황이면 ${late - ev.slack_min}분 늦어요.`}</p>
    <ol class="steps-v">${items.map(([t, w], i) => `<li class="${i < step ? "done" : i === step ? "now" : ""}"><span>${t}</span><span class="when">${w}</span></li>`).join("")}</ol>
    ${notes}
    <div class="row">
      ${a.state === "accepted" ? `<button class="btn primary big" data-act="start">도착했어요, 업무 시작</button>` : `<button class="btn primary big" data-act="complete">업무를 마쳤어요</button>`}
      <button class="btn ghost" data-act="cancel">취소하고 돌아가기</button>
    </div>
    <p class="lead" style="margin-top:12px">길 안내: ${esc(nav?.provider ?? "내비게이션")}</p>`;
}

async function act(action) {
  try {
    await api(`/api/sessions/${S.session}/assignment/${action}`, { method: "POST" });
    if (action !== "start") { S.guidance = []; S.alternatives = []; }
    await loadRecs(); render();
    say({ start: "일 시작하세요. 시간은 제가 볼게요.", complete: "수고하셨어요. 이제 돌아오시면 돼요.", cancel: "취소했어요. 천천히 돌아오세요." }[action]);
  } catch (e) { say(e.message); }
}

// ---------- 주행 잠금 ----------
function renderDriveLock() {
  return `<div class="drive-lock"><div><div class="big-icon">${I.bigCar}</div>
    <h2>운전에 집중해 주세요</h2><p>주행 중에는 화면 조작을 줄이고 음성으로 알려 드려요.</p>
    ${S.driveBrief ? `<p><b>${esc(S.driveBrief)}</b></p>` : ""}</div></div>`;
}

// ---------- 그리기 ----------
function render() {
  renderTop();
  const locked = S.gear === "D" && ["time", "pick"].includes(S.stage);
  $("#stage").innerHTML = renderAlerts() + (locked ? renderDriveLock() : { park: renderPark, time: renderTime, pick: renderPick, go: renderGo }[S.stage]());
  renderGlance();
  drawMap();
}

// 이벤트 위임: 다시 그려도 핸들러를 다시 붙일 필요가 없다
document.addEventListener("click", async (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  const d = t.dataset;
  if (d.filter) { S.filters[d.filter] = !S.filters[d.filter]; await loadParking(); render(); return; }
  if (d.park) {
    S.lot = S.lots[Number(d.park)];
    go("time");
    say(`${clean(S.lot.name).replace(/\s*\(.*\)/, "")}에 세우셨네요. 몇 시까지 돌아오면 될까요?`);
    return;
  }
  if (d.toggle === "lotsExcluded") { S.showLotsExcluded = !S.showLotsExcluded; render(); return; }
  if (d.toggle === "gigsExcluded") { S.showGigsExcluded = !S.showGigsExcluded; render(); return; }
  if (d.shift) { S.plan.returnBy = shiftTime(S.plan.returnBy, Number(d.shift)); render(); return; }
  if (d.work) { S.plan.wantsWork = d.work === "1"; render(); return; }
  if (d.kw) { const k = S.plan.keywords; S.plan.keywords = k.includes(d.kw) ? k.filter((x) => x !== d.kw) : [...k, d.kw]; render(); return; }
  if (d.purpose) { S.plan.purpose = d.purpose; render(); return; }
  if (d.left) { S.left = d.left; $$(".left-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.left === d.left));
    $("#glance").classList.toggle("hidden", d.left !== "glance"); $("#mapBox").classList.toggle("hidden", d.left !== "map"); render(); return; }
  if (d.alertAct) return alertAction(Number(d.alertIdx), d.alertAct, Number(d.minutes || 0));
  if (d.accept) return accept(d.accept);
  if (d.decline) return decline(d.decline);
  if (d.act) return act(d.act);
  if (d.goto) return go(d.goto);
  switch (t.id) {
    case "mic": {
      const typed = $("#utterText")?.value.trim();
      return listen(typed || null);
    }
    case "startPlan": return startPlan();
    case "restToggle":
      S.resting = !S.resting; render();
      return say(S.resting ? "네, 쉬세요. 나갈 때 되면 말씀드릴게요." : "네, 시간 맞는 일 다시 보여 드릴게요.");
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "consent") S.plan.consent = e.target.checked;
  if (e.target.id === "buffer") S.plan.buffer = Number(e.target.value);
  if (e.target.id === "maxDrive") S.plan.maxDrive = e.target.value;
});

// ---------- 설정 ----------
function openSettings(open) {
  $("#settings").classList.toggle("hidden", !open);
  $("#sheetBackdrop").classList.toggle("hidden", !open);
}
function setupSettings() {
  $("#openSettings").innerHTML = I.gear;
  $("#replay").innerHTML = I.replay;
  $("#avatar").innerHTML = I.wave;
  $("#logoMark").innerHTML = I.logo;
  $("#openSettings").onclick = () => openSettings(true);
  $("#closeSettings").onclick = () => openSettings(false);
  $("#sheetBackdrop").onclick = () => openSettings(false);
  $("#replay").onclick = () => S.lastSpoken && say(S.lastSpoken);
  const on = $("#voiceOn"), sel = $("#voiceSelect"), rate = $("#voiceRate");
  on.checked = Voice.prefs.on; rate.value = Voice.prefs.rate;
  const rateText = (v) => (v < 0.93 ? "느리게" : v > 1.12 ? "빠르게" : "보통");
  $("#rateLabel").textContent = rateText(Number(rate.value));
  on.onchange = () => { Voice.set({ on: on.checked }); if (!on.checked) Voice.stop(); };
  rate.oninput = () => { Voice.set({ rate: Number(rate.value) }); $("#rateLabel").textContent = rateText(Number(rate.value)); };
  sel.onchange = () => { Voice.set({ name: sel.value }); updateHint(); };
  $("#voiceTest").onclick = () => say("5시 55분까지 여기로 돌아오시면 돼요. 길이 막히면 제가 먼저 말씀드릴게요.");
  function updateHint() {
    const v = Voice.current();
    $("#voiceHint").textContent = !v ? "이 브라우저에는 한국어 음성이 없어요. 화면 문구로만 안내해요."
      : Voice.isNatural(v) ? "자연스러운 목소리를 쓰고 있어요."
      : "지금 브라우저에는 기계음에 가까운 기본 음성만 있어요. Microsoft Edge나 Chrome에서 열면 더 자연스러운 목소리가 자동으로 선택돼요.";
  }
  Voice.onVoicesChanged((voices) => {
    const cur = Voice.current();
    sel.innerHTML = voices.map((v) => `<option value="${esc(v.name)}" ${cur && v.name === cur.name ? "selected" : ""}>${esc(v.name.replace(/Microsoft |Online |\(Natural\)| - Korean \(Korea\)| - Korean \(Korean\)/g, "").trim())}${Voice.isNatural(v) ? " · 자연스러운 음성" : " · 기본 음성"}</option>`).join("") || "<option>한국어 음성 없음</option>";
    updateHint();
  });
  $("#deleteSession").onclick = async () => { await restart(); openSettings(false); say("위치 정보랑 기록, 다 지웠어요."); };
}

// ---------- 시연 도구 ----------
async function restart() {
  if (S.session) { try { await api(`/api/sessions/${S.session}`, { method: "DELETE" }); } catch (_) {} }
  try { localStorage.removeItem("routemate.session"); } catch (_) {}
  try { await api("/api/demo/incidents", { method: "DELETE" }); } catch (_) {}
  Object.assign(S, { stage: "park", lot: null, session: null, recs: null, driveBrief: null, lastAccept: null, resting: false,
    guidance: [], alternatives: [], showLotsExcluded: false, showGigsExcluded: false, now: S.scenario.now,
    plan: { returnBy: "17:55", wantsWork: true, keywords: [], buffer: 5, maxDrive: "", consent: true, heard: "", purpose: "pickup" },
    alerts: [], live: [] });
  stopAuto();
  await loadParking(); render();
}

function setupDemoTools() {
  $("#tick").onclick = () => advance(5);
  $("#autoplay").onclick = () => toggleAuto();
  $$("[data-incident]").forEach((b) => (b.onclick = async () => {
    await api(`/api/demo/incidents${S.session ? `?sid=${S.session}` : ""}`, { method: "POST", body: JSON.stringify({ type: b.dataset.incident, now: S.now, minutes: 15 }) });
    if (!S.session) return say("상황을 만들었어요. 계획을 시작하면 바로 반영돼요.");
    await loadRecs(); await pollSituation();
  }));
  $("#toggleDrive").onclick = async () => {
    S.gear = S.gear === "P" ? "D" : "P";
    await loadRecs(); render();
    if (S.gear === "D") say(S.driveBrief || "운전하세요. 필요한 건 말로 알려 드릴게요.");
    else say("차 세우셨네요. 이제 화면 보셔도 돼요.");
  };
  $$("[data-event]").forEach((b) => (b.onclick = async () => {
    if (!S.session) return say("먼저 돌아올 시각을 정하고 계획을 시작해 주세요.");
    try {
      const r = await api(`/api/sessions/${S.session}/events`, { method: "POST", body: JSON.stringify({ type: b.dataset.event, delay_min: b.dataset.event === "traffic_delay" ? 10 : 0, now: S.now }) });
      S.guidance = r.guidance; S.alternatives = r.alternatives || [];
      await loadRecs();
      go(S.recs?.assignment ? "go" : "pick");
      say(r.guidance[0]);
    } catch (e) { say(e.message); }
  }));
  $("#resume").onclick = async () => {
    if (!S.session) return say("먼저 계획을 시작해 주세요.");
    await api(`/api/sessions/${S.session}/resume`, { method: "POST" });
    S.guidance = []; S.alternatives = [];
    await loadRecs(); render();
    say("다시 시간 맞는 일 찾아볼게요.");
  };
  $("#restart").onclick = async () => { await restart(); say("처음부터 다시 할게요."); };
  setInterval(async () => { try { $("#audit").textContent = JSON.stringify(await api("/api/audit?limit=30"), null, 1); } catch (_) {} }, 3000);
}

// 진행 중인 일의 경로에 걸린 실시간 지연(분). 걸어서 하는 일은 교통 영향 없음
function delayNow(a) {
  const bd = a.evaluation.breakdown;
  if (bd.walk_to_site != null) return 0;
  const known = bd.traffic_delay || 0;
  const d = S.live.filter((x) => x.mine && x.type !== "weather").reduce((s, x) => s + x.delay_min, 0) + (S.live.some((x) => x.type === "weather") ? 3 : 0);
  return Math.max(0, d - known);
}

// ---------- 한눈에 보기 ----------
const LIVE_ICON = { accident: "🚨", weather: "🌧", school_rush: "🚗", congestion: "🚗" };
const shopOf = (s) => clean(s || "").replace("제휴 ", "");
const lotShort = (l) => clean(l.name).replace(/\s*\(.*\)/, "");

function node(ic, t, s, me) {
  return `<div class="node ${me ? "me" : ""}"><div class="ic">${ic}</div><div class="t">${esc(t)}</div>${s ? `<div class="s">${esc(s)}</div>` : ""}</div>`;
}
function link(text, { walk = false, bad = "" } = {}) {
  return `<div class="link ${walk ? "walk" : ""} ${bad ? "bad" : ""}"><div class="line"></div><div class="m">${esc(text)}</div>${bad ? `<div class="m bad">${esc(bad)}</div>` : ""}</div>`;
}

function renderGlance() {
  const el = $("#glance");
  if (!el || S.left !== "glance") return;
  const [pLabel, pIcon, pPlace] = PURPOSE[S.plan.purpose] || PURPOSE.pickup;
  const a = S.recs?.assignment;
  const active = a && ["accepted", "in_progress"].includes(a.state);
  const urgent = S.alerts.some((x) => x.priority >= 3);

  // 1) 가장 크게: 남은 시간
  let label, num, next, cls = "";
  if (!S.session) {
    const classEnd = hhmm(S.scenario.pickup_end) === "18:10" ? "18:00" : hhmm(S.scenario.pickup_end);
    label = `${pPlace} 끝나는 ${classEnd}까지`;
    num = minutesUntil(classEnd);
    next = S.stage === "park" ? "먼저 차 세울 곳을 고르세요" : "돌아올 시각을 정해 주세요";
  } else {
    label = `${pLabel} ${S.plan.returnBy}까지`;
    num = minutesUntil(S.plan.returnBy);
    if (active) next = a.state === "accepted" ? `${shopOf(a.evaluation.partner)}에 가는 중` : `${shopOf(a.evaluation.partner)}에서 일하는 중`;
    else next = S.resting ? "쉬는 중이에요" : `시간 맞는 일 ${S.recs?.recommended?.length || 0}개`;
    if (num <= 10) cls = "warn";
    if (active) {
      const lateBy = minutesUntil(shiftTime(a.evaluation.finish_at, delayNow(a))) - num;
      if (lateBy > 0) { cls = "danger"; next = `이대로면 ${lateBy}분 늦어요 · 끝나면 바로 출발하세요`; }
    }
  }
  if (urgent || num <= 0) cls = "danger";
  const hero = `<div class="hero ${cls}"><div class="label">${esc(label)}</div>
    <div class="num">${num > 0 ? num : 0}<small>분 남았어요</small></div><div class="next">${esc(next)}</div></div>`;

  // 2) 경로 띠: 그림만 봐도 어디서 어디로, 몇 분인지
  const mineDelay = S.live.filter((x) => x.mine && x.type !== "weather").reduce((s, x) => s + x.delay_min, 0);
  const rain = S.live.some((x) => x.type === "weather");
  let strip;
  if (active) {
    const bd = a.evaluation.breakdown;
    const onFoot = bd.walk_to_site != null;
    const go = bd.drive_to_site ?? bd.walk_to_site, back = bd.drive_back ?? bd.walk_back;
    const bad = !onFoot && (mineDelay || rain) ? `+${mineDelay + (rain ? 3 : 0)}분 지연` : "";
    strip = `<div class="strip"><h5>지금 동선</h5><div class="nodes">
      ${node("🅿️", "내 차", "출발", a.state === "accepted")}
      ${link(`${onFoot ? "걸어서" : "차로"} ${go}분`, { walk: onFoot, bad: a.state === "accepted" ? bad : "" })}
      ${node("📦", shopOf(a.evaluation.partner), `일 ${bd.task}분`, a.state === "in_progress")}
      ${link(`${onFoot ? "걸어서" : "차로"} ${back}분`, { walk: onFoot, bad })}
      ${node(pIcon, pPlace, S.plan.returnBy)}
    </div></div>`;
  } else if (S.lot) {
    strip = `<div class="strip"><h5>지금 동선</h5><div class="nodes">
      ${node("🅿️", "내 차", lotShort(S.lot), true)}
      ${link(`걸어서 ${S.lot.walk_to_destination_min}분`, { walk: true })}
      ${node(pIcon, pPlace, S.session ? S.plan.returnBy : "")}
    </div></div>`;
  } else {
    const best = S.lots[0];
    strip = best ? `<div class="strip"><h5>가장 가까운 주차장으로 가면</h5><div class="nodes">
      ${node("🚗", "지금 위치", "", true)}
      ${link(`차로 ${best.drive_min}분`)}
      ${node("🅿️", lotShort(best), won(best.fee_estimate))}
      ${link(`걸어서 ${best.walk_to_destination_min}분`, { walk: true })}
      ${node(pIcon, pPlace, "")}
    </div></div>` : "";
  }

  // 3) 지금 주변 상황
  const live = S.session
    ? (S.live.length ? S.live.map((x) => `<div class="live-item ${x.mine ? "mine" : ""}"><span class="e">${LIVE_ICON[x.type] || "⚠️"}</span>
        <div><b>${esc(x.title)}</b><small>${x.type === "weather" ? "운전하면 3분쯤 더 걸려요" : x.mine ? `내 동선에 영향 · ${x.delay_min}분 정도 늦어져요` : "내 동선과는 떨어져 있어요"} · ${esc(x.source)}</small></div></div>`).join("")
      : `<div class="live-empty">지금은 특별한 상황이 없어요. 생기면 바로 말씀드릴게요.</div>`)
    : `<div class="live-empty">계획을 시작하면 사고·정체·날씨를 계속 지켜볼게요.</div>`;

  // 4) 불법 주정차 손해 (합법 주차 유도)
  const z = S.enf?.zones?.[0];
  const myLot = S.lot || S.lots[0];
  const fine = z ? `<div class="fine">
      <div class="head"><div class="sign">단속</div><div class="t">${esc(z.name)}은 ${esc(z.kind)}이에요<small>잠깐만 세워도 과태료 ${won(z.fine_car)} (승용차 기준)</small></div></div>
      <div class="vs">
        <div class="box good"><small>${myLot ? esc(lotShort(myLot)) : "주차장"}</small><b>${myLot ? won(myLot.fee_estimate) : "-"}</b></div>
        <div class="x">vs</div>
        <div class="box bad"><small>불법 주정차</small><b>${won(z.fine_car)}</b></div>
      </div>
      <div class="counter">오늘 이 구역 예상 단속액<br><b id="enfCounter">${won(Math.floor(S.enfBase))}</b>
        <small>하루 예상 약 ${Math.round(z.today_estimate_total / 10000).toLocaleString("ko-KR")}만 원 · ${esc(z.source)} · 시연용 추정치</small></div>
    </div>` : "";

  el.innerHTML = hero + strip + `<div class="sec-title">${S.session ? '<span class="dot-live"></span>' : ""}지금 주변 상황</div><div class="live">${live}</div>` + fine;
}

async function loadEnforcement() {
  try {
    const d = S.scenario.destination;
    S.enf = await api(`/api/enforcement?lat=${d.lat}&lng=${d.lng}&now=${encodeURIComponent(S.now)}`);
    S.enfBase = S.enf.zones[0]?.today_estimate_so_far || 0;
    S.enfAt = performance.now();
  } catch (_) { S.enf = null; }
}
// 실제 시간이 흐르는 동안 계속 올라가는 카운터 (분당 평균 단속액 기준)
function tickCounter() {
  const z = S.enf?.zones?.[0], el = $("#enfCounter");
  if (!z || !el) return;
  const v = S.enfBase + (z.per_minute / 60) * ((performance.now() - S.enfAt) / 1000);
  el.textContent = won(Math.floor(v));
}

// ---------- 먼저 말 걸기 ----------
const ALERT_KIND = { late: "늦을 수 있어요", tight: "시간이 빠듯해요", info: "길 상황", leave: "출발 알림", weather: "날씨", rush: "학원 앞 상황",
  safety: "안전", schedule: "일정 변경", new_gig: "새 일", remind: "시간 알림" };

function renderAlerts() {
  return S.alerts.slice(0, 2).map((x, i) => `
    <div class="alert p${x.priority}"><div class="k">${ALERT_KIND[x.kind] || "알림"}</div><p>${esc(S.gear === "D" ? x.say_short : x.say)}</p>
      <div class="row">${x.actions.map((ac) => `<button class="btn ${ac.action === "dismiss" ? "ghost" : "primary"}" data-alert-act="${ac.action}" data-alert-idx="${i}" data-minutes="${ac.minutes || 0}">${esc(ac.label)}</button>`).join("")}
      ${x.actions.length ? "" : `<button class="btn ghost" data-alert-act="close" data-alert-idx="${i}">확인</button>`}</div>
    </div>`).join("");
}

async function pollSituation() {
  if (!S.session) return;
  const q = new URLSearchParams({ now: S.now, gear: S.gear, resting: S.resting });
  const r = await api(`/api/sessions/${S.session}/situation?${q}`);
  S.live = r.live;
  if (r.interventions.length) {
    // 같은 갈래(길 상황·출발)의 새 알림이 오면 옛 알림은 치운다 — 화면엔 지금 유효한 말만
    const ROUTE = ["late", "tight", "info", "leave"];
    const newRoute = r.interventions.some((x) => ROUTE.includes(x.kind));
    S.alerts = [...r.interventions, ...S.alerts.filter((x) => !(newRoute && ROUTE.includes(x.kind)))].slice(0, 3);
    const top = r.interventions[0];
    say(S.gear === "D" ? top.say_short : top.say);
    if (top.actions.length || top.priority >= 3) stopAuto(); // 결정이 필요한 순간에는 자동 진행을 멈춘다
  }
  render();
}

async function alertAction(idx, action, minutes) {
  const x = S.alerts[idx];
  S.alerts.splice(idx, 1);
  if (action === "close") return render();
  if (action === "show_gigs") { await loadRecs(); go("pick"); return say("새로 올라온 일 보여 드릴게요."); }
  try {
    const r = await api(`/api/sessions/${S.session}/situation/action`, { method: "POST", body: JSON.stringify({ action, minutes, intervention_id: x?.id || "" }) });
    if (action === "extend") S.plan.returnBy = r.return_by;
    await loadRecs();
    if (action === "cancel_gig") go("go"); else render();
    say(r.message);
  } catch (e) { say(e.message); }
}

// ---------- 시간 흐름 (시연) ----------
async function advance(min) {
  const d = new Date(S.now); d.setMinutes(d.getMinutes() + min); S.now = toIso(d);
  await loadEnforcement();
  await loadRecs();
  if (S.session) await pollSituation(); else render();
}
function stopAuto() {
  if (S.auto) clearInterval(S.auto);
  S.auto = null;
  const b = $("#autoplay"); if (b) { b.classList.remove("on"); b.textContent = "▶ 실시간 자동 진행 (1분씩)"; }
}
function toggleAuto() {
  if (S.auto) return stopAuto();
  if (!S.session) return say("먼저 주차하고 계획을 시작해 주세요. 그다음 자동 진행이 돼요.");
  const b = $("#autoplay"); b.classList.add("on"); b.textContent = "⏸ 자동 진행 멈추기";
  let busy = false;
  S.auto = setInterval(async () => {
    if (busy) return; busy = true;
    try {
      await advance(1);
      if (minutesUntil(S.plan.returnBy) < -2) stopAuto();
    } finally { busy = false; }
  }, 2200);
}

async function init() {
  S.scenario = await api("/api/demo/scenario");
  S.now = S.scenario.now;
  // 새로고침 전 이용 기록이 남아 있으면 지운다 (배정된 일감도 함께 풀림)
  try {
    const prev = localStorage.getItem("routemate.session");
    if (prev) { await fetch(`/api/sessions/${prev}`, { method: "DELETE" }); localStorage.removeItem("routemate.session"); }
  } catch (_) {}
  setupSettings();
  setupDemoTools();
  await loadParking();
  await loadEnforcement();
  render();
  setInterval(tickCounter, 250);
  const z = S.enf?.zones?.[0];
  $("#bubbleText").textContent = z
    ? `주차장 ${S.lots.length}곳 찾았어요. ${z.name}은 ${z.kind}이라, 잠깐 세워도 과태료가 ${Math.round(z.fine_car / 10000)}만 원이에요.`
    : `주차장 ${S.lots.length}곳 찾았어요.`;
  S.lastSpoken = $("#bubbleText").textContent;
}
init();
