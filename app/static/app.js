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

// ---------- 각 소스 1위 요약 (소스 많을 때 1위만 한눈에) ----------
function renderTopPicks(ordered, srcMeta) {
  const bar = $("#top-picks");
  bar.innerHTML = "";
  if (ordered.length < 2) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  bar.appendChild(el("div", "tp-title", `🥇 소스별 1위 (${ordered.length}곳)`));
  const row = el("div", "tp-row");
  for (const [source, list] of ordered) {
    const meta = srcMeta(source);
    const top = list[0];
    const chip = el("button", `tp-chip ${meta.source_type === "realtime" ? "rt" : "su"}`);
    chip.appendChild(el("span", "tp-src", meta.display_name || source));
    const ko = top.term_ko && top.term_ko.trim() && top.term_ko.trim() !== top.term.trim();
    chip.appendChild(el("span", "tp-term", ko ? top.term_ko : top.term));
    chip.title = ko ? `${top.term}\n→ ${top.term_ko}` : top.term;
    chip.onclick = () => {
      state.source = state.source === source ? "" : source;
      $("#source-filter").value = state.source;
      loadTrends();
    };
    row.appendChild(chip);
  }
  bar.appendChild(row);
}

// ---------- 소스별 그룹 렌더 (각 소스의 1위가 크게 보이도록) ----------
function renderGrouped(items) {
  const results = $("#results");
  results.innerHTML = "";
  const srcMeta = (name) => state.meta.sources.find((s) => s.name === name) || {};
  // 소스별 묶기 (API가 이미 source, rank 순으로 정렬해서 줌)
  const groups = new Map();
  for (const it of items) {
    if (!groups.has(it.source)) groups.set(it.source, []);
    groups.get(it.source).push(it);
  }
  // 그룹 순서: 실시간 급상승 먼저, 그 다음 항목 많은 순
  const ordered = [...groups.entries()].sort((a, b) => {
    const ta = srcMeta(a[0]).source_type === "realtime" ? 0 : 1;
    const tb = srcMeta(b[0]).source_type === "realtime" ? 0 : 1;
    if (ta !== tb) return ta - tb;
    return b[1].length - a[1].length;
  });
  renderTopPicks(ordered, srcMeta);
  const frag = document.createDocumentFragment();
  for (const [source, list] of ordered) {
    const meta = srcMeta(source);
    const group = el("section", "source-group");
    const head = el("div", "source-group-head");
    head.appendChild(el("span", "sg-name", meta.display_name || source));
    const st = meta.source_type === "realtime" ? "realtime" : "sustained";
    head.appendChild(el("span", `sg-badge ${st}`,
      st === "realtime" ? "🔥 실시간" : "📈 지속"));
    if (meta.risk === "high") head.appendChild(el("span", "sg-risk", "⚠️"));
    head.appendChild(el("span", "sg-count", `${list.length}건`));
    group.appendChild(head);
    const grid = el("div", "source-group-items");
    for (const it of list) grid.appendChild(renderCard(it));
    group.appendChild(grid);
    frag.appendChild(group);
  }
  results.appendChild(frag);
}

// ---------- 카드 ----------
function renderCard(item) {
  const first = item.rank === 1;
  const card = el("div", `card status-${item.status || item.source_type}${first ? " rank-first" : ""}`);
  const rankEl = el("div", `rank rank-${item.rank}`, first ? "🥇 1" : `${item.rank}`);
  card.appendChild(rankEl);

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
    if (!data.items.length) {
      results.innerHTML = "";
      $("#top-picks").classList.add("hidden");
      $("#empty-state").classList.remove("hidden");
    } else {
      $("#empty-state").classList.add("hidden");
      if (state.sort === "rank") {
        // 기본(순위)정렬: 소스별로 묶어 각 소스 1위가 잘 보이게
        results.classList.remove("flat");
        renderGrouped(data.items);
      } else {
        $("#top-picks").classList.add("hidden");
        results.innerHTML = "";
        results.classList.add("flat");
        const frag = document.createDocumentFragment();
        for (const it of data.items) frag.appendChild(renderCard(it));
        results.appendChild(frag);
      }
    }
    const srcNote = state.source ? " · 소스 필터 적용중" : "";
    $("#result-meta").textContent = `${data.count}건${srcNote}`;
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
  $("#reset-filters").addEventListener("click", () => {
    state.category = ""; state.source = ""; state.view = "all"; state.q = "";
    $("#search").value = "";
    $("#source-filter").value = "";
    for (const btn of $("#view-toggle").children) btn.classList.toggle("active", btn.dataset.view === "all");
    renderTabs();
    loadTrends();
  });
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
