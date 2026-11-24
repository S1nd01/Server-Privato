// Pezzi condivisi dalle schermate: LED, anello d'uso, scale di colore, etichette di stato.
import { h, svg, toast } from "./core.js";

export const STATUS_LABEL = {
  running: "Attivo", partial: "Parziale", stopped: "Fermo", not_created: "Non creato",
  failed: "Errore", exited: "Finito", created: "In avvio", restarting: "Riavvio",
};

export const HEALTH = { healthy: "Funziona bene", starting: "In avvio", unhealthy: "Non risponde" };
export const HEALTH_LED = { healthy: "running", starting: "partial", unhealthy: "failed" };

export const led = (state) => h("span", { class: "led", "data-s": state, "aria-hidden": "true" });

export function empty(text) { return h("p", { class: "empty" }, text); }
export function errorBox(e) { return h("p", { class: "notice", "data-kind": "error", role: "alert" }, e.message || String(e)); }
export function section(title, ...body) { return h("section", { class: "block" }, h("h2", {}, title), ...body); }

export function serviceUrl(s) {
  if (!s.url_port) return null;
  const onTs = location.hostname.endsWith(".ts.net");
  if (s.ts_only && !onTs) return null;
  const scheme = onTs ? "https" : s.scheme;
  return `${scheme}://${location.hostname}:${s.url_port}${s.path || ""}`;
}

export async function run(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, "error"); } finally { btn.disabled = false; }
}

export const level = (p) => (p == null ? "off" : p >= 85 ? "bad" : p >= 60 ? "warn" : "ok");
export const pct = (n) => (n == null ? "—" : (n < 10 ? n.toFixed(1) : String(Math.round(n))).replace(".", ",") + "%");
export const dec = (n) => String(n).replace(".", ",");

export function fact(label, value, sub, lead) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, lead || null, value, sub ? h("small", {}, sub) : null));
}

// ---- anello d'uso: la CPU del servizio rispetto a tutto il server ----
export const RING = 2 * Math.PI * 42; // circonferenza dell'anello (raggio 42 nel viewBox 100x100)

export function makeGauge() {
  const value = h("strong");
  const caption = h("small");
  const arc = svg("circle", { cx: 50, cy: 50, r: 42, class: "arc", transform: "rotate(-90 50 50)" });
  const el = h("div", { class: "gauge", role: "img" },
    svg("svg", { viewBox: "0 0 100 100", "aria-hidden": "true" }, svg("circle", { cx: 50, cy: 50, r: 42, class: "track" }), arc),
    h("div", { class: "gv" }, value, caption));
  function set({ p, big, small, word }, name) {
    el.dataset.level = level(p);
    arc.style.strokeDasharray = `${p == null ? 0 : (Math.min(100, Math.max(p, 1.5)) / 100) * RING} ${RING}`;
    value.className = word ? "word" : "";
    value.textContent = big;
    caption.textContent = small || "";
    el.setAttribute("aria-label", `${name}: ${big}${small ? " " + small : ""}`);
  }
  return { el, set };
}

// Cosa scrivere dentro l'anello, dato lo stato del servizio e le sue statistiche.
export function gaugeValues(s, st, isBusy) {
  const on = s.status === "running" || s.status === "partial";
  if (isBusy) return { p: null, big: "…", small: "un attimo", word: true };
  if (!on) return { p: null, big: STATUS_LABEL[s.status] || s.status, small: "", word: true };
  if (st && st.cpu_host_percent != null) return { p: st.cpu_host_percent, big: pct(st.cpu_host_percent), small: "uso CPU", word: false };
  return { p: null, big: "—", small: "uso CPU", word: false };
}
