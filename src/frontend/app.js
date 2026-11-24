import { $, h, probe, api, setToken, clearToken, getToken, setAuthed, toast } from "./core.js";
import { VIEWS, TITLES, led } from "./views.js";

const POLL_MS = 5000;
const ctx = {
  installPrompt: null,
  setServices,
  logout() { clearToken(); location.reload(); },
};

// ---- barra di LED nell'intestazione: una per servizio, si accendono in sequenza al primo caricamento ----
let firstLeds = true;
function setServices(services) {
  const strip = $("leds");
  strip.replaceChildren(...services.map((s, i) => {
    const l = led(s.status);
    l.title = s.name;
    if (firstLeds) { l.classList.add("boot"); l.style.setProperty("--i", String(i)); }
    return l;
  }));
  firstLeds = false;
  const up = services.filter((s) => s.status === "running").length;
  $("summary").textContent = up === services.length ? "Tutto in funzione" : up === 0 ? "Nessun servizio attivo" : `${up} servizi su ${services.length} attivi`;
}

// ---- schermate ----
let current = null; // { name, view }
let timer = null;
let running = false;

// #servizi, #backup... oppure #servizio/<id> (pagina Dettagli di un servizio: il resto dopo la barra e' il parametro)
function route() {
  const [n, ...rest] = location.hash.replace("#", "").split("/");
  let param = "";
  try { param = decodeURIComponent(rest.join("/")); } catch { /* indirizzo malformato: si ignora */ }
  if (n === "servizio" && param) return { name: n, param };
  return { name: VIEWS[n] && n !== "servizio" ? n : "servizi", param: "" };
}

async function show() {
  const { name, param } = route();
  if (current && current.name === name && current.param === param) return;
  const root = $("view");
  root.replaceChildren();
  current = { name, param, view: VIEWS[name](root, ctx, param) };
  document.title = `${TITLES[name]} - Homeserver`;
  const tab = name === "servizio" ? "servizi" : name;   // i Dettagli stanno sotto la scheda Servizi
  document.querySelectorAll("nav a").forEach((a) => {
    const on = a.getAttribute("href") === "#" + tab;
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
  await current.view.update();
}

async function tick() {
  if (!running || document.hidden || !current) return;
  await current.view.update();
}

function startApp() {
  if (running) return;
  running = true;
  setAuthed(true);
  $("gate").hidden = true;
  $("app").hidden = false;
  show();
  // le LED dell'intestazione si aggiornano anche fuori dalla schermata Servizi
  timer = setInterval(async () => {
    if (document.hidden) return;
    if (current && current.name !== "servizi" && current.name !== "servizio") { try { setServices(await api("/services")); } catch { /* si vede nelle schermate */ } }
    tick();
  }, POLL_MS);
}

function stopApp() {
  running = false;
  setAuthed(false);
  clearInterval(timer);
  current = null;
}

// ---- accesso con token ----
// La schermata iniziale (React, src/hero) compare solo a chi non e' autenticato e solo la prima volta dopo l'apertura della pagina:
// un token rifiutato o scaduto porta dritto al form. Se il modulo non si carica (build assente, rete) si va al form: l'accesso non dipende mai dall'hero.
let heroDone = false;

function showGate(message) {
  stopApp();
  $("app").hidden = true;
  if (!message && !heroDone) { showHero(); return; }
  openGate(message);
}

async function showHero() {
  const root = $("hero-root");
  $("gate").hidden = true;
  try {
    const { mountHero } = await import("/hero/hero.js");
    const unmount = await mountHero(root, {
      onEnter({ go, help } = {}) {
        heroDone = true;
        unmount();
        root.hidden = true;
        if (go) history.replaceState(null, "", "#" + go);   // la scheda che si apre dopo l'accesso
        openGate("");
        if (help) document.querySelector(".gate-help").open = true;
      },
    });
    root.hidden = false;   // solo a montaggio finito (stile caricato): niente lampo di pagina vuota
  } catch {
    heroDone = true;
    root.hidden = true;
    openGate("");
  }
}

function openGate(message) {
  $("gate").hidden = false;
  const msg = $("gate-msg");
  msg.textContent = message || "";
  msg.hidden = !message;
  $("token").focus();
}

$("gate-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const btn = ev.submitter || $("gate-form").querySelector("button");
  const value = $("token").value.trim();
  if (!value) return;
  btn.disabled = true;
  setToken(value, $("remember").checked);
  const r = await probe();
  btn.disabled = false;
  if (r === "ok") { $("token").value = ""; startApp(); }
  else if (r === "locked") { clearToken(); showGate("Troppi tentativi: aspetta un minuto e riprova."); }
  else if (r === "offline") { showGate("Il server non risponde."); }
  else { clearToken(); $("token").select(); showGate("Token non valido."); }
});

document.addEventListener("hs:auth-lost", () => { clearToken(); showGate("Il token non è più valido. Inseriscilo di nuovo."); });
window.addEventListener("hashchange", () => { if (running) show(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden && running) tick(); });

// ---- installazione come app ----
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); ctx.installPrompt = e; if (current && current.name === "rete") current.view.update(); });
window.addEventListener("appinstalled", () => { ctx.installPrompt = null; toast("App installata"); });

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* l'app funziona anche senza */ });
}

// ---- avvio: una sola richiesta di prova prima di tutto il resto ----
(async () => {
  const r = await probe();
  if (r === "ok") startApp();
  else if (r === "token") showGate(getToken() ? "Il token salvato non è più valido." : "");
  else if (r === "locked") showGate("Troppi tentativi: aspetta un minuto e ricarica la pagina.");
  else { startApp(); } // server spento: le schermate mostrano l'errore e si riprova da sole
})();
