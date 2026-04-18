const API = "/api";
const LS_DISCLAIMER = "wt.disclaimer.v1";

const state = {
  profile: null,
  program: null,
  progression: null,
  streaks: null,
  view: "profile",
};

// ---------- tiny helpers ----------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstChild;
};
const todayISO = () => new Date().toISOString().slice(0, 10);
const parseCSV = (s) => (s || "").split(",").map(x => x.trim()).filter(Boolean);

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  if (res.status === 204) return null;
  return res.json();
}

// ---------- audio beep (no asset files) ----------
let _audioCtx = null;
function beep(freq = 880, ms = 160) {
  try {
    _audioCtx = _audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = _audioCtx.createOscillator();
    const g = _audioCtx.createGain();
    o.frequency.value = freq;
    o.type = "sine";
    o.connect(g); g.connect(_audioCtx.destination);
    g.gain.setValueAtTime(0.001, _audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, _audioCtx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + ms / 1000);
    o.start();
    o.stop(_audioCtx.currentTime + ms / 1000 + 0.02);
  } catch {}
  if (navigator.vibrate) navigator.vibrate(80);
}

// ---------- plate calc ----------
// default plates (kg, per side): 20, 15, 10, 5, 2.5, 1.25
function platesForSide(totalKg, barKg = 20, plates = [20, 15, 10, 5, 2.5, 1.25]) {
  if (totalKg <= barKg) return null;
  let remaining = (totalKg - barKg) / 2;
  const out = [];
  for (const p of plates) {
    while (remaining >= p - 0.001) {
      out.push(p); remaining -= p;
    }
  }
  if (remaining > 0.1) return { plates: out, leftover: +remaining.toFixed(2) };
  return { plates: out, leftover: 0 };
}

function plateHTML(totalKg, equipment) {
  if (equipment !== "barbell") return "";
  if (!totalKg || totalKg <= 0) return "";
  const res = platesForSide(totalKg);
  if (!res) return `<div class="plate-calc">Bar only (≤ 20kg).</div>`;
  const txt = res.plates.length
    ? res.plates.join(" + ") + " per side"
    : "bar only";
  const lo = res.leftover ? ` <span class="err">(+${res.leftover}kg unaccounted)</span>` : "";
  return `<div class="plate-calc">Plates: <span class="plates">${txt}</span>${lo}</div>`;
}

// ---------- stepper ----------
function stepper(label, value, step, min = 0, max = 9999, cb) {
  const wrap = el(`
    <div class="stepper" aria-label="${label}">
      <button type="button" aria-label="decrease ${label}">−</button>
      <input type="number" inputmode="decimal" value="${value}" />
      <button type="button" aria-label="increase ${label}">+</button>
      <div class="label">${label}</div>
    </div>
  `);
  const [dec, inc] = wrap.querySelectorAll("button");
  const input = wrap.querySelector("input");
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const change = (v) => {
    input.value = v;
    cb && cb(v);
  };
  dec.addEventListener("click", () => change(clamp(+(+input.value - step).toFixed(2))));
  inc.addEventListener("click", () => change(clamp(+(+input.value + step).toFixed(2))));
  input.addEventListener("input", () => cb && cb(+input.value || 0));
  return wrap;
}

// ---------- views ----------
function renderProfile() {
  const tpl = $("#tpl-profile").content.cloneNode(true);
  const form = tpl.querySelector("#profile-form");

  if (state.profile) {
    const p = state.profile;
    form.elements.name.value = p.name || "";
    form.elements.age.value = p.age ?? "";
    form.elements.sex.value = p.sex || "";
    form.elements.height_cm.value = p.height_cm ?? "";
    form.elements.weight_kg.value = p.weight_kg ?? "";
    form.elements.fitness_level.value = p.fitness_level || "beginner";
    form.elements.goals.value = p.goals || "general_strength";
    form.elements.injuries.value = (p.injuries || []).join(", ");
    form.elements.conditions.value = (p.conditions || []).join(", ");
    form.elements.equipment.value = (p.equipment || []).join(", ");
    form.elements.notes.value = p.notes || "";
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = form.elements;
    const payload = {
      name: f.name.value,
      age: f.age.value ? Number(f.age.value) : null,
      sex: f.sex.value || null,
      height_cm: f.height_cm.value ? Number(f.height_cm.value) : null,
      weight_kg: f.weight_kg.value ? Number(f.weight_kg.value) : null,
      fitness_level: f.fitness_level.value,
      goals: f.goals.value,
      injuries: parseCSV(f.injuries.value),
      conditions: parseCSV(f.conditions.value),
      equipment: parseCSV(f.equipment.value),
      notes: f.notes.value,
    };
    const saved = state.profile
      ? await api(`/profile/${state.profile.id}`, { method: "PUT", body: JSON.stringify(payload) })
      : await api(`/profile`, { method: "POST", body: JSON.stringify(payload) });
    state.profile = saved;
    await refreshStreaks();
    setIndicator();
    switchView("today");
  });

  swap(tpl);
}

// ---------- Today ----------
async function renderToday() {
  if (!state.profile) { switchView("profile"); return; }
  const tpl = $("#tpl-today").content.cloneNode(true);
  $("#app").replaceChildren(tpl);

  $("#today-date").value = todayISO();

  const [program, progression, streaks] = await Promise.all([
    api(`/program/${state.profile.id}`),
    api(`/stats/progression?profile_id=${state.profile.id}`),
    api(`/stats/streaks?profile_id=${state.profile.id}`),
  ]);
  state.program = program;
  state.progression = progression;
  state.streaks = streaks;

  if (streaks.nudges && streaks.nudges.length) {
    $("#nudge-panel").classList.remove("hidden");
    $("#nudge-panel").innerHTML = `<strong>Nudges</strong><ul>${streaks.nudges.map(n => `<li>${n}</li>`).join("")}</ul>`;
  }

  const sel = $("#today-day");
  program.days.forEach((d, i) => {
    const o = document.createElement("option");
    o.value = i; o.textContent = `${d.label} (${d.focus})`;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => renderExercises(Number(sel.value)));
  renderExercises(0);

  $("#today-save").addEventListener("click", saveSession);
}

function renderExercises(dayIdx) {
  const container = $("#today-exercises");
  container.innerHTML = "";
  const day = state.program.days[dayIdx];
  if (!day) { container.innerHTML = "<p class='err'>No safe exercises available for this day — review profile.</p>"; return; }

  day.exercises.forEach((ex, i) => {
    const suggest = state.progression?.suggestions?.[ex.name];
    const yt = ex.youtube_url ? `<a href="${ex.youtube_url}" target="_blank" rel="noopener">▶ demo</a>` : "";
    const badge = suggest
      ? `<span class="suggest-badge" title="${suggest.reason}">suggested: ${suggest.suggested_weight_kg}kg</span>`
      : "";

    const block = el(`
      <div class="ex-block" data-ex="${i}">
        <div class="ex-title">
          <div><strong>${ex.name}</strong> <small>· ${ex.muscle_group} · ${ex.equipment}</small></div>
          <div style="display:flex; gap:.4rem; align-items:center;">
            ${badge}
            <small>target ${ex.default_sets} × ${ex.default_reps}</small>
            ${yt}
          </div>
        </div>
        <div class="sets-container"></div>
        <button type="button" class="add-set">+ add set</button>
        <label>Notes <input class="ex-notes" placeholder="form cues, pain, etc." /></label>
      </div>
    `);
    container.appendChild(block);

    const setsContainer = block.querySelector(".sets-container");
    const startWeight = suggest?.suggested_weight_kg ?? 0;
    const defaultReps = parseFirstInt(ex.default_reps) ?? 8;

    const addSet = (reps = defaultReps, weight = startWeight, rpe = "") => {
      const idx = setsContainer.querySelectorAll(".setrow-card").length + 1;
      const row = el(`<div class="setrow-card"><div class="setnum">${idx}</div></div>`);

      const repsStepper = stepper("reps", reps, 1, 0, 99);
      const weightStepper = stepper("weight kg", weight, 2.5, 0, 999, (v) => {
        plateWrap.innerHTML = plateHTML(v, ex.equipment);
      });
      const rpeStepper = stepper("RPE", rpe === "" ? 7 : rpe, 1, 1, 10);

      const doneBtn = el(`<button type="button" class="done-set" title="Mark set complete">✓</button>`);
      const timerSlot = el(`<div class="timer-slot" style="grid-column: 1/-1;"></div>`);
      const plateWrap = el(`<div class="plate-wrap" style="grid-column: 1/-1;">${plateHTML(weight, ex.equipment)}</div>`);

      row.append(repsStepper, weightStepper, rpeStepper, doneBtn, plateWrap, timerSlot);

      doneBtn.addEventListener("click", () => {
        if (doneBtn.classList.contains("done")) return;
        doneBtn.classList.add("done");
        doneBtn.textContent = "✓✓";
        beep(880, 140);
        setTimeout(() => beep(1100, 120), 180);
        startRestTimer(timerSlot, 90); // 90s default rest
      });

      setsContainer.appendChild(row);
    };

    for (let s = 0; s < ex.default_sets; s++) addSet();
    block.querySelector(".add-set").addEventListener("click", () => addSet());
  });
}

function parseFirstInt(str) {
  const m = String(str || "").match(/\d+/);
  return m ? Number(m[0]) : null;
}

function startRestTimer(slot, seconds) {
  slot.innerHTML = "";
  const box = el(`<div class="rest-timer"><span class="t">${fmtMMSS(seconds)}</span><button type="button" data-a="-15">−15</button><button type="button" data-a="+15">+15</button><button type="button" data-a="skip">skip</button></div>`);
  slot.appendChild(box);
  let remaining = seconds;
  const t = box.querySelector(".t");
  const id = setInterval(() => {
    remaining -= 1;
    t.textContent = fmtMMSS(Math.max(0, remaining));
    if (remaining <= 0) {
      clearInterval(id);
      beep(660, 220);
      setTimeout(() => beep(990, 260), 260);
      box.remove();
    }
  }, 1000);
  box.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    const a = b.dataset.a;
    if (a === "skip") { clearInterval(id); box.remove(); return; }
    remaining += a === "+15" ? 15 : -15;
    if (remaining <= 0) { clearInterval(id); box.remove(); return; }
    t.textContent = fmtMMSS(remaining);
  }));
}

function fmtMMSS(s) {
  const m = Math.floor(s / 60); const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function collectEntries() {
  const blocks = $$(".ex-block");
  const day = state.program.days[Number($("#today-day").value)];
  const entries = [];
  blocks.forEach((b, i) => {
    const rows = [...b.querySelectorAll(".setrow-card")];
    const sets = rows
      .map(r => {
        const [repsI, weightI, rpeI] = r.querySelectorAll(".stepper input");
        const reps = Number(repsI?.value || 0);
        const weight_kg = Number(weightI?.value || 0);
        const rpeVal = rpeI?.value;
        return {
          reps,
          weight_kg,
          rpe: rpeVal ? Number(rpeVal) : null,
        };
      })
      .filter(s => s.reps > 0);
    if (sets.length) {
      entries.push({
        exercise: day.exercises[i].name,
        sets,
        notes: b.querySelector(".ex-notes").value || "",
      });
    }
  });
  return entries;
}

async function saveSession() {
  const dayIdx = Number($("#today-day").value);
  const day = state.program.days[dayIdx];
  const entries = collectEntries();
  if (entries.length === 0) {
    $("#today-result").innerHTML = `<p class='err'>Log at least one set before saving.</p>`;
    return;
  }
  const payload = {
    profile_id: state.profile.id,
    date: $("#today-date").value,
    day_label: day.label,
    entries,
    perceived_effort: Number($("#today-rpe").value || 5),
    session_notes: $("#today-notes").value,
  };
  const saved = await api(`/sessions`, { method: "POST", body: JSON.stringify(payload) });
  $("#today-result").innerHTML = `<p>Saved session #${saved.id}. <a href="#" id="goto-hist">View history</a></p>`;
  $("#goto-hist").addEventListener("click", (e) => { e.preventDefault(); switchView("history"); });
  await refreshStreaks();
}

// ---------- Pain ----------
async function renderPain() {
  if (!state.profile) { switchView("profile"); return; }
  const tpl = $("#tpl-pain").content.cloneNode(true);
  $("#app").replaceChildren(tpl);
  $("#pain-date").value = todayISO();
  const range = $("#pain-score");
  range.addEventListener("input", () => { $("#pain-score-val").textContent = range.value; });
  $("#pain-save").addEventListener("click", async () => {
    const payload = {
      profile_id: state.profile.id,
      date: $("#pain-date").value,
      area: $("#pain-area").value,
      score: Number($("#pain-score").value),
      notes: $("#pain-notes").value,
    };
    await api("/pain", { method: "POST", body: JSON.stringify(payload) });
    $("#pain-notes").value = "";
    range.value = 0; $("#pain-score-val").textContent = "0";
    await loadPainList();
  });
  await loadPainList();
}

async function loadPainList() {
  const list = $("#pain-list");
  list.innerHTML = "";
  const entries = await api(`/pain?profile_id=${state.profile.id}&days=60`);
  if (!entries.length) { list.innerHTML = "<p class='muted'>No pain logged in the last 60 days.</p>"; return; }
  entries.forEach(p => {
    const lvl = p.score >= 7 ? "high" : p.score >= 4 ? "mid" : "low";
    const row = el(`
      <div class="pain-row">
        <span class="pain-score" data-level="${lvl}">${p.score}</span>
        <div style="flex:1;"><strong>${p.area}</strong> <small class="muted">${p.date}</small>${p.notes ? `<div class="muted">${p.notes}</div>` : ""}</div>
        <button type="button" data-id="${p.id}">delete</button>
      </div>
    `);
    row.querySelector("button").addEventListener("click", async () => {
      await api(`/pain/${p.id}`, { method: "DELETE" });
      await loadPainList();
    });
    list.appendChild(row);
  });
}

// ---------- History (calendar + charts) ----------
const calState = { year: null, month: null, data: null };

async function renderHistory() {
  if (!state.profile) { switchView("profile"); return; }
  const tpl = $("#tpl-history").content.cloneNode(true);
  $("#app").replaceChildren(tpl);
  const now = new Date();
  calState.year = now.getFullYear();
  calState.month = now.getMonth() + 1;
  $("#cal-prev").addEventListener("click", () => shiftMonth(-1));
  $("#cal-next").addEventListener("click", () => shiftMonth(1));
  $("#cal-today").addEventListener("click", () => {
    const d = new Date();
    calState.year = d.getFullYear(); calState.month = d.getMonth() + 1;
    loadCalendar();
  });
  await loadCalendar();
  await loadCharts();
}

async function shiftMonth(delta) {
  let m = calState.month + delta, y = calState.year;
  if (m < 1) { m = 12; y -= 1; } else if (m > 12) { m = 1; y += 1; }
  calState.year = y; calState.month = m;
  await loadCalendar();
}

async function loadCalendar() {
  calState.data = await api(`/sessions/calendar?year=${calState.year}&month=${calState.month}&profile_id=${state.profile.id}`);
  drawCalendar();
  $("#day-sessions")?.classList.add("hidden");
  $("#session-detail")?.classList.add("hidden");
}

function drawCalendar() {
  const { year, month, data } = calState;
  const label = new Date(year, month - 1, 1).toLocaleString(undefined, { month: "long", year: "numeric" });
  $("#cal-label").textContent = label;
  const grid = $("#cal-grid");
  grid.innerHTML = "";
  const leading = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const todayIso = todayISO();
  for (let i = 0; i < leading; i++) grid.appendChild(el(`<div class="cal-day empty"></div>`));
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const sessions = (data.days && data.days[iso]) || [];
    const classes = ["cal-day"];
    if (sessions.length) classes.push("has");
    if (iso === todayIso) classes.push("today");
    const marker = sessions.length ? `<div class="marker">${sessions.length}× · RPE ${sessions[0].perceived_effort}</div>` : "";
    const cell = el(`<div class="${classes.join(" ")}"><div class="num">${d}</div>${marker}</div>`);
    if (sessions.length) cell.addEventListener("click", () => showDaySessions(iso, sessions));
    grid.appendChild(cell);
  }
}

function showDaySessions(iso, sessions) {
  const panel = $("#day-sessions");
  panel.classList.remove("hidden");
  $("#ds-title").textContent = iso;
  const list = $("#ds-list");
  list.innerHTML = "";
  sessions.forEach(s => {
    const tag = s.has_suggestions ? `<span class="pill">AI ✓</span>` : "";
    const item = el(`
      <div class="history-item">
        <div><strong>${s.day_label || "—"}</strong> ${tag}</div>
        <span class="pill">${s.entries_count} exercises · RPE ${s.perceived_effort}</span>
      </div>
    `);
    item.addEventListener("click", () => showSessionDetail(s.id));
    list.appendChild(item);
  });
  $("#session-detail").classList.add("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function showSessionDetail(id) {
  const s = await api(`/sessions/${id}`);
  $("#session-detail").classList.remove("hidden");
  $("#sd-title").textContent = `${s.date} — ${s.day_label}`;
  const body = $("#sd-body");
  body.innerHTML = "";
  (s.entries || []).forEach(e => {
    const lines = e.sets.map((st, i) =>
      `set ${i + 1}: ${st.reps} reps × ${st.weight_kg} kg${st.rpe ? ` @ RPE ${st.rpe}` : ""}`
    ).join("<br/>");
    body.appendChild(el(`<div class="ex-block"><div class="ex-title"><strong>${e.exercise}</strong></div><div>${lines}</div>${e.notes ? `<small>${e.notes}</small>` : ""}</div>`));
  });
  const sg = $("#sd-suggestions");
  sg.innerHTML = "";
  if (s.ai_suggestions && s.ai_suggestions.summary) renderSuggestions(s.ai_suggestions);
  const btn = $("#sd-suggest");
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = "Thinking (Ollama)...";
    try {
      const updated = await api(`/sessions/${id}/suggest`, { method: "POST" });
      renderSuggestions(updated.ai_suggestions);
    } catch (e) {
      sg.innerHTML = `<p class='err'>Failed: ${e.message}</p>`;
    } finally { btn.disabled = false; btn.textContent = "Get AI suggestions"; }
  };
}

function renderSuggestions(s) {
  const sg = $("#sd-suggestions");
  const next = (s.next_session || []).map(x => `<li>${x}</li>`).join("");
  const watch = (s.watchouts || []).map(x => `<li class='watchout'>${x}</li>`).join("");
  sg.innerHTML = `
    <div class="suggestion">
      <h4>Summary</h4><p>${s.summary || ""}</p>
      ${next ? `<h4>Next session</h4><ul>${next}</ul>` : ""}
      ${watch ? `<h4>Watchouts</h4><ul>${watch}</ul>` : ""}
      ${s.recovery ? `<h4>Recovery</h4><p>${s.recovery}</p>` : ""}
    </div>`;
}

// ---------- Charts (SVG, no libs) ----------
const GROUP_COLORS = {
  chest: "#6ee7b7", back: "#60a5fa", legs: "#f472b6",
  shoulders: "#fbbf24", arms: "#c084fc", core: "#94a3b8", full_body: "#a3e635",
};

async function loadCharts() {
  const [vol, orm] = await Promise.all([
    api(`/stats/volume?profile_id=${state.profile.id}&weeks=8`),
    api(`/stats/one-rm?profile_id=${state.profile.id}`),
  ]);
  drawVolumeChart(vol);
  draw1RMChart(orm);
}

function drawVolumeChart({ weeks, data }) {
  const host = $("#chart-volume");
  host.innerHTML = "";
  if (!weeks.length) { host.innerHTML = "<p class='muted'>Not enough data yet.</p>"; return; }
  const groups = Array.from(new Set(Object.values(data).flatMap(g => Object.keys(g))));
  const W = 800, H = 240, pad = 30;
  const maxVal = Math.max(1, ...Object.values(data).flatMap(g => Object.values(g)));
  const barW = (W - pad * 2) / weeks.length / Math.max(1, groups.length) * 0.85;

  const legend = el(`<div class="svg-legend">${groups.map(g => `<span><i class="swatch" style="background:${GROUP_COLORS[g] || "#666"}"></i>${g}</span>`).join("")}</div>`);
  host.appendChild(legend);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "svg-chart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");

  weeks.forEach((wk, wi) => {
    const baseX = pad + wi * ((W - pad * 2) / weeks.length);
    const xLabel = document.createElementNS(svg.namespaceURI, "text");
    xLabel.setAttribute("x", baseX + 5); xLabel.setAttribute("y", H - 8);
    xLabel.textContent = wk.slice(5);
    svg.appendChild(xLabel);

    groups.forEach((g, gi) => {
      const val = (data[wk] && data[wk][g]) || 0;
      const h = (val / maxVal) * (H - pad * 2);
      const rect = document.createElementNS(svg.namespaceURI, "rect");
      rect.setAttribute("x", baseX + gi * (barW + 1));
      rect.setAttribute("y", H - pad - h);
      rect.setAttribute("width", barW);
      rect.setAttribute("height", h);
      rect.setAttribute("fill", GROUP_COLORS[g] || "#666");
      const title = document.createElementNS(svg.namespaceURI, "title");
      title.textContent = `${g} ${wk}: ${Math.round(val)} kg-reps`;
      rect.appendChild(title);
      svg.appendChild(rect);
    });
  });
  host.appendChild(svg);
}

function draw1RMChart({ series }) {
  const host = $("#chart-1rm");
  host.innerHTML = "";
  const lifts = Object.keys(series).filter(k => series[k].length >= 1);
  if (!lifts.length) { host.innerHTML = "<p class='muted'>Log more sessions to see 1RM trends.</p>"; return; }

  const W = 800, H = 240, pad = 30;
  // collect all dates & 1RMs
  const allDates = Array.from(new Set(lifts.flatMap(l => series[l].map(p => p.date)))).sort();
  const xFor = (d) => pad + (allDates.indexOf(d) / Math.max(1, allDates.length - 1)) * (W - pad * 2);
  const max1 = Math.max(1, ...lifts.flatMap(l => series[l].map(p => p.e1rm)));
  const yFor = (v) => H - pad - (v / max1) * (H - pad * 2);

  const palette = ["#6ee7b7", "#60a5fa", "#f472b6", "#fbbf24", "#c084fc", "#a3e635", "#f87171", "#22d3ee"];
  const legendItems = lifts.map((l, i) => `<span><i class="swatch" style="background:${palette[i % palette.length]}"></i>${l}</span>`).join("");
  host.appendChild(el(`<div class="svg-legend">${legendItems}</div>`));

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "svg-chart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");

  // y axis label
  const yl = document.createElementNS(svg.namespaceURI, "text");
  yl.setAttribute("x", 4); yl.setAttribute("y", 14); yl.textContent = `max e1RM: ${Math.round(max1)}kg`;
  svg.appendChild(yl);

  lifts.forEach((l, i) => {
    const pts = series[l].map(p => `${xFor(p.date)},${yFor(p.e1rm)}`).join(" ");
    const poly = document.createElementNS(svg.namespaceURI, "polyline");
    poly.setAttribute("fill", "none");
    poly.setAttribute("stroke", palette[i % palette.length]);
    poly.setAttribute("stroke-width", "2");
    poly.setAttribute("points", pts);
    svg.appendChild(poly);
    series[l].forEach(p => {
      const c = document.createElementNS(svg.namespaceURI, "circle");
      c.setAttribute("cx", xFor(p.date)); c.setAttribute("cy", yFor(p.e1rm));
      c.setAttribute("r", "3"); c.setAttribute("fill", palette[i % palette.length]);
      const t = document.createElementNS(svg.namespaceURI, "title");
      t.textContent = `${l} ${p.date}: ${p.e1rm}kg`;
      c.appendChild(t);
      svg.appendChild(c);
    });
  });

  host.appendChild(svg);
}

// ---------- Review ----------
async function renderReview() {
  if (!state.profile) { switchView("profile"); return; }
  const tpl = $("#tpl-review").content.cloneNode(true);
  $("#app").replaceChildren(tpl);
  $("#review-run").addEventListener("click", async () => {
    const btn = $("#review-run");
    btn.disabled = true; btn.textContent = "Reviewing the week (Ollama)...";
    const out = $("#review-result");
    out.innerHTML = "";
    try {
      const data = await api(`/review/weekly?profile_id=${state.profile.id}`, { method: "POST" });
      const r = data.ai_review || {};
      out.innerHTML = `
        <div class="suggestion">
          <p class="muted">${data.sessions_count} sessions, ${data.pain_entries_count} pain entries · ${data.window_start} → ${data.window_end}</p>
          <h4>Summary</h4><p>${r.summary || "(empty)"}</p>
          ${r.what_worked?.length ? `<h4>What worked</h4><ul>${r.what_worked.map(x=>`<li>${x}</li>`).join("")}</ul>` : ""}
          ${r.concerns?.length ? `<h4>Concerns</h4><ul>${r.concerns.map(x=>`<li class='watchout'>${x}</li>`).join("")}</ul>` : ""}
          ${r.next_week_plan?.length ? `<h4>Next week plan</h4><ul>${r.next_week_plan.map(x=>`<li>${x}</li>`).join("")}</ul>` : ""}
          ${r.program_changes?.length ? `<h4>Program changes</h4><ul>${r.program_changes.map(x=>`<li>${x}</li>`).join("")}</ul>` : ""}
        </div>`;
    } catch (e) {
      out.innerHTML = `<p class='err'>Failed: ${e.message}</p>`;
    } finally {
      btn.disabled = false; btn.textContent = "Generate weekly review";
    }
  });
}

// ---------- Settings ----------
function renderSettings() {
  if (!state.profile) { switchView("profile"); return; }
  const tpl = $("#tpl-settings").content.cloneNode(true);
  $("#app").replaceChildren(tpl);
  $("#export-btn").addEventListener("click", async () => {
    const data = await api(`/stats/export?profile_id=${state.profile.id}`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `workout-export-${todayISO()}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  });
  $("#wipe-btn").addEventListener("click", async () => {
    if (!confirm("Delete ALL sessions and pain entries for this profile? Profile will be kept.")) return;
    await api(`/stats/wipe?profile_id=${state.profile.id}`, { method: "DELETE" });
    alert("Wiped.");
    await refreshStreaks();
  });
}

// ---------- chrome ----------
function swap(tpl) { $("#app").replaceChildren(tpl); }

function switchView(v) {
  state.view = v;
  $$("header nav button").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  const fn = ({
    profile: renderProfile, today: renderToday, pain: renderPain,
    history: renderHistory, review: renderReview, settings: renderSettings,
  })[v];
  fn && fn();
}

function setIndicator() {
  $("#profile-indicator").textContent = state.profile
    ? `${state.profile.name} · ${state.profile.fitness_level} · injuries: ${(state.profile.injuries || []).join(", ") || "none"}`
    : "no profile — create one to begin";
}

async function refreshStreaks() {
  if (!state.profile) return;
  try {
    state.streaks = await api(`/stats/streaks?profile_id=${state.profile.id}`);
    const n = state.streaks.current_streak_days;
    $("#streak-badge").textContent = n ? `🔥 ${n}-day streak · ${state.streaks.total_sessions} sessions` : "";
  } catch {}
}

function showDisclaimerIfNeeded() {
  if (localStorage.getItem(LS_DISCLAIMER) === "1") return;
  $("#disclaimer").classList.remove("hidden");
  const ack = $("#disclaimer-ack"), go = $("#disclaimer-go");
  ack.addEventListener("change", () => { go.disabled = !ack.checked; });
  go.addEventListener("click", () => {
    localStorage.setItem(LS_DISCLAIMER, "1");
    $("#disclaimer").classList.add("hidden");
  });
}

async function init() {
  showDisclaimerIfNeeded();
  $$("header nav button").forEach(b => b.addEventListener("click", () => switchView(b.dataset.view)));
  try {
    const profs = await api("/profile");
    state.profile = profs[0] || null;
  } catch {}
  await refreshStreaks();
  setIndicator();
  switchView(state.profile ? "today" : "profile");
}

init();
