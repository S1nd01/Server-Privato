// Le quattro schermate. Ognuna esporta mount(root, ctx) -> { update(), tick }.
import { h, api, ApiError, fmtBytes, fmtDate, ago, toast } from "./core.js";

const STATUS_LABEL = {
  running: "Attivo", partial: "Parziale", stopped: "Fermo", not_created: "Non creato",
  failed: "Errore", exited: "Finito", created: "In avvio", restarting: "Riavvio",
};

export const led = (state) => h("span", { class: "led", "data-s": state, "aria-hidden": "true" });

function empty(text) { return h("p", { class: "empty" }, text); }
function errorBox(e) { return h("p", { class: "notice", "data-kind": "error", role: "alert" }, e.message || String(e)); }
function section(title, ...body) { return h("section", { class: "block" }, h("h2", {}, title), ...body); }

function serviceUrl(s) {
  if (!s.url_port) return null;
  const onTs = location.hostname.endsWith(".ts.net");
  const scheme = onTs ? "https" : s.scheme;
  return `${scheme}://${location.hostname}:${s.url_port}${s.path || ""}`;
}

async function run(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, "error"); } finally { btn.disabled = false; }
}

// ---------------------------------------------------------------- Servizi
const openServices = new Set();

export function servizi(root, ctx) {
  const list = h("ul", { class: "rows" });
  root.append(section("Servizi", list));
  let busy = new Set();

  async function act(s, action) {
    busy.add(s.id);
    await update(false);
    try { await api(`/services/${s.id}/${action}`, { method: "POST" }); }
    catch (e) { toast(e.message, "error"); }
    busy.delete(s.id);
    await update();
  }

  function row(s) {
    const open = openServices.has(s.id);
    const on = s.status === "running" || s.status === "partial";
    const url = serviceUrl(s);
    const isBusy = busy.has(s.id);
    const canToggle = on ? s.can_stop : true;
    const sw = h("button", {
      class: "switch", role: "switch", "aria-checked": String(on), disabled: isBusy || !canToggle,
      "aria-label": (on ? "Ferma " : "Avvia ") + s.name,
      title: !canToggle ? "Questo servizio non si ferma dal pannello" : null,
      onclick: () => act(s, on ? "stop" : "start"),
    }, h("span", { class: "knob" }));
    const detail = h("div", { class: "detail", hidden: !open },
      h("ul", { class: "containers" }, s.containers.map((c) => h("li", {}, led(c.status), h("span", {}, c.name), h("small", {}, STATUS_LABEL[c.status] || c.status)))),
      h("div", { class: "actions" },
        url ? h("a", { class: "btn", href: url, target: "_blank", rel: "noopener" }, "Apri") : null,
        s.can_stop ? h("button", { class: "btn", disabled: isBusy || s.status === "not_created", onclick: () => act(s, "restart") }, "Riavvia") : null));
    const head = h("button", {
      class: "rowmain", "aria-expanded": String(open),
      onclick: () => { open ? openServices.delete(s.id) : openServices.add(s.id); detail.hidden = open; head.setAttribute("aria-expanded", String(!open)); },
    }, led(isBusy ? "partial" : s.status),
      h("span", { class: "text" }, h("strong", {}, s.name), h("small", {}, isBusy ? "Un attimo…" : `${STATUS_LABEL[s.status] || s.status}. ${s.description}`)));
    return h("li", { class: "row" + (isBusy ? " busy" : "") }, h("div", { class: "line" }, head, sw), detail);
  }

  async function update() {
    try {
      const services = await api("/services");
      ctx.setServices(services);
      list.replaceChildren(...services.map(row));
    } catch (e) { list.replaceChildren(errorBox(e)); }
  }
  return { update };
}

// ---------------------------------------------------------------- Steam
const openLogs = new Set();

export function steam(root, ctx) {
  const appid = h("input", { id: "appid", name: "appid", type: "number", inputmode: "numeric", min: "1", required: true, placeholder: "es. 730", autocomplete: "off" });
  const platform = h("select", { id: "platform", name: "platform" }, ["windows", "linux", "macos"].map((p) => h("option", { value: p }, p[0].toUpperCase() + p.slice(1))));
  const login = h("input", { id: "login", name: "login", type: "text", placeholder: "anonymous", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Scarica");
  const form = h("form", { class: "form", onsubmit: async (ev) => {
    ev.preventDefault();
    await run(submit, async () => {
      const id = Number(appid.value);
      await api("/steam/downloads", { method: "POST", json: { appid: id, platform: platform.value, login: login.value.trim() || "anonymous" } });
      openLogs.add(id);
      toast("Download avviato");
      await update();
    });
  } },
    h("label", { for: "appid" }, "AppID", appid, h("small", {}, "Il numero nell'indirizzo dello store Steam")),
    h("label", { for: "platform" }, "Sistema", platform),
    h("label", { for: "login" }, "Account", login, h("small", {}, "Vuoto = anonimo (solo giochi gratuiti o server dedicati)")),
    submit);
  const downloads = h("ul", { class: "rows" });
  const library = h("ul", { class: "rows plain" });
  root.append(section("Nuovo download", form), section("Download", downloads), section("Libreria", library));

  let lastRunning = -1;

  function dlRow(d) {
    const done = d.status === "exited" && d.exit_code === 0;
    const failed = d.status === "exited" && d.exit_code !== 0;
    const state = done ? "running" : failed ? "failed" : d.status === "running" ? "partial" : "stopped";
    const label = done ? "Completato" : failed ? `Errore (codice ${d.exit_code})` : d.status === "running" ? (d.progress != null ? `Download in corso, ${String(d.progress).replace(".", ",")}%` : "In corso") : d.status;
    const open = openLogs.has(d.appid);
    const pre = h("pre", { class: "log", hidden: !open }, "…");
    if (open) api(`/steam/downloads/${d.appid}/logs?tail=30`).then((r) => { pre.textContent = r.logs.trim() || "Nessun messaggio"; pre.scrollTop = pre.scrollHeight; }).catch(() => {});
    const bar = d.status === "running" && d.progress != null
      ? (() => { const i = h("i"); i.style.width = Math.min(100, d.progress) + "%"; return h("div", { class: "bar", role: "progressbar", "aria-valuenow": String(d.progress), "aria-valuemin": "0", "aria-valuemax": "100" }, i); })()
      : null;
    const size = d.status === "running" && d.total_bytes ? h("small", {}, `${fmtBytes(d.downloaded_bytes)} di ${fmtBytes(d.total_bytes)}`) : null;
    return h("li", { class: "row" },
      h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led(state), h("span", { class: "text" }, h("strong", {}, `App ${d.appid}`), h("small", {}, `${label}. ${d.platform || ""}`), size)),
        h("button", { class: "btn quiet", onclick: () => { open ? openLogs.delete(d.appid) : openLogs.add(d.appid); update(); } }, open ? "Nascondi log" : "Log"),
        h("button", { class: "btn quiet", onclick: (e) => run(e.currentTarget, async () => { await api(`/steam/downloads/${d.appid}`, { method: "DELETE" }); openLogs.delete(d.appid); await update(); }) }, d.status === "running" ? "Annulla" : "Rimuovi")),
      bar, pre);
  }

  async function loadLibrary() {
    try {
      const games = await api("/steam/library");
      library.replaceChildren(...(games.length ? games.map((g) => h("li", { class: "row" }, h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led(g.installed ? "running" : "partial"),
          h("span", { class: "text" }, h("strong", {}, g.name || `App ${g.appid}`), h("small", {}, `${g.installed ? "Installato" : "Incompleto"}${g.size_bytes != null ? ", " + fmtBytes(g.size_bytes) : ""}`)))))) : [empty("Nessun gioco scaricato.")]));
    } catch (e) { library.replaceChildren(errorBox(e)); }
  }

  async function update() {
    try {
      const items = await api("/steam/downloads");
      downloads.replaceChildren(...(items.length ? items.map(dlRow) : [empty("Nessun download.")]));
      const running = items.filter((d) => d.status === "running").length;
      if (running !== lastRunning) { lastRunning = running; await loadLibrary(); }
    } catch (e) { downloads.replaceChildren(errorBox(e)); }
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
        h("p", { class: "hint" }, "Si attiva compilando RESTIC_REPO_DIR e RESTIC_PASSWORD_FILE nel file .env (istruzioni in docs/restic.md), poi `docker compose up -d --build`."),
      ];
    }
    const running = st.job && st.job.result === "running";
    const mk = (label, kind, cls = "btn") => h("button", { class: cls, disabled: running, onclick: (e) => start(e.currentTarget, kind) }, label);
    const actions = !st.initialized
      ? [mk("Prepara l'archivio", "init", "btn primary")]
      : [mk("Esegui backup ora", "backup", "btn primary"), mk("Controlla integrità", "check"),
         confirming
           ? h("span", { class: "confirm" }, h("span", {}, `Tengo ${st.keep.daily} giorni, ${st.keep.weekly} settimane, ${st.keep.monthly} mesi e cancello il resto. Confermi?`),
               mk("Sì, pulisci", "forget", "btn danger"), h("button", { class: "btn quiet", onclick: () => { confirming = false; update(); } }, "Annulla"))
           : h("button", { class: "btn", disabled: running, onclick: () => { confirming = true; update(); } }, "Pulisci vecchie copie")];
    return [
      h("dl", { class: "facts" },
        h("div", {}, h("dt", {}, "Ultima copia"), h("dd", {}, st.initialized ? (st.last_backup_at ? `${ago(st.last_backup_at)} (${fmtDate(st.last_backup_at)})` : "ancora nessuna") : "archivio da preparare")),
        h("div", {}, h("dt", {}, "Automatico"), h("dd", {}, st.schedule ? `ogni giorno alle ${st.schedule}` : "disattivato")),
        h("div", {}, h("dt", {}, "Dove"), h("dd", {}, st.repo || "")),
        h("div", {}, h("dt", {}, "Cosa si salva"), h("dd", {}, st.sources.map((s) => s.path + (s.exists ? "" : " (non trovata)")).join(", ")))),
      h("div", { class: "actions wrap" }, actions),
    ];
  }

  function renderJob(job) {
    if (!job) { jobBox.hidden = true; return; }
    jobBox.hidden = false;
    const state = job.result === "running" ? "partial" : job.result === "failed" ? "failed" : "running";
    const pre = h("pre", { class: "log", hidden: !showLogs }, "…");
    if (showLogs) api("/backup/jobs/current/logs?tail=60").then((r) => { pre.textContent = r.logs.trim() || "Nessun messaggio"; pre.scrollTop = pre.scrollHeight; }).catch(() => {});
    jobBox.replaceChildren(
      h("div", { class: "line" },
        h("div", { class: "rowmain static" }, led(state), h("span", { class: "text" }, h("strong", {}, JOB_LABEL[job.kind] || "Operazione"), h("small", {}, `${RESULT_LABEL[job.result] || job.result}${job.finished_at && job.result !== "running" ? ", " + ago(job.finished_at) : ""}`))),
        h("button", { class: "btn quiet", onclick: () => { showLogs = !showLogs; update(); } }, showLogs ? "Nascondi log" : "Log")),
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
      renderJob(st.job);
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

export const VIEWS = { servizi, steam, backup, rete };
export const TITLES = { servizi: "Servizi", steam: "Steam", backup: "Backup", rete: "Rete" };
