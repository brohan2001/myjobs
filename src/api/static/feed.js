"use strict";
const $ = (id) => document.getElementById(id);
const state = { country: "", mode: "", cursor: null, loading: false };

function ago(iso) {
  if (!iso) return "";
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

function salary(s) {
  if (!s) return "";
  const fmt = (n) => n == null ? "" : new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
  const range = [fmt(s.min), fmt(s.max)].filter(Boolean).join("–");
  return `${s.currency || ""} ${range}${s.period ? " / " + s.period : ""}`.trim();
}

function row(job) {
  const li = document.createElement("li");
  const a = document.createElement("a");
  a.href = job.url; a.target = "_blank"; a.rel = "noopener noreferrer";
  a.textContent = job.title || "Untitled role";
  const where = job.locations.map((l) => l.name).filter(Boolean).join(" · ") || job.locations_raw.join(" · ");
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = [job.company.name, where, job.work_modes.join("/"), salary(job.salary), ago(job.first_seen_at)]
    .filter(Boolean).join(" — ");
  li.append(a, meta);
  return li;
}

async function load(reset) {
  if (state.loading) return;
  state.loading = true;
  if (reset) { state.cursor = null; $("jobs").replaceChildren(); }
  const p = new URLSearchParams({ limit: "50" });
  const q = $("q").value.trim();
  if (q) p.set("q", q);
  if (state.country) p.set("country", state.country);
  if (state.mode) p.set("work_mode", state.mode);
  if ($("since").value) p.set("since", $("since").value);
  if (state.cursor) p.set("cursor", state.cursor);
  try {
    const res = await fetch(`/api/v1/jobs?${p}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    const data = await res.json();
    data.jobs.forEach((j) => $("jobs").append(row(j)));
    state.cursor = data.next_cursor;
    $("more").hidden = !state.cursor;
    $("empty").hidden = $("jobs").children.length > 0;
  } catch (e) {
    $("empty").hidden = false;
    $("empty").textContent = `Couldn't load jobs (${e.message}).`;
  } finally {
    state.loading = false;
  }
}

async function stats() {
  try {
    const s = await (await fetch("/api/v1/stats")).json();
    $("stats").textContent = `${s.active_jobs.toLocaleString()} open jobs at ${s.companies_hiring.toLocaleString()} companies · `
      + `${s.new_last_24h.toLocaleString()} new today · updated ${ago(s.last_updated) || "not yet"}`;
  } catch { $("stats").textContent = ""; }
}

let debounce;
$("q").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => load(true), 300); });
$("since").addEventListener("change", () => load(true));
$("filters").addEventListener("submit", (e) => { e.preventDefault(); load(true); });
document.querySelectorAll(".chips button").forEach((b) => b.addEventListener("click", () => {
  if ("mode" in b.dataset) {
    state.mode = state.mode ? "" : b.dataset.mode;
    b.setAttribute("aria-pressed", String(!!state.mode));
  } else {
    state.country = b.dataset.country;
    document.querySelectorAll(".chips button[data-country]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
  }
  load(true);
}));
$("more").addEventListener("click", () => load(false));
stats(); load(true);
