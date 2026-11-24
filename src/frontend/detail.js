// Pagina «Dettagli» di un servizio (#servizio/<id>): anello d'uso, grafico delle risorse, spegnimento, risparmio, contenitori,
// manutenzione e log. Le card della schermata Servizi tengono solo interruttore e stato; tutto il resto sta qui.
import { h, svg, api, fmtBytes, fmtDate, fmtDuration, ago, toast } from "./core.js";
import { STATUS_LABEL, HEALTH, HEALTH_LED, led, errorBox, section, serviceUrl, pct, dec, fact, makeGauge, gaugeValues, run } from "./ui.js";

const WINDOWS = [{ s: 900, label: "15 minuti" }, { s: 3600, label: "1 ora" }];
const SERIES = [
  { key: "cpu", cls: "s-cpu", label: "CPU del servizio", get: (p) => p.cpu },
  { key: "mem", cls: "s-mem", label: "RAM del servizio", get: (p) => p.mem_pct },
  { key: "host", cls: "s-host", label: "CPU di tutto il server", get: (p) => p.host_cpu },
];
const GAP_S = 60;   // se fra due letture passa piu' di cosi' (pannello chiuso nel frattempo) la linea si interrompe

// ---------------------------------------------------------------- grafico
// Linee su un solo asse: % del server (CPU totale e RAM totale). Le tre linee si distinguono anche per il tratto, non solo per il colore.
// La larghezza segue quella del riquadro (1 unita' = 1 pixel): cosi' le etichette restano leggibili anche sul telefono.
const H = 200, PAD = { l: 42, r: 10, t: 10, b: 26 };
const PH = H - PAD.t - PAD.b;
const niceMax = (v) => [5, 10, 20, 25, 50, 100].find((c) => c >= v * 1.1) || 100;

function makeChart() {
  const plot = svg("svg", { class: "chart", role: "img" });
  const msg = h("p", { class: "empty chartmsg" }, "Raccolgo i dati: il grafico si riempie mentre tieni aperta questa pagina.");
  const legend = h("ul", { class: "legend" });
  const toggles = new Map();
  let windowS = WINDOWS[0].s;
  let onWindow = () => {};

  const group = h("div", { class: "seg", role: "group", "aria-label": "Periodo del grafico" },
    WINDOWS.map((w) => {
      const b = h("button", { class: "btn quiet", type: "button", "aria-pressed": String(w.s === windowS), onclick: () => {
        windowS = w.s;
        toggles.forEach((btn, s) => btn.setAttribute("aria-pressed", String(s === windowS)));
        onWindow(windowS);
      } }, w.label);
      toggles.set(w.s, b);
      return b;
    }));

  const wrap = h("div", { class: "chartwrap" }, plot, msg);
  const el = h("figure", { class: "chartbox" },
    h("div", { class: "charthead" }, h("figcaption", {}, "Uso delle risorse (% del server)"), group),
    wrap, legend);
  if (typeof ResizeObserver === "function") {
    let lastW = 0;
    new ResizeObserver(() => { if (wrap.clientWidth !== lastW) { lastW = wrap.clientWidth; if (lastHist) draw(lastHist); } }).observe(wrap);
  }

  let lastHist = null;
  function draw(hist) {
    lastHist = hist;
    const W = Math.max(280, Math.round(wrap.clientWidth - 18)) || 600;   // 18 = spazio interno del riquadro
    const PW = W - PAD.l - PAD.r;
    plot.setAttribute("viewBox", `0 0 ${W} ${H}`);
    plot.setAttribute("height", String(H));
    const pts = (hist && hist.points) || [];
    const lastOf = (get) => { for (let i = pts.length - 1; i >= 0; i--) { const v = get(pts[i]); if (v != null) return v; } return null; };
    legend.replaceChildren(...SERIES.map((s) => {
      const v = lastOf(s.get);
      return h("li", {}, svg("svg", { viewBox: "0 0 28 8", width: 28, height: 8, "aria-hidden": "true", class: "lsample" }, svg("line", { x1: 0, y1: 4, x2: 28, y2: 4, class: "ln " + s.cls })),
        h("span", {}, s.label), h("strong", {}, v == null ? "—" : pct(v)));
    }));
    const enough = pts.filter((p) => SERIES.some((s) => s.get(p) != null)).length >= 2;
    msg.hidden = enough;
    plot.hidden = !enough;
    if (!enough) { plot.replaceChildren(); plot.setAttribute("aria-label", "Grafico delle risorse: dati non ancora sufficienti"); return; }

    const maxV = Math.max(1, ...pts.flatMap((p) => SERIES.map((s) => s.get(p)).filter((v) => v != null)));
    const top = niceMax(maxV);
    const t1 = hist.now, t0 = t1 - hist.window_s;
    const x = (t) => PAD.l + Math.max(0, Math.min(1, (t - t0) / (t1 - t0))) * PW;
    const y = (v) => PAD.t + PH - Math.min(1, v / top) * PH;

    const kids = [];
    [0, 0.5, 1].forEach((f) => {
      const yy = PAD.t + PH - f * PH;
      kids.push(svg("line", { x1: PAD.l, x2: W - PAD.r, y1: yy, y2: yy, class: "grid" }));
      const label = svg("text", { x: PAD.l - 6, y: yy + 4, class: "ctext", "text-anchor": "end" });
      label.textContent = dec(+(top * f).toFixed(1)) + "%";
      kids.push(label);
    });
    const xl = (anchor, xx, txt) => { const t = svg("text", { x: xx, y: H - 6, class: "ctext", "text-anchor": anchor }); t.textContent = txt; return t; };
    const span = hist.window_s >= 3600 ? "1 ora fa" : `${Math.round(hist.window_s / 60)} min fa`;
    kids.push(xl("start", PAD.l, span), xl("end", W - PAD.r, "ora"));

    SERIES.forEach((s) => {
      let d = "", prev = null, n = 0;
      const flush = () => { if (n === 1 && prev) kids.push(svg("circle", { cx: x(prev.t), cy: y(s.get(prev)), r: 2.5, class: "dot " + s.cls })); n = 0; };
      pts.forEach((p) => {
        const v = s.get(p);
        if (v == null) { flush(); prev = null; return; }
        if (prev && p.t - prev.t > GAP_S) { flush(); prev = null; }
        d += `${prev ? "L" : "M"}${x(p.t).toFixed(1)} ${y(v).toFixed(1)} `;
        n++;
        prev = p;
      });
      flush();
      if (d) kids.push(svg("path", { d: d.trim(), class: "ln " + s.cls, fill: "none", "vector-effect": "non-scaling-stroke" }));
    });
    plot.replaceChildren(...kids);
    plot.setAttribute("aria-label", `Grafico delle risorse, ultimi ${span.replace(" fa", "")}. ` +
      SERIES.map((s) => `${s.label}: ${lastOf(s.get) == null ? "nessun dato" : pct(lastOf(s.get))}`).join(". "));
  }

  return { el, draw, set onWindow(fn) { onWindow = fn; }, get windowS() { return windowS; } };
}

// ---------------------------------------------------------------- contenitori
const listFact = (label, items, none) => h("div", {}, h("dt", {}, label),
  h("dd", {}, items.length ? h("ul", { class: "plainlist" }, items.map((i) => h("li", {}, i))) : none));

function makeContainer(sid, name) {
  const ledSlot = h("span", { class: "ledslot" });
  const info = h("small");
  const dl = h("dl", { class: "facts compact" });
  const pre = h("pre", { class: "log", hidden: true, tabindex: "0", "aria-label": `Log di ${name}` });
  const refresh = h("button", { class: "btn quiet", type: "button", hidden: true, onclick: (e) => run(e.currentTarget, loadLog) }, "Aggiorna");
  const logBtn = h("button", { class: "btn quiet", type: "button", "aria-expanded": "false", onclick: async (e) => {
    const open = pre.hidden;
    pre.hidden = !open;
    refresh.hidden = !open;
    logBtn.setAttribute("aria-expanded", String(open));
    logBtn.textContent = open ? "Nascondi log" : "Log";
    if (open) await run(e.currentTarget, loadLog);
  } }, "Log");
  const el = h("li", { class: "cont" },
    h("div", { class: "line" }, h("div", { class: "rowmain static" }, ledSlot, h("span", { class: "text" }, h("strong", {}, name), info)), logBtn, refresh),
    pre, dl);

  async function loadLog() {
    const r = await api(`/services/${sid}/logs?container=${encodeURIComponent(name)}&tail=150`);
    pre.textContent = (r.logs.trim() || "Nessun messaggio") + (r.truncated ? "\n[… tagliato: mostro solo la parte finale]" : "");
    pre.scrollTop = pre.scrollHeight;
  }

  function patch(c, status, x, host) {
    ledSlot.replaceChildren(led(status));
    const usage = status === "running" && x
      ? `${pct(x.cpu_percent != null && host ? x.cpu_percent / host.cores : null)} CPU · ${fmtBytes(x.mem_bytes)}`
      : STATUS_LABEL[status] || status;
    info.textContent = usage;
    if (!c || !c.exists) { dl.replaceChildren(fact("Stato", "Non ancora creato")); return; }
    const limits = [c.limit_mem ? `memoria max ${fmtBytes(c.limit_mem)}` : null, c.limit_cpus ? `CPU max ${dec(c.limit_cpus)} core` : null].filter(Boolean);
    dl.replaceChildren(
      fact("Immagine", c.image || "?", c.image_id ? `id ${c.image_id}` : null),
      c.started_at ? fact("Avviato", fmtDate(c.started_at), ago(c.started_at))
        : fact("Fermato", c.finished_at && !c.finished_at.startsWith("0001") ? fmtDate(c.finished_at) : "mai avviato",
            c.exit_code != null && c.finished_at && !c.finished_at.startsWith("0001") ? `codice di uscita ${c.exit_code}${c.oom_killed ? ", memoria finita" : ""}` : null),
      c.health ? fact("Controllo di salute", HEALTH[c.health] || c.health, c.health_failing ? `${c.health_failing} controlli falliti di fila` : null, led(HEALTH_LED[c.health] || "partial")) : null,
      fact("Riavvii", String(c.restarts), c.restart_policy ? `politica: ${c.restart_policy}` : null),
      fact("Rete", c.network_mode || "—"),
      fact("Limiti", limits.length ? limits.join(" · ") : "Nessun limite"),
      listFact("Porte pubblicate", c.ports.map((p) => `${p.container} → ${p.host.join(", ")}`), "Nessuna (si raggiunge dalla rete interna o da Tailscale)"),
      listFact("Cartelle", c.mounts.map((m) => `${m.source || "(anonimo)"} → ${m.destination} (${m.rw ? "scrittura" : "sola lettura"})`), "Nessuna"));
  }
  return { el, patch };
}

// ---------------------------------------------------------------- pagina
export function servizio(root, ctx, sid) {
  const st = { services: null, stats: null, detail: null, hist: null, modes: null };
  const at = { stats: 0, hist: 0, detail: 0 };
  let statesKey = "";
  let busy = false;
  let confirming = false;
  let focused = false;

  const page = h("div", { class: "dpage" });
  const errBox = h("div", { class: "alerts", hidden: true });
  root.append(page);

  // --- cornice principale (come nella bozza: nome, anello, grafico, pulsanti, freccia indietro)
  const title = h("h2", { tabindex: "-1", class: "dtitle" });
  const statusLine = h("p", { class: "dstatus" });
  const desc = h("p", { class: "hint" });
  const gauge = makeGauge();
  gauge.el.classList.add("big");
  const chart = makeChart();
  chart.onWindow = () => { at.hist = 0; refreshHist(); };

  const powerBtn = h("button", { class: "btn", type: "button", onclick: () => act(isOn() ? "stop" : "start") });
  const saverBtn = h("button", { class: "btn", type: "button", onclick: () => onSaver() }, "Risparmio energetico");
  const note = h("p", { class: "hint dnote", "aria-live": "polite" });
  const confirmRow = h("div", { class: "confirm", hidden: true, role: "group", "aria-label": "Conferma" });
  const back = h("a", { class: "btn back", href: "#servizi" },
    svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", class: "ico" }, svg("path", { d: "M19 12H5M11 6l-6 6 6 6" })), "Torna ai servizi");

  const frame = h("div", { class: "dframe panel" },
    h("div", { class: "dleft" }, title, statusLine, gauge.el, desc),
    h("div", { class: "dright" }, chart.el,
      h("div", { class: "dbtns" }, h("div", { class: "actions wrap" }, powerBtn, saverBtn), confirmRow, note)),
    h("div", { class: "dback" }, back));

  // --- sezioni sotto la cornice
  const factsBox = h("dl", { class: "facts grid" });
  const contList = h("ul", { class: "rows plain conts" });
  const maint = h("div", { class: "panel" });
  const restartBtn = h("button", { class: "btn", type: "button", onclick: () => act("restart") }, "Riavvia");
  const openLink = h("a", { class: "btn", target: "_blank", rel: "noopener" }, "Apri il servizio");
  const maintHint = h("p", { class: "hint" });
  maint.append(h("div", { class: "actions wrap" }, restartBtn, openLink), maintHint);
  page.append(errBox, frame, section("Stato", h("div", { class: "panel" }, factsBox)), section("Contenitori", contList), section("Manutenzione", maint));

  const conts = new Map();
  const svc = () => (st.services || []).find((s) => s.id === sid);
  const isOn = () => { const s = svc(); return !!s && (s.status === "running" || s.status === "partial"); };

  // ---- modalità di risparmio che comprendono questo servizio (definite in services.py; qui non si inventa nulla)
  const modeOf = (action) => (st.modes || []).find((m) => m.action === action && m.services.includes(sid));
  function modeActive(m) {
    const want = m.action === "stop" ? "stopped" : "running";
    const sts = m.services.map((id) => (st.services || []).find((s) => s.id === id)).filter((s) => s && s.status !== "not_created");
    return sts.length > 0 && sts.every((s) => s.status === want);
  }
  const namesOf = (m) => m.services.map((id) => ((st.services || []).find((s) => s.id === id) || { name: id }).name).join(", ");

  function onSaver() {
    const s = svc();
    const stopM = modeOf("stop"), startM = modeOf("start");
    const m = isOn() ? stopM : (stopM && modeActive(stopM) ? startM : null);
    if (!s || !m) return;
    confirming = m;
    renderConfirm();
  }

  function renderConfirm() {
    const m = confirming;
    confirmRow.hidden = !m;
    if (!m) { confirmRow.replaceChildren(); return; }
    const verb = m.action === "stop" ? "spegne" : "riaccende";
    confirmRow.replaceChildren(
      h("span", {}, `La modalità «${m.name}» ${verb}: ${namesOf(m)}. Confermi?`),
      h("button", { class: "btn primary", type: "button", onclick: async (e) => {
        const mode = confirming; confirming = false; renderConfirm();
        await run(e.currentTarget, async () => {
          busy = true; render();
          try {
            const r = await api(`/modes/${mode.id}/apply`, { method: "POST" });
            toast(`Modalità ${mode.name} applicata` + (r.skipped && r.skipped.length ? ` (${r.skipped.length} container non creati, saltati)` : ""));
          } finally { busy = false; }
          await refresh(true);
        });
      } }, "Sì, applica"),
      h("button", { class: "btn quiet", type: "button", onclick: () => { confirming = false; renderConfirm(); powerBtn.focus(); } }, "Annulla"));
  }

  async function act(action) {
    const s = svc();
    if (!s) return;
    busy = true; confirming = false; render();
    try { await api(`/services/${sid}/${action}`, { method: "POST" }); }
    catch (e) { toast(e.message, "error"); }
    busy = false;
    await refresh(true);
  }

  // ---- disegno
  function render() {
    const s = svc();
    if (!s) return;
    const on = isOn();
    const x = st.stats && st.stats.services && st.stats.services[sid];
    const host = st.stats && st.stats.host;
    document.title = `${s.name} - Dettagli - Homeserver`;

    title.textContent = s.name;
    statusLine.replaceChildren(led(busy ? "partial" : s.status), busy ? "Un attimo…" : STATUS_LABEL[s.status] || s.status);
    desc.textContent = s.description;
    gauge.set(gaugeValues(s, x, busy), s.name);

    // spegnimento
    powerBtn.textContent = on ? "Spegni" : "Accendi";
    powerBtn.className = "btn " + (on ? "danger" : "primary");
    powerBtn.disabled = busy || (on && !s.can_stop) || s.status === "not_created";

    // risparmio energetico: la modalita' che comprende questo servizio, oppure nulla
    const stopM = modeOf("stop"), startM = modeOf("start");
    let saverText = "Risparmio energetico", reason = "";
    if (on) { if (!stopM) reason = "Nessuna modalità di risparmio prevede questo servizio (si definiscono in src/backend/app/services.py)."; }
    else if (stopM && modeActive(stopM) && startM) saverText = "Esci dal risparmio";
    else reason = "Il servizio è spento: per riaccenderlo usa «Accendi».";
    saverBtn.textContent = saverText;
    saverBtn.disabled = busy || !!reason;
    const notes = [];
    if (!s.can_stop && on) notes.push("Questo servizio non si ferma dal pannello.");
    if (s.status === "not_created") notes.push(`Non è ancora stato creato: dal terminale del server, nella cartella del progetto, lancia ${createCmd()}.`);
    else if (reason) notes.push(reason);
    note.textContent = notes.join(" ");

    // stato
    const url = serviceUrl(s);
    factsBox.replaceChildren(
      fact("CPU", x && on && x.cpu_host_percent != null ? pct(x.cpu_host_percent) : "—", "del server"),
      fact("Memoria", x && on && x.mem_bytes != null ? fmtBytes(x.mem_bytes) : "—",
        x && on && host && host.mem_total && x.mem_bytes != null ? `${pct((x.mem_bytes / host.mem_total) * 100)} del server` : null),
      fact("Attivo da", x && on ? fmtDuration(x.uptime_s) : "—"),
      fact("Salute", on && x && x.health ? HEALTH[x.health] || x.health : "Nessun controllo", null, on && x && x.health ? led(HEALTH_LED[x.health] || "partial") : null),
      fact("Riavvii automatici", x ? String(x.restarts) : "—", x && x.restarts > 0 ? "è andato in errore" : null),
      fact("Indirizzo", url ? h("a", { href: url, target: "_blank", rel: "noopener" }, url.replace(/^https?:\/\//, "")) : "Solo da Tailscale o non web"));

    // contenitori
    const dmap = new Map(((st.detail && st.detail.containers) || []).map((c) => [c.name, c]));
    const els = s.containers.map((c) => {
      let it = conts.get(c.name);
      if (!it) { it = makeContainer(sid, c.name); conts.set(c.name, it); }
      it.patch(dmap.get(c.name), c.status, x && x.containers && x.containers[c.name], host);
      return it.el;
    });
    const cur = Array.from(contList.children);
    if (cur.length !== els.length || els.some((e, i) => e !== cur[i])) contList.replaceChildren(...els);

    // manutenzione
    restartBtn.disabled = busy || !s.can_stop || s.status === "not_created";
    restartBtn.title = s.can_stop ? "" : "Questo servizio non si riavvia dal pannello";
    openLink.hidden = !url || !on;
    if (url) openLink.href = url;
    maintHint.textContent = "Aggiornare le immagini o cambiare la configurazione si fa dal terminale del server (docker compose pull e up -d): il pannello non tocca i file del progetto.";

    chart.draw(st.hist);
    renderConfirm();
  }

  function createCmd() {
    const prof = st.detail && st.detail.compose_profile;
    const s = svc();
    return `docker compose ${prof ? `--profile ${prof} ` : ""}up -d ${s ? s.containers[0].name : sid}`;
  }

  // ---- dati
  async function refreshHist() {
    try { st.hist = await api(`/services/${sid}/history?window=${chart.windowS}`); at.hist = Date.now(); chart.draw(st.hist); } catch { /* il grafico resta com'era */ }
  }

  async function refresh(force = false) {
    try {
      const services = await api("/services");
      errBox.hidden = true;
      st.services = services;
      const s = svc();
      if (!s) { page.replaceChildren(section("Servizio non trovato", h("p", { class: "notice", "data-kind": "error", role: "alert" }, `Non conosco nessun servizio «${sid}».`), h("div", { class: "actions" }, back))); document.title = "Servizio non trovato - Homeserver"; return; }
      if (!st.modes) st.modes = await api("/modes").catch(() => null);
      const key = services.map((x) => x.id + x.status).join();
      const now = Date.now();
      const changed = key !== statesKey;
      statesKey = key;
      const jobs = [];
      if (force || changed || now - at.stats >= 10000) {
        jobs.push(api("/stats").then((r) => { st.stats = r; at.stats = Date.now(); }).catch(() => {}));
      }
      if (force || changed || now - at.detail >= 30000) {
        jobs.push(api(`/services/${sid}/detail`).then((r) => { st.detail = r; at.detail = Date.now(); }).catch(() => {}));
      }
      await Promise.all(jobs);
      // lo storico si legge dopo le statistiche: e' la lettura delle statistiche che lo allunga
      if (force || changed || Date.now() - at.hist >= 10000) {
        try { st.hist = await api(`/services/${sid}/history?window=${chart.windowS}`); at.hist = Date.now(); } catch { /* resta il grafico di prima */ }
      }
      render();
      ctx.setServices(services);
      if (!focused) { focused = true; title.focus({ preventScroll: true }); ctx.focusSid = sid; }
    } catch (e) {
      errBox.replaceChildren(errorBox(e));
      errBox.hidden = false;
    }
  }

  return { update: () => refresh(false) };
}
