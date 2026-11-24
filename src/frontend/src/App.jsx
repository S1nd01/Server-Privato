import React, { useCallback, useEffect, useRef, useState } from "react";
import { HashRouter, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, probe } from "./api.js";
import BackupPage from "./Backup.jsx";
import Login from "./Login.jsx";
import { AccessPage, NetworkPage } from "./Network.jsx";
import { Overview, ServicesPage } from "./Services.jsx";
import Welcome from "./Welcome.jsx";

const NAV = [
  { id: "overview", label: "Panoramica", icon: "◫" },
  { id: "services", label: "Servizi", icon: "▦" },
  { id: "backup", label: "Backup", icon: "◈" },
  { id: "network", label: "Rete", icon: "⌁" },
  { id: "access", label: "Accessi", icon: "⌑" },
];
function Icon({ children }) {
  return (
    <span className="nav-icon" aria-hidden="true">
      {children}
    </span>
  );
}
function DashboardApp() {
  const routerLocation = useLocation();
  const navigateTo = useNavigate();
  const route = routerLocation.pathname.replace(/^\//, "");
  const legacy = { servizi: "services", rete: "network", accessi: "access" };
  const page = NAV.some((item) => item.id === route)
    ? route
    : legacy[route] || "overview";
  const [welcome, setWelcome] = useState(false);
  const [help, setHelp] = useState(false);
  const enter = useCallback(
    ({ go, help } = {}) => {
      if (go) navigateTo("/" + go);
      setHelp(Boolean(help));
      setWelcome(false);
    },
    [navigateTo],
  );
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
  const [busyMode, setBusyMode] = useState(false);
  const refreshPending = useRef(false);
  const snapshotKey = useRef(null);
  const [busyJob, setBusyJob] = useState(false);
  const [toast, setToast] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [refreshError, setRefreshError] = useState("");

  useEffect(() => {
    if (!sidebarOpen) return;
    const onEscape = (event) => {
      if (event.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, [sidebarOpen]);

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
    if (
      page === "backup" &&
      result.initialized &&
      result.job?.result !== "running"
    ) {
      const key = JSON.stringify([
        result.repo,
        result.last_backup_at,
        result.job?.finished_at,
      ]);
      if (snapshotKey.current !== key) {
        const snaps = await api("/backup/snapshots").catch(() => null);
        setSnapshots(snaps);
        if (snaps) snapshotKey.current = key;
      }
    } else {
      setSnapshots(null);
      snapshotKey.current = null;
    }
    if (page === "backup" && result.job) {
      const jobLogs = await api("/backup/jobs/current/logs?tail=60").catch(
        () => null,
      );
      setLogs(jobLogs?.logs || "");
    } else setLogs("");
  }, [page]);
  const loadNetwork = useCallback(async () => {
    const result = await api("/tailscale/status");
    setNetwork(result);
  }, []);
  const loadAccess = useCallback(async () => {
    const result = await api("/access");
    setAccess(result);
  }, []);

  const refresh = useCallback(
    async (full = false) => {
      if (refreshPending.current) return;
      refreshPending.current = true;
      try {
        const jobs = [loadServices()];
        if (full) jobs.push(loadStats());
        if (page === "backup" || full) jobs.push(loadBackup());
        if (page === "network" || full) jobs.push(loadNetwork());
        if (page === "access" || full) jobs.push(loadAccess());
        const results = await Promise.allSettled(jobs);
        const failed = results.find((result) => result.status === "rejected");
        setRefreshError(
          failed ? failed.reason?.message || "Aggiornamento parziale" : "",
        );
        setLastUpdated(new Date());
      } catch (error) {
        setRefreshError(error.message || "Aggiornamento non riuscito");
      } finally {
        refreshPending.current = false;
      }
    },
    [page, loadServices, loadStats, loadBackup, loadNetwork, loadAccess],
  );

  useEffect(() => {
    let alive = true;
    probe()
      .then((result) => {
        if (!alive) return;
        if (result === "ok") {
          setAuthenticated(true);
          setAuthMessage("");
        } else if (result === "token") {
          if (getToken()) {
            clearToken();
            setAuthMessage("Il token salvato non è valido.");
          } else setWelcome(true);
        } else if (result === "locked")
          setAuthMessage(
            "Troppi tentativi. Attendi un minuto prima di riprovare.",
          );
        else if (result === "config")
          setAuthMessage("Configura il token sul server e riavvia il backend.");
        else
          setAuthMessage(
            "Server non raggiungibile: puoi comunque inserire il token.",
          );
      })
      .finally(() => {
        if (alive) setChecking(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const onLost = () => {
      clearToken();
      setAuthenticated(false);
      setAuthMessage("Sessione scaduta. Inserisci nuovamente il token.");
    };
    window.addEventListener("hs:auth-lost", onLost);
    return () => window.removeEventListener("hs:auth-lost", onLost);
  }, [authenticated]);

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
    const statsTimer = window.setInterval(() => {
      if (!document.hidden)
        loadStats().catch((error) => setRefreshError(error.message));
    }, 15000);
    const onVisible = () => {
      if (!document.hidden) run(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.clearInterval(statsTimer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [authenticated, refresh]);

  useEffect(() => {
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      setInstallPrompt(e);
    };
    const installed = () => setInstallPrompt(null);
    window.addEventListener("beforeinstallprompt", handler);
    window.addEventListener("appinstalled", installed);
    return () => {
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", installed);
    };
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    api("/modes")
      .then(setModes)
      .catch(() => setModes([]));
  }, [authenticated]);

  async function serviceAction(service, action) {
    if (busyServices.has(service.id)) return;
    if (action === "stop" && !window.confirm("Arrestare " + service.name + "?"))
      return;
    setBusyServices((prev) => new Set(prev).add(service.id));
    try {
      await api("/services/" + service.id + "/" + action, { method: "POST" });
      notify(service.name + ": operazione completata");
      await Promise.all([loadServices(), loadStats()]);
    } catch (error) {
      notify(error.message);
    } finally {
      setBusyServices((prev) => {
        const next = new Set(prev);
        next.delete(service.id);
        return next;
      });
    }
  }

  async function applyMode(mode) {
    if (
      busyMode ||
      !window.confirm("Applicare la modalità «" + mode.name + "»?")
    )
      return;
    setBusyMode(true);
    try {
      const result = await api("/modes/" + mode.id + "/apply", {
        method: "POST",
      });
      setServices(result.services || []);
      notify("Modalità " + mode.name + " applicata");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusyMode(false);
    }
  }

  async function startJob(kind) {
    if (busyJob) return;
    setBusyJob(true);
    try {
      const result = await api("/backup/jobs", {
        method: "POST",
        json: { kind },
      });
      notify(result.warnings?.join(" · ") || "Operazione backup avviata");
      await loadBackup();
    } catch (error) {
      notify(error.message);
    } finally {
      setBusyJob(false);
    }
  }

  function navigate(id) {
    navigateTo("/" + id);
    setSidebarOpen(false);
  }
  function logout() {
    clearToken();
    setAuthenticated(false);
    setAuthMessage("");
    navigateTo("/overview");
  }

  const active = services.filter((s) => s.status === "running").length;
  const partial = services.filter((s) => s.status === "partial").length;
  const pageTitle = NAV.find((n) => n.id === page)?.label || "Panoramica";

  if (checking)
    return (
      <main className="loading-screen">
        <img className="brand-mark" alt="" src="/icons/icon.svg" />
        <p>Connessione a HomeServer…</p>
      </main>
    );
  if (!authenticated && welcome) return <Welcome onEnter={enter} />;
  if (!authenticated)
    return (
      <Login
        help={help}
        message={authMessage}
        onLogin={() => {
          setAuthMessage("");
          setAuthenticated(true);
        }}
      />
    );

  return (
    <div className="app-shell">
      <aside className={"sidebar " + (sidebarOpen ? "open" : "")}>
        <div className="sidebar-brand">
          <img className="brand-mark" alt="" src="/icons/icon.svg" />
          <div>
            <strong>HomeServer</strong>
          </div>
        </div>

        <nav className="side-nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              aria-current={page === item.id ? "page" : undefined}
              className={page === item.id ? "active" : ""}
              onClick={() => navigate(item.id)}
            >
              <Icon>{item.icon}</Icon>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-indicator">
            <i /> Sessione attiva
          </div>
          <button className="sidebar-logout" onClick={logout}>
            Esci dal pannello
          </button>
        </div>
      </aside>
      {sidebarOpen && (
        <button
          className="scrim"
          aria-label="Chiudi navigazione"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu"
            aria-expanded={sidebarOpen}
            aria-label="Apri navigazione"
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>
          <div>
            <h1>{pageTitle}</h1>
          </div>
          <div className="topbar-right">
            <div className="top-status">
              <span className="good-dot" />
              {active} <span className="warn-dot" />
              {partial} <span className="bad-dot" />
              {services.length - active - partial}
            </div>
            <span className="updated-label">
              {lastUpdated
                ? "Aggiornato " + lastUpdated.toLocaleTimeString("it-IT")
                : "Aggiornamento…"}
            </span>
            <button
              className="icon-button"
              aria-label="Aggiorna"
              title="Aggiorna"
              onClick={() => refresh(true)}
            >
              ↻
            </button>
          </div>
        </header>
        <main className="content">
          {refreshError && (
            <div className="inline-error" role="alert">
              {refreshError}
            </div>
          )}
          {(stats?.setup?.missing?.length || stats?.setup?.root_owned?.length) >
            0 &&
            (page === "overview" || page === "services") && (
              <details className="warning-box">
                <summary>Verifica le cartelle sul server</summary>
                <p>
                  Esegui <code>./src/scripts/sync-env.sh</code>.
                </p>
                {stats.setup.missing?.length > 0 && (
                  <p>Mancanti: {stats.setup.missing.join(", ")}</p>
                )}
                {stats.setup.root_owned?.length > 0 && (
                  <p>
                    Di proprietà di root: {stats.setup.root_owned.join(", ")}
                  </p>
                )}
              </details>
            )}
          {page === "overview" && (
            <Overview
              services={services}
              stats={stats}
              backup={backup}
              network={network}
              onNavigate={navigate}
            />
          )}
          {page === "services" && (
            <ServicesPage
              services={services}
              stats={stats}
              onAction={serviceAction}
              busyServices={busyServices}
              modes={modes}
              onMode={applyMode}
              busyMode={busyMode}
            />
          )}
          {page === "backup" && (
            <BackupPage
              data={backup}
              snapshots={snapshots}
              logs={logs}
              onJob={startJob}
              loading={busyJob}
            />
          )}
          {page === "network" && (
            <NetworkPage
              data={network}
              onLogout={logout}
              installPrompt={installPrompt}
            />
          )}
          {page === "access" && <AccessPage data={access} />}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <DashboardApp />
    </HashRouter>
  );
}
