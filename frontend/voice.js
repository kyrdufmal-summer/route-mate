// 음성 안내 모듈
// - 브라우저가 제공하는 한국어 목소리 중 가장 자연스러운 것(신경망 음성)을 자동으로 고른다.
// - 화면 문구와 별도로 '말하기용 문구'를 만들어 시각·기호를 사람이 말하듯 읽는다.
// - 실제 차량에서는 Pleos TTS SDK 로 교체한다. (speak 인터페이스만 맞추면 됨)
const Voice = (() => {
  const KEY = "routemate.voice";
  let prefs = { on: true, name: null, rate: 1.0 };
  try { prefs = { ...prefs, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch (_) {}
  let voices = [];
  let audioCtx = null;

  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (_) {} };

  // 자연스러운 정도 점수: 신경망(Natural/Online/Neural) > 구글 > 기타 한국어 > 구형 로컬 음성
  function score(v) {
    const n = v.name;
    let s = 0;
    if (/Natural|Neural/i.test(n)) s += 50;
    if (/Online/i.test(n)) s += 30;
    if (/Google/i.test(n)) s += 25;
    if (/SunHi|InJoon|Hyunsu|Seoyeon|Yuna|Jian/i.test(n)) s += 10;
    if (/Heami/i.test(n)) s -= 10;
    return s;
  }

  function load() {
    const all = ("speechSynthesis" in window) ? speechSynthesis.getVoices() : [];
    voices = all.filter((v) => /^ko/i.test(v.lang)).sort((a, b) => score(b) - score(a));
    return voices;
  }

  function current() {
    return voices.find((v) => v.name === prefs.name) || voices[0] || null;
  }

  function isNatural(v) { return v && score(v) >= 25; }

  // 화면 문구 → 말하기 문구
  function spoken(text) {
    return String(text)
      .replace(/\[샘플\]\s*/g, "")
      .replace(/(\d{1,2}):(\d{2})/g, (_, h, m) => {
        h = Number(h); m = Number(m);
        const ampm = h < 12 ? "오전" : h === 12 ? "낮" : "오후";
        const hh = h % 12 === 0 ? 12 : h % 12;
        return `${ampm} ${hh}시${m ? ` ${m}분` : ""}`;
      })
      .replace(/\(P단\)/g, "")
      .replace(/(\d+)m\b/g, "$1미터")
      .replace(/km\/h/g, "킬로미터")
      .replace(/\s*[·•|]\s*/g, ", ")
      .replace(/→/g, ", 그다음 ")
      .replace(/[()]/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  // 안내 시작을 알리는 짧은 알림음 (차량 안내음처럼 부드럽게)
  function chime() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const t = audioCtx.currentTime;
      [[660, 0], [880, 0.12]].forEach(([f, d]) => {
        const o = audioCtx.createOscillator(), g = audioCtx.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0, t + d);
        g.gain.linearRampToValueAtTime(0.08, t + d + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.25);
        o.connect(g).connect(audioCtx.destination);
        o.start(t + d); o.stop(t + d + 0.3);
      });
    } catch (_) {}
  }

  function speak(text, { chimeFirst = true, onstart, onend } = {}) {
    // 차량용 앱(APK) 안에서는 차량(Android) 시스템 TTS 로 읽는다
    const native = window.RouteMateNative;
    if (prefs.on && native && native.available && native.available()) {
      if (chimeFirst) chime();
      onstart && onstart();
      setTimeout(() => { native.speak(spoken(text), prefs.rate); onend && setTimeout(onend, 4000); }, chimeFirst ? 380 : 0);
      return;
    }
    if (!prefs.on || !("speechSynthesis" in window)) { onend && onend(); return; }
    speechSynthesis.cancel();
    const v = current();
    // 문장 단위로 나눠 읽으면 끊김이 줄고 억양이 자연스러워진다
    const parts = spoken(text).split(/(?<=[.?!])\s+/).filter(Boolean);
    const run = () => parts.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p);
      u.lang = "ko-KR";
      if (v) u.voice = v;
      u.rate = prefs.rate * (isNatural(v) ? 1.0 : 0.95); // 구형 음성은 조금 천천히
      u.pitch = isNatural(v) ? 1.0 : 1.05;
      if (i === 0 && onstart) u.onstart = onstart;
      if (i === parts.length - 1 && onend) u.onend = onend;
      speechSynthesis.speak(u);
    });
    if (chimeFirst) { chime(); setTimeout(run, 380); } else run();
  }

  function onVoicesChanged(cb) {
    if (!("speechSynthesis" in window)) return cb([]);
    load(); cb(voices);
    speechSynthesis.onvoiceschanged = () => { load(); cb(voices); };
  }

  return {
    get prefs() { return prefs; },
    set(p) { prefs = { ...prefs, ...p }; save(); },
    speak, spoken, onVoicesChanged, current, isNatural,
    stop() { try { speechSynthesis.cancel(); } catch (_) {} },
  };
})();
