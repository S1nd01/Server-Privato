// Le schermate. Ognuna esporta mount(root, ctx) -> { update() }. Pezzi condivisi: ui.js; pagina «Dettagli» di un servizio: detail.js.
import { h, api, ApiError, fmtBytes, fmtDate, fmtDuration, ago, toast } from "./core.js";
import { STATUS_LABEL, HEALTH, HEALTH_LED, led, empty, errorBox, section, serviceUrl, run, level, pct, dec, fact, makeGauge, gaugeValues } from "./ui.js";
import { servizio } from "./detail.js";

export { led };

// ---------------------------------------------------------------- Servizi
// barra con etichetta, valore e dettaglio (usata per il server)
function meter(label, p, value, sub) {
  const fill = h("i");
  fill.style.width = Math.max(0, Math.min(100, p ?? 0)) + "%";
  return h("div", { class: "meter" },
    h("div", { class: "mhead" }, h("span", {}, label), h("strong", {}, value)),
    h("div", { class: "bar", "data-level": level(p), role: "progressbar", "aria-label": label,
      "aria-valuenow": p == null ? null : String(Math.round(p)), "aria-valuemin": "0", "aria-valuemax": "100" }, fill),
    sub ? h("small", {}, sub) : null);
}

// Esito dell'ultimo controllo dei dischi (smart-check.sh -> /api/smart).
function smartFact(sm) {
  if (!sm) return null;
  if (!sm.configured) return fact("Dischi (SMART)", "Controllo non attivo", "vedi docs/smart.md", led("not_created"));
  const when = sm.at ? `controllati ${ago(sm.at)}` : "esito non leggibile";
  if (sm.level === "bad") return fact("Dischi (SMART)", "Guasto rilevato", sm.problems[0], led("failed"));
  if (sm.stale) return fact("Dischi (SMART)", "Controllo fermo", sm.at ? `ultimo esito ${ago(sm.at)}` : when, led("partial"));
  if (sm.level === "warn") return fact("Dischi (SMART)", "Da controllare", (sm.warnings[0] || sm.errors[0] || ""), led("partial"));
  return fact("Dischi (SMART)", "Nessun problema", `${sm.checked} ${sm.checked === 1 ? "disco" : "dischi"}, ${when}`, led("running"));
}

function renderHost(host, smart) {
  const memP = host.mem_total ? (host.mem_used / host.mem_total) * 100 : null;
  const tiles = [
    meter("Processore", host.cpu_percent, pct(host.cpu_percent),
      host.load ? `Carico ${host.load.map(dec).join(" · ")} su ${host.cores} core` : `${host.cores} core`),
    meter("Memoria", memP, pct(memP), `${fmtBytes(host.mem_used)} di ${fmtBytes(host.mem_total)}`),
    ...(host.disks || []).map((d) => {
      const p = d.total ? (d.used / d.total) * 100 : null;
      return meter(`Disco ${d.label}`, p, pct(p), `${fmtBytes(d.used)} di ${fmtBytes(d.total)}`);
    }),
  ];
  const facts = h("dl", { class: "mini" },
    fact("Server acceso da", fmtDuration(host.uptime_s)),
    host.temp_c != null ? fact("Temperatura", dec(host.temp_c) + " °C") : null,
    smartFact(smart));
  return [h("div", { class: "meters" }, tiles), facts];
}

// Una scheda per servizio: barra col nome e l'interruttore, anello d'uso, dati essenziali e il link «Dettagli».
// Manutenzione, log, grafico e risparmio stanno nella pagina Dettagli (detail.js), non qui.
// Si crea una volta sola e poi si aggiorna sul posto (patch): cosi' il focus non si perde a ogni aggiornamento.
function makeCard({ act }) {
  const state = { s: null, on: false };
  const ledSlot = h("span", { class: "ledslot" });
  const name = h("strong");
  const sw = h("button", { class: "switch", role: "switch", onclick: () => act(state.s, state.on ? "stop" : "start") }, h("span", { class: "knob" }));
  const desc = h("small", { class: "desc" });
  const gauge = makeGauge();
  const mini = h("dl", { class: "mini" });
  const more = h("a", { class: "btn" }, "Dettagli");
  const openLink = h("a", { class: "btn quiet", target: "_blank", rel: "noopener" }, "Apri");

  const el = h("article", { class: "card" },
    h("div", { class: "cardbar" }, ledSlot, h("span", { class: "text" }, name, desc), sw),
    gauge.el, mini,
    h("div", { class: "actions wrap" }, more, openLink));

  function patch(s, st, host, isBusy) {
    state.s = s;
    const on = s.status === "running" || s.status === "partial";
    state.on = on;
    el.className = "card" + (isBusy ? " busy" : "");
    ledSlot.replaceChildren(led(isBusy ? "partial" : s.status));
    name.textContent = s.name;
    desc.textContent = isBusy ? "Un attimo…" : `${STATUS_LABEL[s.status] || s.status}. ${s.description}`;
    desc.title = isBusy ? "" : s.description;   // la descrizione e' tagliata a 2 righe: per intero nel suggerimento

    const canToggle = on ? s.can_stop : true;
    sw.setAttribute("aria-checked", String(on));
    sw.setAttribute("aria-label", (on ? "Ferma " : "Avvia ") + s.name);
    sw.disabled = isBusy || !canToggle;
    sw.title = canToggle ? "" : "Questo servizio non si ferma dal pannello";

    gauge.set(gaugeValues(s, st, isBusy), s.name);

    // dati del servizio acceso
    mini.hidden = !(on && st);
    if (on && st) {
      mini.replaceChildren(
        fact("Memoria", st.mem_bytes != null ? fmtBytes(st.mem_bytes) : "—",
          host && host.mem_total && st.mem_bytes != null ? `${pct((st.mem_bytes / host.mem_total) * 100)} del server` : null),
        fact("Attivo da", fmtDuration(st.uptime_s)),
        fact("Salute", st.health ? HEALTH[st.health] || st.health : "Nessun controllo", null, st.health ? led(HEALTH_LED[st.health] || "partial") : null),
        fact("Riavvii automatici", String(st.restarts), st.restarts > 0 ? "è andato in errore" : null));
    }

    more.href = "#servizio/" + encodeURIComponent(s.id);
    more.setAttribute("aria-label", `Dettagli di ${s.name}`);
    more.dataset.sid = s.id;
    const url = serviceUrl(s);
    openLink.hidden = !url || !on;
    if (url) { openLink.href = url; openLink.setAttribute("aria-label", `Apri ${s.name} (nuova scheda)`); }
  }

  return { el, patch, link: more };
}

// Sostituisce i figli solo se l'elenco o l'ordine e' cambiato: cosi' il focus sui pulsanti non si perde a ogni aggiornamento.
function place(parent, els) {
  const cur = Array.from(parent.children);
  if (cur.length !== els.length || els.some((e, i) => e !== cur[i])) parent.replaceChildren(...els);
}

export function servizi(root, ctx) {
  const alerts = h("div", { class: "alerts", hidden: true });
  const hostBox = h("div", { class: "panel" }, h("p", { class: "empty" }, "Leggo i dati del server…"));
  const grid = h("div", { class: "cards" });
  const utilGrid = h("div", { class: "cards" });   // blocco Utility: i servizi con group "utility" (manutenzione, compressione...)
  const hostSection = section("Server", hostBox);
  const cardsSection = section("Servizi", grid);
  const utilSection = section("Utility", utilGrid);
  utilSection.hidden = true;
  // Modalità: pulsanti che accendono o spengono più gruppi insieme (definite in src/backend/app/services.py)
  const modesRow = h("div", { class: "modes" });
  const modesNote = h("p", { class: "hint" });
  const modesSection = section("Modalità", modesRow, modesNote);
  modesSection.hidden = true;
  // su schermo largo queste sezioni occupano tutta la larghezza: le card si affiancano e vanno a capo
  for (const el of [alerts, hostSection, modesSection, cardsSection, utilSection]) el.classList.add("wide");
  root.append(alerts, hostSection, modesSection, cardsSection, utilSection);
  const cards = new Map();
  const busy = new Set();
  let last = null;
  let alertKey = "";

  async function act(s, action) {
    busy.add(s.id);
    if (last) render();
    try { await api(`/services/${s.id}/${action}`, { method: "POST" }); }
    catch (e) { toast(e.message, "error"); }
    busy.delete(s.id);
    await update();
  }

  // ---- modalità ----
  let modeDefs = null;   // si leggono una volta sola: non cambiano e non costano una chiamata a Docker
  let modeBusy = false;
  const modeBtns = new Map();

  // Attiva se tutti i suoi gruppi (quelli già creati) sono nello stato che la modalità produce.
  function modeActive(m, services) {
    const want = m.action === "stop" ? "stopped" : "running";
    const sts = m.services.map((id) => services.find((s) => s.id === id)).filter((s) => s && s.status !== "not_created");
    return sts.length > 0 && sts.every((s) => s.status === want);
  }

  function renderModes(services) {
    if (!modeDefs || !modeDefs.length) { modesSection.hidden = true; return; }
    modesSection.hidden = false;
    const btns = modeDefs.map((m) => {
      let b = modeBtns.get(m.id);
      if (!b) { b = h("button", { class: "btn", type: "button", onclick: () => applyMode(m) }); modeBtns.set(m.id, b); }
      b.textContent = m.name;
      b.title = m.description;
      b.setAttribute("aria-pressed", String(modeActive(m, services)));
      b.disabled = modeBusy;
      return b;
    });
    place(modesRow, btns);
    const on = modeDefs.find((m) => modeActive(m, services));
    modesNote.textContent = on ? on.description : modeDefs.map((m) => `${m.name}: ${m.description}`).join(" · ");
  }

  async function applyMode(m) {
    modeBusy = true;
    m.services.forEach((id) => busy.add(id));
    if (last) render();
    try {
      const r = await api(`/modes/${m.id}/apply`, { method: "POST" });
      toast(`Modalità ${m.name} applicata` + (r.skipped && r.skipped.length ? ` (${r.skipped.length} container non creati, saltati)` : ""));
    } catch (e) { toast(e.message, "error"); }
    modeBusy = false;
    m.services.forEach((id) => busy.delete(id));
    await update();
  }

  function renderAlerts(services, st, smart) {
    const msgs = [];
    services.forEach((s) => {
      const x = st && st.services && st.services[s.id];
      if (s.status === "partial") msgs.push(`${s.name} è acceso solo in parte: apri i dettagli per vedere quale pezzo è fermo.`);
      if (x && x.health === "unhealthy") msgs.push(`${s.name} non supera il controllo di salute.`);
    });
    const setup = st && st.setup;
    if (setup && (setup.missing.length || setup.root_owned.length)) {
      const bad = [...setup.root_owned, ...setup.missing];
      msgs.push(`Alcune cartelle dei dati mancano o non sono tue (${bad.slice(0, 4).join(", ")}${bad.length > 4 ? "…" : ""}). Dal terminale del server lancia ./src/scripts/sync-env.sh.`);
    }
    const host = st && st.host;
    if (host) {
      if (host.mem_total && host.mem_used / host.mem_total >= 0.9) msgs.push("La memoria del server è quasi piena.");
      (host.disks || []).forEach((d) => { if (d.total && d.used / d.total >= 0.9) msgs.push(`Il disco ${d.label} è quasi pieno.`); });
      if (host.temp_c != null && host.temp_c >= 75) msgs.push(`Il server è caldo: ${dec(host.temp_c)} °C.`);
    }
    if (smart && smart.configured) {
      smart.problems.slice(0, 3).forEach((m) => msgs.push(`Disco in pericolo: ${m}`));
      smart.warnings.slice(0, 3).forEach((m) => msgs.push(`Disco da controllare: ${m}`));
      smart.errors.slice(0, 2).forEach((m) => msgs.push(`Controllo dei dischi: ${m}`));
      if (smart.stale && smart.at) msgs.push(`Il controllo dei dischi non gira da ${ago(smart.at).replace(" fa", "")}: guarda il cron di smart-check.sh.`);
    }
    const key = msgs.join("|");
    if (key === alertKey) return; // non ricreo gli avvisi se non cambiano (i lettori di schermo non li rileggono)
    alertKey = key;
    alerts.hidden = msgs.length === 0;
    alerts.replaceChildren(...msgs.map((m) => h("p", { class: "notice", "data-kind": "warn", role: "alert" }, m)));
  }

  function render() {
    const { services, st, smart } = last;
    const host = st && st.host;
    hostBox.replaceChildren(...(host ? renderHost(host, smart) : [h("p", { class: "empty" }, "Dati del server non disponibili.")]));
    const main = [], util = [];
    services.forEach((s) => {
      let c = cards.get(s.id);
      if (!c) { c = makeCard({ act }); cards.set(s.id, c); }
      c.patch(s, st && st.services && st.services[s.id], host, busy.has(s.id));
      (s.group === "utility" ? util : main).push(c.el);
    });
    place(grid, main);
    place(utilGrid, util);
    utilSection.hidden = util.length === 0;
    renderModes(services);
    renderAlerts(services, st, smart);
    if (ctx.focusSid) {   // tornando da «Dettagli» il focus riparte dal link del servizio che si stava guardando
      const c = cards.get(ctx.focusSid);
      ctx.focusSid = null;
      if (c) c.link.focus({ preventScroll: false });
    }
  }

  // Lo stato dei servizi e' leggero (una sola chiamata a Docker) e si rinnova a ogni giro; le statistiche costano di piu'
  // e basta rileggerle ogni 15 secondi, o subito se un servizio cambia stato (acceso, spento, riavviato).
  const STATS_EVERY_MS = 15000;
  let statsAt = 0;
  let statesKey = "";
  async function update() {
    try {
      const services = await api("/services");
      if (!modeDefs) modeDefs = await api("/modes").catch(() => null);   // se manca, la sezione resta nascosta e si riprova al giro dopo
      const key = services.map((s) => s.id + s.status).join();
      let st = last ? last.st : null;
      let smart = last ? last.smart : null;
      if (key !== statesKey || Date.now() - statsAt >= STATS_EVERY_MS) {
        // le statistiche e l'esito SMART sono un di piu': se mancano si vedono comunque i servizi
        const [fresh, sm] = await Promise.all([api("/stats").catch(() => null), api("/smart").catch(() => null)]);
        if (fresh) { st = fresh; statsAt = Date.now(); }
        if (sm) smart = sm;
        statesKey = key;
      }
      last = { services, st, smart };
      render();
      ctx.setServices(services);
    } catch (e) {
      cards.clear();
      last = null;
      grid.replaceChildren(errorBox(e));
      utilGrid.replaceChildren();
      utilSection.hidden = true;
      modesSection.hidden = true;
    }
  }
  return { update };
}

// ---------------------------------------------------------------- Backup
const JOB_LABEL = { init: "Preparazione archivio", backup: "Backup", forget: "Pulizia vecchie copie", check: "Controllo integrità" };
const RESULT_LABEL = { running: "in corso", ok: "riuscito", warning: "riuscito, ma alcuni file non erano leggibili", failed: "non riuscito" };

export function backup(root, ctx) {
  const statusBox = h("div", { class: "panel" });
  const jobBox = h("div", { class: "panel", hidden: true });
  const snapBox = h("ul", { class: "rows plain" });
  const snapSection = section("Copie salvate", snapBox);
  snapSection.hidden = true;
  root.append(section("Backup", statusBox), jobBox, snapSection);

  let confirming = false;
  let showLogs = false;
  let lastJobKey = "";

  async function start(btn, kind) {
    await run(btn, async () => {
      const j = await api("/backup/jobs", { method: "POST", json: { kind } });
      (j.warnings || []).forEach((w) => toast(w));
      toast(`${JOB_LABEL[kind]} avviato`);
      confirming = false;
      showLogs = true;
      await update();
    });
  }

  function renderStatus(st) {
    if (!st.configured) {
      return [
        h("p", { class: "lead" }, "Il backup non è ancora attivo."),
        h("ul", { class: "bullets" }, st.problems.map((p) => h("li", {}, p))),
        h("p", { class: "hint" }, "Si attiva compilando RESTIC_REPO_DIR e RESTIC_PASSWORD_FILE nel file .env (istruzioni in docs/restic.md), poi `docker compose up -d --build`. Per l'archivio su un disco esterno: ./src/scripts/backup-disco.sh."),
      ];
    }
    const running = st.job && st.job.result === "running";
    const diskGone = !!(st.disk && !st.disk.present);
    const mk = (label, kind, cls = "btn") => h("button", { class: cls, disabled: running, onclick: (e) => start(e.currentTarget, kind) }, label);
    const actions = diskGone ? [] : !st.initialized
      ? [mk("Prepara l'archivio", "init", "btn primary")]
      : [mk("Esegui backup ora", "backup", "btn primary"), mk("Controlla integrità", "check"),
         confirming
           ? h("span", { class: "confirm" }, h("span", {}, `Tengo ${st.keep.daily} giorni, ${st.keep.weekly} settimane, ${st.keep.monthly} mesi e cancello il resto. Confermi?`),
               mk("Sì, pulisci", "forget", "btn danger"), h("button", { class: "btn quiet", onclick: () => { confirming = false; update(); } }, "Annulla"))
           : h("button", { class: "btn", disabled: running, onclick: () => { confirming = true; update(); } }, "Pulisci vecchie copie")];
    return [
      h("dl", { class: "facts" },
        h("div", {}, h("dt", {}, "Ultima copia"), h("dd", {}, st.last_backup_at ? `${ago(st.last_backup_at)} (${fmtDate(st.last_backup_at)})` : st.initialized === false ? "archivio da preparare" : "ancora nessuna")),
        h("div", {}, h("dt", {}, "Quando parte"), h("dd", {}, "solo quando lo avvii tu, da qui")),
        h("div", {}, h("dt", {}, "Dove"), h("dd", {}, (st.repo || "") + (st.disk ? (st.disk.present ? " (disco collegato)" : " (disco NON collegato)") : ""))),
        h("div", {}, h("dt", {}, "Cosa si salva"), h("dd", {}, st.sources.map((s) => s.path + (s.exists ? "" : " (non trovata)")).join(", ")))),
      ...(diskGone ? [h("p", { class: "notice", "data-kind": "warn" }, `Il disco di backup non è collegato (lo cerco in ${st.disk.path}). Collegalo e montalo per fare un backup o vedere le copie salvate.`)] : []),
      ...(st.stale && !diskGone ? [h("p", { class: "notice", "data-kind": "warn" }, st.last_backup_at ? `L'ultima copia risale a ${st.age_days} giorni fa: è ora di farne una.` : "Non c'è ancora nessuna copia: fai il primo backup.")] : []),
      ...(st.stale && diskGone ? [h("p", { class: "notice", "data-kind": "warn" }, st.last_backup_at ? `L'ultima copia risale a ${st.age_days} giorni fa: collega il disco e fanne una.` : "Non c'è ancora nessuna copia.")] : []),
      h("div", { class: "actions wrap" }, actions),
    ];
  }

  function renderJob(job, st) {
    if (!job) { jobBox.hidden = true; return; }
    jobBox.hidden = false;
    const state = job.result === "running" ? "partial" : job.result === "failed" ? "failed" : "running";
    const pre = h("pre", { class: "log", hidden: !showLogs }, "…");
    if (showLogs) api("/backup/jobs/current/logs?tail=60").then((r) => { pre.textContent = r.logs.trim() || "Nessun messaggio"; pre.scrollTop = pre.scrollHeight; }).catch(() => {});
    jobBox.replaceChildren(
      h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led(state), h("span", { class: "text" }, h("strong", {}, JOB_LABEL[job.kind] || "Operazione"), h("small", {}, `${RESULT_LABEL[job.result] || job.result}${job.finished_at && job.result !== "running" ? ", " + ago(job.finished_at) : ""}`))),
        h("button", { class: "btn quiet", onclick: () => { showLogs = !showLogs; update(); } }, showLogs ? "Nascondi log" : "Log")),
      ...(st && st.disk && job.kind === "backup" && (job.result === "ok" || job.result === "warning")
        ? [h("p", { class: "hint" }, "Finito: ora puoi scollegare il disco. Espellilo prima dal sistema, poi tienilo spento o altrove.")] : []),
      pre);
  }

  async function loadSnapshots(st) {
    const idle = !st.job || st.job.result !== "running";
    if (!st.initialized || !idle) { if (!st.initialized) snapSection.hidden = true; return; }
    try {
      const snaps = await api("/backup/snapshots");
      snapSection.hidden = false;
      snapBox.replaceChildren(...(snaps.length ? snaps.map((s) => h("li", { class: "row" }, h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led("running"), h("span", { class: "text" }, h("strong", {}, fmtDate(s.time)),
          h("small", {}, `${s.id}${s.added_bytes != null ? ", nuovi " + fmtBytes(s.added_bytes) : ""}${s.total_bytes != null ? ", totale " + fmtBytes(s.total_bytes) : ""}`)))))) : [empty("Nessuna copia ancora.")]));
    } catch (e) {
      if (e.status !== 409) { snapSection.hidden = false; snapBox.replaceChildren(errorBox(e)); }
    }
  }

  async function update() {
    try {
      const st = await api("/backup/status");
      statusBox.replaceChildren(...renderStatus(st));
      const key = st.job ? `${st.job.kind}|${st.job.result}|${st.job.finished_at}` : "";
      renderJob(st.job, st);
      if (key !== lastJobKey || snapSection.hidden) { lastJobKey = key; await loadSnapshots(st); }
    } catch (e) { statusBox.replaceChildren(errorBox(e)); }
  }
  return { update };
}

// ---------------------------------------------------------------- Rete (Tailscale + questa app)
export function rete(root, ctx) {
  const tsBox = h("div", { class: "panel" });
  const peersBox = h("ul", { class: "rows plain" });
  const peersSection = section("Dispositivi nella tua rete", peersBox);
  peersSection.hidden = true;
  const appBox = h("div", { class: "panel" });
  root.append(section("Accesso da fuori casa", tsBox), peersSection, section("Questa app", appBox));

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast("Indirizzo copiato"); } catch { toast("Copia non riuscita: selezionalo a mano", "error"); }
  };

  function renderApp() {
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const kids = [];
    if (standalone) kids.push(h("p", { class: "lead" }, "Stai usando l'app installata."));
    else if (!window.isSecureContext) kids.push(h("p", { class: "notice", "data-kind": "warn" }, "Per installarla serve una connessione protetta (HTTPS). Aprila dall'indirizzo https della sezione qui sopra."));
    else if (ctx.installPrompt) {
      kids.push(h("p", {}, "Installala per averla come un'app sul telefono."), h("button", { class: "btn primary", onclick: async () => { const p = ctx.installPrompt; ctx.installPrompt = null; p.prompt(); await p.userChoice.catch(() => {}); update(); } }, "Installa l'app"));
    } else if (ios) kids.push(h("p", {}, "Su iPhone: tocca il tasto Condividi in Safari, poi «Aggiungi alla schermata Home»."));
    else kids.push(h("p", {}, "Dal menu del browser scegli «Installa app» oppure «Aggiungi a schermata Home»."));
    kids.push(h("div", { class: "actions" }, h("button", { class: "btn quiet", onclick: () => ctx.logout() }, "Esci da questo dispositivo")));
    appBox.replaceChildren(...kids);
  }

  async function update() {
    renderApp();
    try {
      const t = await api("/tailscale/status");
      const kids = [];
      const ok = t.state === "Running";
      kids.push(h("div", { class: "line" }, h("div", { class: "rowmain static" }, led(ok ? "running" : t.state === "NeedsLogin" ? "partial" : "stopped"),
        h("span", { class: "text" }, h("strong", {}, ok ? "Collegato a Tailscale" : t.state === "NeedsLogin" ? "Serve il login" : `Stato: ${t.state}`),
          h("small", {}, ok ? (t.tailnet || "") : "")))));
      if (t.login_url) kids.push(h("p", {}, "Apri questo link per collegare il server al tuo account Tailscale."), h("a", { class: "btn primary", href: t.login_url, target: "_blank", rel: "noopener" }, "Accedi a Tailscale"));
      if (ok && t.https_url) {
        kids.push(h("p", { class: "lead" }, "Dal telefono, con Tailscale acceso, apri:"), h("p", { class: "url" }, t.https_url),
          h("div", { class: "actions wrap" }, h("a", { class: "btn primary", href: t.https_url, target: "_blank", rel: "noopener" }, "Apri"), h("button", { class: "btn", onclick: () => copy(t.https_url) }, "Copia indirizzo")));
      } else if (ok) {
        kids.push(h("p", { class: "notice", "data-kind": "warn" }, "I certificati HTTPS non sono attivi: nel pannello di Tailscale (Settings, DNS) abilita MagicDNS e HTTPS Certificates. Senza HTTPS l'app non si può installare."));
      }
      (t.health || []).forEach((m) => kids.push(h("p", { class: "notice", "data-kind": "warn" }, m)));
      tsBox.replaceChildren(...kids);
      peersSection.hidden = !(t.peers && t.peers.length);
      peersBox.replaceChildren(...(t.peers || []).map((p) => h("li", { class: "row" }, h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led(p.online ? "running" : "stopped"),
          h("span", { class: "text" }, h("strong", {}, p.name), h("small", {}, `${p.online ? "Online" : "Visto " + ago(p.last_seen)}${p.os ? ", " + p.os : ""}`)))))));
    } catch (e) {
      peersSection.hidden = true;
      tsBox.replaceChildren(errorBox(e instanceof ApiError ? e : new Error(String(e))));
    }
  }
  return { update };
}


// ---------------------------------------------------------------- Accessi (dove stanno le credenziali e come si recuperano)
// Il pannello non mostra e non reimposta nessuna password: elenca i comandi da lanciare dal terminale del server (docs/credenziali.md).
const RECOVERY_LABEL = { mostra: "Si può rileggere", reimposta: "Si reimposta", impossibile: "Non recuperabile" };
const RECOVERY_LED = { mostra: "running", reimposta: "partial", impossibile: "failed" };

export function accessi(root, ctx) {
  const intro = h("div", { class: "panel" }, empty("Carico l'elenco…"));
  const list = h("ul", { class: "rows plain" });
  root.append(section("Accessi e recupero", intro), list);

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast("Comando copiato"); } catch { toast("Copia non riuscita: selezionalo a mano", "error"); }
  };

  function item(it) {
    const kids = [
      h("div", { class: "line" }, h("div", { class: "rowmain static" }, led(RECOVERY_LED[it.recovery] || "partial"),
        h("span", { class: "text" }, h("strong", {}, it.name), h("small", {}, `${RECOVERY_LABEL[it.recovery] || it.recovery}. ${it.where}`)))),
    ];
    if (it.ok === false) kids.push(h("p", { class: "notice", "data-kind": "warn" }, it.id === "pannello"
      ? "Il pannello non ha un token: chiunque lo raggiunga può comandare Docker. Genera il token con gen-api-token.sh."
      : "Il file della passphrase non risulta configurato (vedi docs/restic.md)."));
    if (it.note) kids.push(h("p", { class: "hint" }, it.note));
    if (it.command) kids.push(h("div", { class: "cmd" }, h("code", {}, it.command), h("button", { class: "btn quiet", onclick: () => copy(it.command) }, "Copia")));
    return h("li", { class: "row" }, ...kids);
  }

  async function update() {
    try {
      const d = await api("/access");
      intro.replaceChildren(
        h("p", { class: "lead" }, "Le password non si leggono e non si cambiano da qui."),
        h("p", { class: "hint" }, "Il recupero si fa dal terminale del server, nella cartella del progetto: così chi ruba il token del pannello non ottiene anche tutte le altre credenziali. Ogni voce mostra il comando da lanciare."),
        h("p", { class: "hint" }, "Senza argomenti lo script elenca tutti i comandi: ", h("code", {}, d.script)));
      list.replaceChildren(...d.items.map(item));
    } catch (e) { intro.replaceChildren(errorBox(e)); list.replaceChildren(); }
  }
  return { update };
}

export const VIEWS = { servizi, servizio, backup, rete, accessi };
export const TITLES = { servizi: "Servizi", servizio: "Dettagli", backup: "Backup", rete: "Rete", accessi: "Accessi" };
