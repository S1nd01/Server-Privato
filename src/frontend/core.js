// Funzioni di base: costruzione elementi, formattazione, chiamate API con token.
export const $ = (id) => document.getElementById(id);

// h("div", {class: "x", onclick: fn}, figli...). Mai attributi style=: la CSP li blocca (si usa el.style.x).
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el[k] = v;
    else if (k === "style") continue;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

// Come h(), ma per gli elementi SVG (servono per gli anelli d'uso).
export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v != null && v !== false) el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) if (c) el.append(c);
  return el;
}

// 90 -> "1 min", 7300 -> "2 h 1 min", 200000 -> "2 g 7 h"
export function fmtDuration(s) {
  if (s == null) return "—";
  if (s < 60) return "meno di 1 min";
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
  return `${Math.floor(s / 86400)} g ${Math.floor((s % 86400) / 3600)} h`;
}

export function fmtBytes(n) {
  if (n == null) return "?";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0).replace(".", ",") + " " + u[i];
}

export function ago(iso) {
  if (!iso) return "mai";
  const t = typeof iso === "number" ? iso * 1000 : Date.parse(iso);
  if (Number.isNaN(t)) return "mai";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 90) return "adesso";
  if (s < 5400) return Math.round(s / 60) + " minuti fa";
  if (s < 129600) return Math.round(s / 3600) + " ore fa";
  return Math.round(s / 86400) + " giorni fa";
}

export function fmtDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d);
}

// ---- token: sessionStorage (solo questa scheda) oppure localStorage ("Ricorda su questo dispositivo") ----
const KEY = "hs_token";
function store(kind) { try { return kind === "local" ? localStorage : sessionStorage; } catch { return null; } }
export function getToken() {
  for (const k of ["session", "local"]) {
    try { const v = store(k)?.getItem(KEY); if (v) return v; } catch { /* storage non disponibile */ }
  }
  return "";
}
export function setToken(t, remember) {
  clearToken();
  try { store(remember ? "local" : "session")?.setItem(KEY, t); } catch { /* ignora */ }
}
export function clearToken() {
  for (const k of ["session", "local"]) { try { store(k)?.removeItem(KEY); } catch { /* ignora */ } }
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

let authed = false;
export function setAuthed(v) { authed = v; }

export async function raw(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const t = getToken();
  if (t) headers["X-API-Token"] = t;
  let body;
  if (opts.json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  let res;
  try {
    res = await fetch("/api" + path, { method: opts.method || "GET", headers, body, cache: "no-store" });
  } catch {
    throw new ApiError("Server non raggiungibile", 0);
  }
  if (!res.ok) {
    if (res.status === 401 && authed) document.dispatchEvent(new Event("hs:auth-lost"));
    const err = await res.json().catch(() => ({}));
    const detail = typeof err.detail === "string" ? err.detail : Array.isArray(err.detail) ? "Dati non validi" : res.statusText;
    throw new ApiError(detail || "Errore", res.status);
  }
  return res;
}
export const api = async (path, opts) => (await raw(path, opts)).json();

// Una sola richiesta di prova PRIMA di tutte le altre (più richieste senza token farebbero scattare il limite dei tentativi).
// Ritorna "ok" | "token" (serve il token) | "locked" (troppi tentativi) | "offline".
export async function probe() {
  try {
    await api("/services");
    return "ok";
  } catch (e) {
    if (e.status === 401) return "token";
    if (e.status === 429) return "locked";
    if (e.status === 0) return "offline";
    return "ok"; // altri errori (es. Docker spento) li mostrano le sezioni
  }
}

// ---- notifiche brevi ----
let toastTimer;
export function toast(msg, kind = "info") {
  const el = $("toast");
  if (!el) return;
  el.textContent = msg;
  el.dataset.kind = kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, kind === "error" ? 6000 : 3000);
}
