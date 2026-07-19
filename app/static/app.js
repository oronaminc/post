// 일본/대만 트렌드 모니터 — 프론트엔드 (프레임워크 없음, vanilla JS)
"use strict";

const state = {
  region: "",       // "" = 기본(첫) 지역
  category: "",     // "" = 전체
  view: "all",      // all | realtime | sustained
  source: "",
  q: "",
  sort: "rank",
  meta: null,
  lastUpdated: null,
  displayRefreshMs: 30000,
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const sec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (sec < 60) return `${sec}초 전`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  return `${Math.round(hr / 24)}일 전`;
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function currentRegion() {
  return state.region || (state.meta && state.meta.regions[0] && state.meta.regions[0].id) || "jp";
}

// ---------- 지역 스위처 ----------
function renderRegionSwitch() {
  const wrap = $("#region-switch");
  wrap.innerHTML = "";
  const cur = currentRegion();
  for (const r of state.meta.regions) {
    const b = el("button", r.id === cur ? "active" : null);
    b.innerHTML = `<span class="flag">${r.flag || ""}</span> ${r.label}`;
    b.onclick = () => {
      if (state.region === r.id) return;
      state.region = r.id;
      state.category = ""; state.source = "";
      renderRegionSwitch();
      loadMetaAndHealth();
      loadTrends();
    };
    wrap.appendChild(b);
  }
}

// ---------- 소스 헬스 ----------
function renderHealth(sources) {
  const wrap = $("#source-health");
  wrap.innerHTML = "";
  const dot = { ok: "dot-ok", empty: "dot-empty", error: "dot-error", running: "dot-running" };
  for (const s of sources) {
    const badge = el("span", "health-badge");
    badge.appendChild(el("span", `health-dot ${dot[s.status] || "dot-unknown"}`));
    const name = el("span", null, s.display_name || s.source);
    if (s.risk === "high") name.classList.add("risk-high");
    else if (s.risk === "medium") name.classList.add("risk-medium");
    badge.appendChild(name);
    if (s.status === "ok") badge.appendChild(el("span", "health-count", `${s.item_count}`));
    let tip = `상태: ${s.status}`;
    if (s.finished_at) tip += ` · ${timeAgo(s.finished_at)}`;
    if (s.error) tip += `\n오류: ${s.error}`;
    if (s.risk === "high") tip += `\n⚠️ 이용약관 리스크 높음`;
    badge.title = tip;
    wrap.appendChild(badge);
  }
}

// ---------- 카테고리 탭 ----------
function renderTabs() {
  const tabs = $("#category-tabs");
  tabs.innerHTML = "";
  const makeBtn = (id, label) => {
    const b = el("button", state.category === id ? "active" : null, label);
    b.onclick = () => { state.category = id; renderTabs(); loadTrends(); };
    return b;
  };
  tabs.appendChild(makeBtn("", "전체"));
  for (const c of state.meta.categories) tabs.appendChild(makeBtn(c.id, c.label));
}

// ---------- 소스 필터 (선택 지역 소스만) ----------
function renderSourceFilter() {
  const sel = $("#source-filter");
  const cur = currentRegion();
  const prev = state.source;
  sel.innerHTML = '<option value="">모든 소스</option>';
  for (const s of state.meta.sources) {
    if (s.regions && !s.regions.includes(cur)) continue;
    const o = el("option", null, s.display_name);
    o.value = s.name;
    sel.appendChild(o);
  }
  // 지역 바뀌면 이전 소스가 없을 수 있음 → 초기화
  if (![...sel.options].some((o) => o.value === prev)) { sel.value = ""; state.source = ""; }
  else sel.value = prev;
}

function changeEl(item) {
  const rc = item.rank_change;
  if (item.is_rising && (item.occurrences || 1) <= 1) return el("span", "change change-new", "NEW");
  if (rc == null) return el("span", "change change-flat", "–");
  if (rc > 0) return el("span", "change change-up", `▲ ${rc}`);
  if (rc < 0) return el("span", "change change-down", `▼ ${Math.abs(rc)}`);
  return el("span", "change change-flat", "―");
}

function fmtMetric(item) {
  const v = item.metric_value;
  const label = item.metric_label || "";
  if (!v && v !== 0) return label;
  let num = v >= 10000 ? (v / 10000).toFixed(1) + "만" :
            v >= 1000 ? Math.round(v).toLocaleString() : Math.round(v);
  return `${label} ${num}`.trim();
}

// ---------- 카드 ----------
function renderCard(item) {
  const card = el("div", `card status-${item.status || item.source_type}`);
  card.appendChild(el("div", `rank rank-${item.rank}`, `${item.rank}`));

  const body = el("div", "card-body");
  const term = el(item.url ? "a" : "span", "term", item.term);
  if (item.url) { term.href = item.url; term.target = "_blank"; term.rel = "noopener"; }
  body.appendChild(term);

  // 한국어 번역 (원어와 다를 때만)
  if (item.term_ko && item.term_ko.trim() && item.term_ko.trim() !== item.term.trim()) {
    body.appendChild(el("div", "term-ko", item.term_ko));
  }

  const row = el("div", "meta-row");
  row.appendChild(changeEl(item));
  if (item.status === "rising") row.appendChild(el("span", "tag tag-rising", "🔥 급상승"));
  else if (item.status === "sustained") row.appendChild(el("span", "tag tag-sustained", "📈 지속"));
  row.appendChild(el("span", "chip chip-cat", item.category_label || item.category));
  const src = state.meta.sources.find((s) => s.name === item.source);
  row.appendChild(el("span", "chip chip-source", src ? src.display_name : item.source));
  const metricTxt = fmtMetric(item);
  if (metricTxt) row.appendChild(el("span", "chip chip-metric", metricTxt));
  body.appendChild(row);

  card.appendChild(body);
  return card;
}

// ---------- 데이터 로드 ----------
let loading = false;
async function loadTrends() {
  if (loading) return;
  loading = true;
  try {
    const p = new URLSearchParams({
      region: currentRegion(), category: state.category, view: state.view,
      source: state.source, q: state.q, sort: state.sort,
    });
    const data = await fetchJSON(`/api/trends?${p}`);
    state.lastUpdated = data.last_updated;
    $("#last-updated").textContent = timeAgo(data.last_updated);
    const results = $("#results");
    results.innerHTML = "";
    if (!data.items.length) {
      $("#empty-state").classList.remove("hidden");
    } else {
      $("#empty-state").classList.add("hidden");
      const frag = document.createDocumentFragment();
      for (const it of data.items) frag.appendChild(renderCard(it));
      results.appendChild(frag);
    }
    $("#result-meta").textContent = `${data.count}건 표시`;
  } catch (e) {
    $("#result-meta").textContent = `불러오기 실패: ${e.message}`;
  } finally {
    loading = false;
  }
}

async function loadMetaAndHealth() {
  try {
    if (!state.meta) state.meta = await fetchJSON("/api/meta");
    const sec = state.meta.refresh_interval_seconds;
    $("#interval-label").textContent = sec >= 60 ? `${Math.round(sec / 60)}분` : `${sec}초`;
    renderRegionSwitch();
    renderTabs();
    renderSourceFilter();
    const health = await fetchJSON(`/api/sources?region=${currentRegion()}`);
    renderHealth(health.sources);
  } catch (e) {
    $("#result-meta").textContent = `초기화 실패: ${e.message}`;
  }
}

async function manualRefresh() {
  const btn = $("#refresh-btn");
  btn.classList.add("loading"); btn.disabled = true;
  try {
    await fetchJSON("/api/refresh", { method: "POST" });
    for (const delay of [2500, 6000, 12000, 20000]) {
      setTimeout(() => { loadMetaAndHealth(); loadTrends(); }, delay);
    }
  } catch (e) {
    $("#result-meta").textContent = `갱신 실패: ${e.message}`;
  } finally {
    setTimeout(() => { btn.classList.remove("loading"); btn.disabled = false; }, 3000);
  }
}

function bind() {
  $("#view-toggle").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state.view = b.dataset.view;
    for (const btn of $("#view-toggle").children) btn.classList.toggle("active", btn === b);
    loadTrends();
  });
  let searchTimer;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.q = e.target.value; loadTrends(); }, 250);
  });
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; loadTrends(); });
  $("#source-filter").addEventListener("change", (e) => { state.source = e.target.value; loadTrends(); });
  $("#refresh-btn").addEventListener("click", manualRefresh);
}

async function init() {
  bind();
  await loadMetaAndHealth();
  await loadTrends();
  setInterval(() => { loadMetaAndHealth(); loadTrends(); }, state.displayRefreshMs);
  setInterval(() => {
    if (state.lastUpdated) $("#last-updated").textContent = timeAgo(state.lastUpdated);
  }, 1000);
}

init();
