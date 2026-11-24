import React, { useCallback, useEffect, useState } from "react";
import { HashRouter, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, clearToken, formatBytes, formatDate, formatDuration, getToken, probe, setToken } from "./api.js";

const NAV = [
  { id: "overview", label: "Panoramica", icon: "◫" },
  { id: "services", label: "Servizi", icon: "▦" },
  { id: "backup", label: "Backup", icon: "◈" },
  { id: "network", label: "Rete", icon: "⌁" },
  { id: "access", label: "Accessi", icon: "⌑" },
];
const STATUS = { running: "Attivo", partial: "Parziale", stopped: "Fermo", not_created: "Non creato", failed: "Errore", exited: "Terminato", created: "In avvio", restarting: "Riavvio" };
const STATUS_CLASS = { running: "good", partial: "warn", stopped: "muted", not_created: "muted", failed: "bad", exited: "good", created: "warn", restarting: "warn" };

function Icon({ children }) { return <span className="nav-icon" aria-hidden="true">{children}</span>; }
function Card({ title, subtitle, action, children, className = "" }) {
  return <section className={"panel " + className}>
    <div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
    {children}
  </section>;
}
function Progress({ value }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  return <div className="progress"><span className={(pct >= 85 ? "danger " : pct >= 60 ? "warning " : "") + "fill-pct-" + pct} /></div>;
}
function StateDot({ status }) { return <span className={"state-dot " + (STATUS_CLASS[status] || "muted")} aria-label={STATUS[status] || status} />; }
function Empty({ children }) { return <div className="empty-state">{children}</div>; }
function ErrorMessage({ children }) { return <div className="inline-error" role="alert">{children}</div>; }

function Login({ onLogin }) {
  const [token, setValue] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    if (!token.trim() || busy) return;
    setBusy(true); setError("");
    setToken(token.trim(), remember);
    const result = await probe();
    setBusy(false);
    if (result === "ok") { setValue(""); onLogin(); }
    else {
      clearToken();
      setError(result === "locked" ? "Troppi tentativi. Attendi un minuto." :
        result === "offline" ? "Il server non risponde." : "Token non valido.");
    }
  }
  return <main className="login-shell"><form className="login-card" onSubmit={submit}>
    <div className="brand-mark">H</div><p className="eyebrow">HOME SERVER CONTROL</p>
    <h1>Accesso amministratore</h1><p className="muted-copy">Inserisci il token del pannello per continuare.</p>
    <label htmlFor="api-token">Token API</label>
    <input id="api-token" type="password" autoComplete="off" value={token} onChange={e => setValue(e.target.value)} required />
    <label className="remember"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> Ricorda su questo dispositivo</label>
    {error && <ErrorMessage>{error}</ErrorMessage>}
    <button className="button primary full" disabled={busy}>{busy ? "Verifica…" : "Accedi"}</button>
    <p className="login-foot">Il token si genera sul server con <code>./src/scripts/gen-api-token.sh</code>.</p>
  </form></main>;
}

function HostPanel({ host }) {
  if (!host) return <Card title="Risorse server"><Empty>Dati del server non disponibili.</Empty></Card>;
  const mem = host.mem_total ? host.mem_used / host.mem_total * 100 : null;
  const disks = host.disks || [];
  const values = [
    { label: "CPU", value: host.cpu_percent, detail: host.cores + " core" },
    { label: "Memoria", value: mem, detail: formatBytes(host.mem_used) + " / " + formatBytes(host.mem_total) },
    ...disks.map(d => ({ label: "Disco · " + d.label, value: d.total ? d.used / d.total * 100 : null, detail: formatBytes(d.used) + " / " + formatBytes(d.total) })),
  ];
  return <Card title="Risorse del server" subtitle={"Attivo da " + formatDuration(host.uptime_s)} className="host-panel">
    <div className="resource-grid">{values.map(item => <div className="resource" key={item.label}>
      <div className="resource-heading"><span>{item.label}</span><strong>{item.value == null ? "—" : item.value.toFixed(1) + "%"}</strong></div>
      <Progress value={item.value} /><small>{item.detail}</small>
    </div>)}</div>
    <div className="host-meta"><span>{host.cores} core logici</span><span>Carico {host.load ? host.load.join(" · ") : "—"}</span><span>Temperatura {host.temp_c == null ? "n/d" : host.temp_c + " °C"}</span></div>
  </Card>;
}

function ServiceCard({ service, stats, onAction, busy }) {
  const active = service.status === "running" || service.status === "partial";
  const usage = stats?.cpu_host_percent;
  const url = service.url_port && (!service.ts_only || location.hostname.endsWith(".ts.net"))
    ? (location.hostname.endsWith(".ts.net") ? "https" : service.scheme) + "://" + location.hostname + ":" + service.url_port + (service.path || "")
    : null;
  return <article className="service-card">
    <div className="service-title"><StateDot status={busy ? "partial" : service.status} /><div className="service-name"><strong>{service.name}</strong><small>{service.description}</small></div>
      <span className={"status-pill " + (STATUS_CLASS[service.status] || "muted")}>{STATUS[service.status] || service.status}</span>
    </div>
    <div className="service-stat"><strong>{active && usage != null ? usage.toFixed(1) + "%" : active ? "—" : "OFF"}</strong><span>{active ? "CPU host" : "Servizio non attivo"}</span></div>
    {stats && active && <div className="service-meta"><span>RAM {formatBytes(stats.mem_bytes)}</span><span>Uptime {formatDuration(stats.uptime_s)}</span><span>Riavvii {stats.restarts ?? 0}</span></div>}
    <div className="service-actions">
      <button className="button subtle" disabled={busy || (!active && service.status === "not_created")} onClick={() => onAction(service, "restart")}>Riavvia</button>
      {url && active && <a className="button subtle" href={url} target="_blank" rel="noopener noreferrer">Apri servizio ↗</a>}
      <button className={"button " + (active ? "danger" : "primary")} disabled={busy || (active && !service.can_stop)} onClick={() => onAction(service, active ? "stop" : "start")}>{active ? "Arresta" : "Avvia"}</button>
    </div>
    {service.containers?.length > 0 && <details className="container-details"><summary>Container ({service.containers.length})</summary>
      {service.containers.map(c => <div className="container-row" key={c.name}><StateDot status={c.status} /><span>{c.name}</span><small>{STATUS[c.status] || c.status}</small></div>)}
    </details>}
  </article>;
}

function Overview({ services, stats, backup, network, onNavigate, onServiceAction, busyServices }) {
  const active = services.filter(s => s.status === "running").length;
  const partial = services.filter(s => s.status === "partial").length;
  const down = services.length - active - partial;
  return <div className="dashboard-grid">
    <Card title="Servizi" subtitle={services.length + " gruppi configurati"} action={<button className="text-button" onClick={() => onNavigate("services")}>Tutti i servizi ↗</button>}>
      <div className="overview-services">{services.slice(0, 8).map(s => <div className="overview-service" key={s.id}><StateDot status={s.status}/><span>{s.name}</span><small>{STATUS[s.status] || s.status}</small></div>)}</div>
      <div className="summary-strip"><span className="good-text">{active} attivi</span><span className="warn-text">{partial} parziali</span><span className="bad-text">{down} fermi</span></div>
    </Card>
    <HostPanel host={stats?.host} />
    <Card title="Backup" subtitle="Protezione dei dati" action={<button className="text-button" onClick={() => onNavigate("backup")}>Apri backup ↗</button>}>
      {backup ? <><div className="big-stat">{backup.last_backup_at ? formatDate(backup.last_backup_at) : "Nessuna copia"}</div>
        <p className="muted-copy">{backup.configured ? (backup.stale ? "Attenzione: backup da verificare." : "Configurazione presente") : "Configurazione incompleta"}</p>
        {backup.disk && <div className="status-line"><StateDot status={backup.disk.present ? "running" : "failed"}/>{backup.disk.present ? "Disco backup collegato" : "Disco backup scollegato"}</div>}</> : <Empty>Stato backup non disponibile.</Empty>}
    </Card>
    <Card title="Rete Tailscale" subtitle="Accesso remoto sicuro" action={<button className="text-button" onClick={() => onNavigate("network")}>Dettagli ↗</button>}>
      {network ? <><div className="status-line"><StateDot status={network.state === "Running" ? "running" : "partial"}/><strong>{network.state === "Running" ? "Connesso" : network.state}</strong></div>
        <p className="muted-copy">{network.tailnet || "Rete privata"}</p>{network.https_url && <a className="external-link" href={network.https_url} target="_blank" rel="noopener noreferrer">{network.https_url}</a>}</> : <Empty>Stato rete non disponibile.</Empty>}
    </Card>
    <Card title="Stato operativo" subtitle="Riepilogo del sistema">
      <div className="system-summary"><div><span>Servizi</span><strong>{services.length}</strong></div><div><span>CPU</span><strong>{stats?.host?.cpu_percent == null ? "—" : stats.host.cpu_percent + "%"}</strong></div><div><span>RAM</span><strong>{stats?.host?.mem_total ? Math.round(stats.host.mem_used / stats.host.mem_total * 100) + "%" : "—"}</strong></div></div>
      <p className="muted-copy">Ultimo aggiornamento {new Date().toLocaleTimeString("it-IT")}</p>
    </Card>
  </div>;
}

function ServicesPage({ services, stats, onAction, busyServices, modes, onMode }) {
  const regular = services.filter(s => s.group !== "utility");
  const utilities = services.filter(s => s.group === "utility");
  return <div className="page-stack">
    {modes.length > 0 && <Card title="Modalità operative" subtitle="Avvio e arresto coordinato dei gruppi">
      <div className="mode-list">{modes.map(m => <button className="button subtle" key={m.id} disabled={!!modes.busy} title={m.description} onClick={() => onMode(m)}>{m.name}</button>)}</div>
    </Card>}
    <Card title="Servizi" subtitle="Gestione dei container Docker">
      <div className="service-grid">{regular.map(s => <ServiceCard key={s.id} service={s} stats={stats?.services?.[s.id]} busy={busyServices.has(s.id)} onAction={onAction}/>)}</div>
    </Card>
    {utilities.length > 0 && <Card title="Utility" subtitle="Servizi di supporto">{<div className="service-grid">{utilities.map(s => <ServiceCard key={s.id} service={s} stats={stats?.services?.[s.id]} busy={busyServices.has(s.id)} onAction={onAction}/>)}</div>}</Card>}
  </div>;
}

function BackupPage({ data, snapshots, logs, onJob, loading }) {
  const [confirmForget, setConfirmForget] = useState(false);
  const running = data?.job?.result === "running";
  const actions = data?.initialized
    ? [{kind:"backup", label:"Esegui backup", primary:true},{kind:"check",label:"Controlla integrità"},{kind:"forget",label:"Pulisci vecchie copie",danger:true}]
    : [{kind:"init",label:"Prepara archivio",primary:true}];
  return <div className="page-stack">
    <Card title="Stato backup" subtitle="Archivio cifrato Restic">
      {!data ? <Empty>Caricamento stato backup…</Empty> : !data.configured ? <><div className="warning-box">Backup non configurato</div><ul className="problem-list">{data.problems.map(p => <li key={p}>{p}</li>)}</ul></> : <>
        <div className="backup-facts"><div><span>Ultima copia</span><strong>{data.last_backup_at ? formatDate(data.last_backup_at) : "Nessuna copia"}</strong></div><div><span>Modalità</span><strong>Manuale</strong></div><div><span>Archivio</span><strong>{data.initialized ? "Inizializzato" : data.initialized === false ? "Da inizializzare" : "Non verificabile"}</strong></div><div><span>Conservazione</span><strong>{data.keep.daily} giorni · {data.keep.weekly} settimane · {data.keep.monthly} mesi</strong></div></div>
        {data.disk && <div className="status-line"><StateDot status={data.disk.present ? "running" : "failed"}/>{data.disk.present ? "Disco esterno collegato" : "Disco esterno non collegato"}</div>}
        <div className="action-row">{actions.map(a => <button key={a.kind} className={"button " + (a.primary ? "primary" : a.danger ? "danger" : "subtle")} disabled={running || loading || (a.kind === "forget" && !data.initialized)} onClick={() => a.kind === "forget" ? setConfirmForget(true) : onJob(a.kind)}>{a.label}</button>)}</div>
        {confirmForget && <div className="confirm-box"><p>Confermi la pulizia? Verranno conservati {data.keep.daily} backup giornalieri, {data.keep.weekly} settimanali e {data.keep.monthly} mensili; gli altri verranno eliminati.</p><button className="button danger" onClick={() => {setConfirmForget(false); onJob("forget");}}>Conferma eliminazione</button><button className="button subtle" onClick={() => setConfirmForget(false)}>Annulla</button></div>}
        <p className="muted-copy">Percorso archivio: {data.repo || "non impostato"}. Il backup viene avviato manualmente.</p>
      </>}
    </Card>
    {data?.job && <Card title="Ultima operazione" subtitle={data.job.result}><div className="status-line"><StateDot status={running ? "partial" : data.job.result === "failed" ? "failed" : "running"}/><strong>{data.job.kind}</strong><span>{data.job.started_at ? formatDate(data.job.started_at) : ""}</span></div><pre className="log-output">{logs || "Log non disponibile"}</pre></Card>}
    <Card title="Copie disponibili" subtitle="Snapshot Restic recenti">
      {!snapshots ? <Empty>{data?.initialized ? "Caricamento snapshot…" : "Gli snapshot compariranno dopo l'inizializzazione."}</Empty> : snapshots.length === 0 ? <Empty>Nessuno snapshot disponibile.</Empty> : <div className="snapshot-list">{snapshots.map(s => <div className="snapshot-row" key={s.id}><div><strong>{formatDate(s.time)}</strong><small>ID {s.id}</small></div><div><strong>{formatBytes(s.added_bytes)}</strong><small>Nuovi dati</small></div><div><strong>{formatBytes(s.total_bytes)}</strong><small>Elaborati</small></div></div>)}</div>}
    </Card>
  </div>;
}

function NetworkPage({ data, onLogout, installPrompt }) {
  return <div className="page-stack">
    <Card title="Tailscale" subtitle="Connessione privata al server">
      {!data ? <Empty>Caricamento stato rete…</Empty> : <>
        <div className="status-line"><StateDot status={data.state === "Running" ? "running" : data.state === "NeedsLogin" ? "partial" : "stopped"}/><strong>{data.state === "Running" ? "Connesso" : data.state}</strong><span>{data.tailnet || ""}</span></div>
        {data.login_url && <a className="button primary" href={data.login_url} target="_blank" rel="noopener noreferrer">Completa accesso Tailscale ↗</a>}
        {data.https_url ? <div className="remote-address"><span>Indirizzo HTTPS del server</span><strong>{data.https_url}</strong><div className="action-row"><a className="button primary" href={data.https_url} target="_blank" rel="noopener noreferrer">Apri pannello</a><button className="button subtle" onClick={() => navigator.clipboard?.writeText(data.https_url)}>Copia indirizzo</button></div></div> : <p className="muted-copy">Per l'accesso HTTPS abilita MagicDNS e HTTPS Certificates nella console Tailscale.</p>}
        {(data.health || []).map((item,i) => <div className="warning-box" key={i}>{item}</div>)}
      </>}
    </Card>
    <Card title="Dispositivi nella rete" subtitle={(data?.peers?.length || 0) + " dispositivi conosciuti"}>
      {data?.peers?.length ? <div className="peer-list">{data.peers.map(p => <div className="peer-row" key={p.name}><StateDot status={p.online ? "running" : "stopped"}/><div><strong>{p.name}</strong><small>{p.os || "Sistema non identificato"} · {p.online ? "Online" : "Ultimo accesso " + formatDate(p.last_seen)}</small></div><span>{p.ips?.[0] || ""}</span></div>)}</div> : <Empty>Nessun dispositivo o dati non disponibili.</Empty>}
    </Card>
    <Card title="Applicazione" subtitle="Sessione e installazione">
      <p className="muted-copy">La sessione è conservata {getToken() ? "nel browser" : "per questa scheda"}.</p>
      {installPrompt && <button className="button primary" onClick={async () => { await installPrompt.prompt(); }}>Installa applicazione</button>}
      <button className="button danger" onClick={onLogout}>Esci da questo dispositivo</button>
    </Card>
  </div>;
}

function AccessPage({ data }) {
  const [copied, setCopied] = useState("");
  async function copy(command) {
    try { await navigator.clipboard.writeText(command); setCopied(command); setTimeout(() => setCopied(""), 1800); }
    catch { setCopied(""); }
  }
  const label = { mostra: "Si può rileggere", reimposta: "Si può reimpostare", impossibile: "Non recuperabile" };
  return <Card title="Accessi e recupero" subtitle="Le password non vengono mostrate dal pannello">
    <p className="muted-copy">Il recupero delle credenziali avviene dal terminale del server. Questa schermata non espone segreti.</p>
    {!data ? <Empty>Caricamento…</Empty> : <div className="access-list">{data.items.map(item => <div className="access-item" key={item.id}>
      <StateDot status={item.ok === false ? "failed" : item.recovery === "impossibile" ? "muted" : "running"}/>
      <div className="access-content"><div className="access-heading"><strong>{item.name}</strong><span className="status-pill muted">{label[item.recovery] || item.recovery}</span></div><p>{item.where}</p>{item.note && <small>{item.note}</small>}
        {item.ok === false && <div className="warning-box">Configurazione non rilevata.</div>}
        {item.command && <div className="command-line"><code>{item.command}</code><button className="text-button" onClick={() => copy(item.command)}>{copied === item.command ? "Copiato" : "Copia"}</button></div>}
      </div>
    </div>)}</div>}
  </Card>;
}

function DashboardApp() {
  const routerLocation = useLocation();
  const navigateTo = useNavigate();
  const page = routerLocation.pathname.slice(1) || "overview";
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [authMessage, setAuthMessage] = useState("");
  const [services, setServices] = useState([]);
  const [stats, setStats] = useState(null);
  const [modes, setModes] = useState([]);
  const [backup, setBackup] = useState(null);
  const [snapshots, setSnapshots] = useState(null);
  const [logs, setLogs] = useState("");
  const [network, setNetwork] = useState(null);
  const [access, setAccess] = useState(null);
  const [busyServices, setBusyServices] = useState(() => new Set());
  const [busyJob, setBusyJob] = useState(false);
  const [toast, setToast] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [refreshError, setRefreshError] = useState("");

  const notify = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3500);
  }, []);

  const loadServices = useCallback(async () => {
    const result = await api("/services");
    setServices(result);
    return result;
  }, []);
  const loadStats = useCallback(async () => {
    const result = await api("/stats");
    setStats(result);
  }, []);
  const loadBackup = useCallback(async () => {
    const result = await api("/backup/status");
    setBackup(result);
    if (result.initialized && result.job?.result !== "running") {
      const snaps = await api("/backup/snapshots").catch(() => null);
      setSnapshots(snaps);
    } else setSnapshots(null);
    if (result.job) {
      const jobLogs = await api("/backup/jobs/current/logs?tail=60").catch(() => null);
      setLogs(jobLogs?.logs || "");
    }
  }, []);
  const loadNetwork = useCallback(async () => {
    const result = await api("/tailscale/status");
    setNetwork(result);
  }, []);
  const loadAccess = useCallback(async () => {
    const result = await api("/access");
    setAccess(result);
  }, []);

  const refresh = useCallback(async (full = false) => {
    try {
      const jobs = [loadServices()];
      if (full) jobs.push(loadStats());
      if (page === "backup" || full) jobs.push(loadBackup());
      if (page === "network" || full) jobs.push(loadNetwork());
      if (page === "access" || full) jobs.push(loadAccess());
      const results = await Promise.allSettled(jobs);
      const failed = results.find(result => result.status === "rejected");
      setRefreshError(failed ? (failed.reason?.message || "Aggiornamento parziale") : "");
      setLastUpdated(new Date());
    } catch (error) {
      setRefreshError(error.message || "Aggiornamento non riuscito");
    }
  }, [page, loadServices, loadStats, loadBackup, loadNetwork, loadAccess]);

  useEffect(() => {
    let alive = true;
    probe().then(result => {
      if (!alive) return;
      if (result === "ok") { setAuthenticated(true); setAuthMessage(""); }
      else if (result === "token") setAuthMessage(getToken() ? "Il token salvato non è valido." : "");
      else if (result === "locked") setAuthMessage("Troppi tentativi. Attendi un minuto prima di riprovare.");
      else setAuthMessage("Server non raggiungibile: puoi comunque inserire il token.");
    }).finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const onLost = () => { clearToken(); setAuthenticated(false); setAuthMessage("Sessione scaduta. Inserisci nuovamente il token."); };
    window.addEventListener("hs:auth-lost", onLost);
    return () => window.removeEventListener("hs:auth-lost", onLost);
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    let alive = true;
    const run = async (full) => {
      if (document.hidden || !alive) return;
      try {
        await refresh(full);
      } catch (error) {
        if (alive) setRefreshError(error.message || "Errore di aggiornamento");
      }
    };
    run(true);
    const timer = window.setInterval(() => run(false), 5000);
    const statsTimer = window.setInterval(() => { if (!document.hidden) loadStats().catch(error => setRefreshError(error.message)); }, 15000);
    const onVisible = () => { if (!document.hidden) run(true); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { alive = false; window.clearInterval(timer); window.clearInterval(statsTimer); document.removeEventListener("visibilitychange", onVisible); };
  }, [authenticated, refresh]);

  useEffect(() => {
    if (!authenticated) return;
    if (page === "backup") loadBackup().catch(e => setRefreshError(e.message));
    if (page === "network") loadNetwork().catch(e => setRefreshError(e.message));
    if (page === "access") loadAccess().catch(e => setRefreshError(e.message));
  }, [page, authenticated, loadBackup, loadNetwork, loadAccess]);

  useEffect(() => {
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  useEffect(() => {
    const handler = e => { e.preventDefault(); setInstallPrompt(e); };
    const installed = () => setInstallPrompt(null);
    window.addEventListener("beforeinstallprompt", handler);
    window.addEventListener("appinstalled", installed);
    return () => { window.removeEventListener("beforeinstallprompt", handler); window.removeEventListener("appinstalled", installed); };
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    api("/modes").then(setModes).catch(() => setModes([]));
  }, [authenticated]);

  async function serviceAction(service, action) {
    if (busyServices.has(service.id)) return;
    if (action === "stop" && !window.confirm("Arrestare " + service.name + "?")) return;
    setBusyServices(prev => new Set(prev).add(service.id));
    try {
      await api("/services/" + service.id + "/" + action, { method: "POST" });
      notify(service.name + ": operazione completata");
      await Promise.all([loadServices(), loadStats()]);
    } catch (error) { notify(error.message); }
    finally { setBusyServices(prev => { const next = new Set(prev); next.delete(service.id); return next; }); }
  }

  async function applyMode(mode) {
    if (!window.confirm("Applicare la modalità «" + mode.name + "»?")) return;
    try {
      const result = await api("/modes/" + mode.id + "/apply", { method: "POST" });
      setServices(result.services || []);
      notify("Modalità " + mode.name + " applicata");
    } catch (error) { notify(error.message); }
  }

  async function startJob(kind) {
    if (busyJob) return;
    setBusyJob(true);
    try {
      const result = await api("/backup/jobs", { method: "POST", json: { kind } });
      notify("Operazione backup avviata");
      await loadBackup();
    } catch (error) { notify(error.message); }
    finally { setBusyJob(false); }
  }

  function navigate(id) {
    navigateTo("/" + id);
    setSidebarOpen(false);
  }
  function logout() { clearToken(); setAuthenticated(false); setAuthMessage(""); navigateTo("/overview"); }

  const active = services.filter(s => s.status === "running").length;
  const partial = services.filter(s => s.status === "partial").length;
  const pageTitle = NAV.find(n => n.id === page)?.label || "Panoramica";

  if (checking) return <main className="loading-screen"><div className="brand-mark">H</div><p>Connessione a HomeServer…</p></main>;
  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;

  return <div className="app-shell">
    <aside className={"sidebar " + (sidebarOpen ? "open" : "")}>
      <div className="sidebar-brand"><div className="brand-mark">H</div><div><strong>HomeServer</strong><small>CONTROL CENTER</small></div></div>
      <div className="nav-label">Workspace</div>
      <nav className="side-nav">{NAV.map(item => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => navigate(item.id)}><Icon>{item.icon}</Icon>{item.label}</button>)}</nav>
      <div className="sidebar-bottom"><div className="connection-indicator"><i/> Sistema connesso</div><button className="sidebar-logout" onClick={logout}>Esci dal pannello</button></div>
    </aside>
    {sidebarOpen && <button className="scrim" aria-label="Chiudi navigazione" onClick={() => setSidebarOpen(false)} />}
    <div className="main-shell">
      <header className="topbar">
        <button className="mobile-menu" aria-label="Apri navigazione" onClick={() => setSidebarOpen(true)}>☰</button>
        <div><p className="eyebrow">HOME SERVER / {pageTitle.toUpperCase()}</p><h1>{pageTitle}</h1></div>
        <div className="topbar-right"><div className="top-status"><span className="good-dot"/>{active} <span className="warn-dot"/>{partial} <span className="bad-dot"/>{services.length-active-partial}</div><span className="updated-label">{lastUpdated ? "Aggiornato " + lastUpdated.toLocaleTimeString("it-IT") : "Aggiornamento…"}</span><button className="icon-button" title="Aggiorna" onClick={() => refresh(true)}>↻</button></div>
      </header>
      <main className="content">
        {refreshError && <div className="inline-error" role="alert">{refreshError}</div>}
        {page === "overview" && <Overview services={services} stats={stats} backup={backup} network={network} onNavigate={navigate} onServiceAction={serviceAction} busyServices={busyServices}/>}
        {page === "services" && <ServicesPage services={services} stats={stats} onAction={serviceAction} busyServices={busyServices} modes={modes} onMode={applyMode}/>}
        {page === "backup" && <BackupPage data={backup} snapshots={snapshots} logs={logs} onJob={startJob} loading={busyJob}/>}
        {page === "network" && <NetworkPage data={network} onLogout={logout} installPrompt={installPrompt}/>}
        {page === "access" && <AccessPage data={access}/>}
      </main>
    </div>
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>;
}

export default function App() { return <HashRouter><DashboardApp /></HashRouter>; }
