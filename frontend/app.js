// ---- util ----
const $ = (id) => document.getElementById(id);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el[k] = v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c != null) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

function fmtBytes(n) {
  if (n == null) return "?";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + " " + u[i];
}

function ago(epoch) {
  if (!epoch) return "mai";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (s < 90) return s + " s fa";
  if (s < 5400) return Math.round(s / 60) + " min fa";
  if (s < 129600) return Math.round(s / 3600) + " h fa";
  return Math.round(s / 86400) + " g fa";
}

// ---- API (con token opzionale) ----
function getToken() { try { return sessionStorage.getItem("hs_token") || ""; } catch { return ""; } }
function setToken(t) { try { sessionStorage.setItem("hs_token", t); } catch {} }

async function raw(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (getToken()) headers["X-API-Token"] = getToken();
  if (opts.json) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch("/api" + path, { method: opts.method || "GET", headers, body: opts.body });
  if (res.status === 401) {
    const t = prompt("Token del pannello (API_TOKEN):");
    if (t) { setToken(t); return raw(path, opts); }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : res.statusText);
  }
  return res;
}
const api = async (path, opts) => (await raw(path, opts)).json();

// ---- servizi ----
async function loadServices() {
  const box = $("list");
  try {
    const services = await api("/services");
    box.replaceChildren(...services.map((s) => {
      const link = s.url_port
        ? h("a", { href: `${s.scheme}://${location.hostname}:${s.url_port}`, target: "_blank" }, "apri")
        : null;
      const btn = (a, label) => h("button", {
        onclick: async (e) => {
          e.target.disabled = true;
          try { await api(`/services/${s.id}/${a}`, { method: "POST" }); } catch (err) { alert(err.message); }
          loadServices();
        },
      }, label);
      return h("div", { class: "card" }, h("div", { class: "row" },
        h("div", {}, h("strong", {}, s.name), " ", h("span", { class: "badge " + s.status }, s.status),
          h("br"), h("small", {}, s.description)),
        h("div", {}, link, " ", btn("start", "Start"), " ", btn("stop", "Stop"), " ", btn("restart", "Restart"))));
    }));
  } catch (e) { box.textContent = "Errore: " + e.message; }
}

// ---- steam ----
const openLogs = new Set();

async function loadDownloads() {
  const box = $("downloads");
  try {
    const items = await api("/steam/downloads");
    const cards = [];
    for (const d of items) {
      const state = d.status === "exited" ? (d.exit_code === 0 ? "exited0" : "failed") : d.status;
      const label = d.status === "exited" ? (d.exit_code === 0 ? "completato" : `errore (${d.exit_code})`) : d.status;
      const pre = h("pre", { style: openLogs.has(d.appid) ? "" : "display:none" }, "…");
      if (openLogs.has(d.appid)) {
        api(`/steam/downloads/${d.appid}/logs?tail=30`).then((r) => { pre.textContent = r.logs; pre.scrollTop = pre.scrollHeight; });
      }
      cards.push(h("div", { class: "card" },
        h("div", { class: "row" },
          h("div", {}, h("strong", {}, "App " + d.appid), " ", h("span", { class: "badge " + state }, label),
            " ", h("small", {}, d.platform)),
          h("div", {},
            h("button", { onclick: () => { openLogs.has(d.appid) ? openLogs.delete(d.appid) : openLogs.add(d.appid); loadDownloads(); } }, "Log"), " ",
            h("button", { onclick: async () => { await api(`/steam/downloads/${d.appid}`, { method: "DELETE" }).catch((e) => alert(e.message)); loadDownloads(); } },
              d.status === "running" ? "Annulla" : "Rimuovi"))),
        pre));
    }
    box.replaceChildren(...cards);
  } catch (e) { box.textContent = "Errore: " + e.message; }
}

async function loadLibrary() {
  const box = $("library");
  try {
    const games = await api("/steam/library");
    if (!games.length) { box.textContent = "Nessun gioco scaricato."; return; }
    box.replaceChildren(h("table", {},
      h("tr", {}, h("th", {}, "Gioco"), h("th", {}, "AppID"), h("th", {}, "Dimensione"), h("th", {}, "Stato")),
      games.map((g) => h("tr", {}, h("td", {}, g.name || "(sconosciuto)"), h("td", {}, g.appid),
        h("td", {}, fmtBytes(g.size_bytes)), h("td", {}, g.installed ? "installato" : "incompleto")))));
  } catch (e) { box.textContent = "Errore: " + e.message; }
}

$("steam-form").onsubmit = async (ev) => {
  ev.preventDefault();
  try {
    await api("/steam/downloads", { method: "POST", json: {
      appid: Number($("appid").value), platform: $("platform").value, login: $("login").value.trim() || "anonymous",
    } });
    openLogs.add(Number($("appid").value));
  } catch (e) { alert(e.message); }
  loadDownloads();
};

// ---- wireguard ----
let qrOpen = false; // finché un QR è visibile non ricarico la sezione (lo cancellerebbe)

async function qrImage(name) {
  const res = await raw(`/wireguard/peers/${encodeURIComponent(name)}/qr`);
  qrOpen = true;
  return h("img", {
    src: URL.createObjectURL(await res.blob()), alt: "QR " + name, title: "Clic per chiudere",
    style: "width:14rem;background:#fff;padding:.4rem;border-radius:6px;cursor:pointer",
    onclick: () => { qrOpen = false; loadWg(); },
  });
}

async function loadWg() {
  if (qrOpen) return;
  const box = $("wg");
  try {
    const [st, pr] = await Promise.all([api("/wireguard/status"), api("/wireguard/peers")]);
    const rows = st.peers.map((p) => {
      const online = p.last_handshake && Date.now() / 1000 - p.last_handshake < 180;
      const cell = h("td", {});
      if (pr.exposed) {
        cell.append(h("button", { onclick: async (e) => { e.target.replaceWith(await qrImage(p.name)); } }, "QR"), " ",
          h("button", { onclick: async () => {
            const blob = await (await raw(`/wireguard/peers/${encodeURIComponent(p.name)}/conf`)).blob();
            const a = h("a", { href: URL.createObjectURL(blob), download: p.name + ".conf" }); a.click();
          } }, ".conf"));
      }
      return h("tr", {}, h("td", {}, p.name), h("td", {}, h("span", { class: "badge " + (online ? "running" : "stopped") }, online ? "online" : "offline")),
        h("td", {}, ago(p.last_handshake)), h("td", {}, p.endpoint || "—"), h("td", {}, `↓${fmtBytes(p.rx_bytes)} ↑${fmtBytes(p.tx_bytes)}`), cell);
    });
    box.replaceChildren(
      h("small", {}, `wg0 · porta ${st.listen_port} · chiave pubblica ${st.public_key.slice(0, 12)}…`),
      h("table", {}, h("tr", {}, ["Peer", "Stato", "Ultimo handshake", "Endpoint", "Traffico", ""].map((t) => h("th", {}, t))), rows),
      pr.exposed ? null : h("p", { class: "muted" }, h("small", {}, "QR/.conf nascosti (WG_EXPOSE_PEERS=false). Per un nuovo dispositivo: docker compose exec wireguard /app/show-peer NOME")));
  } catch (e) { box.textContent = e.message; }
}

// ---- avvio ----
function refresh() { loadServices(); loadDownloads(); loadLibrary(); loadWg(); }
refresh();
setInterval(refresh, 10000);
