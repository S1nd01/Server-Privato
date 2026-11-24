import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { HashRouter, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, probe } from "./api.js";
import BackupPage from "./Backup.jsx";
import Login from "./Login.jsx";
import { AccessPage, NetworkPage } from "./Network.jsx";
import { ResourcesPage, ServiceDetail, ServicesPage } from "./Services.jsx";
import Welcome from "./Welcome.jsx";

const NAV = [
  { id: "backup", label: "Backup" },
  { id: "network", label: "Rete" },
  { id: "access", label: "Accessi" },
  { id: "resources", label: "Risorse" },
];

function DashboardApp() {
  const routerLocation = useLocation();
  const navigateTo = useNavigate();
  const route = routerLocation.pathname.replace(/^\//, "");
  const serviceId = /^services\/([a-z0-9-]+)$/.exec(route)?.[1];
  const legacy = { rete: "network", accessi: "access" };
  const page = serviceId
    ? "detail"
    : NAV.some((item) => item.id === route)
      ? route
      : Object.hasOwn(legacy, route)
        ? legacy[route]
        : "services";
  const gridScroll = useRef(0);
  const gridFocus = useRef(null);

  useLayoutEffect(() => {
    if (page === "services") {
      document
        .getElementById(gridFocus.current)
        ?.focus({ preventScroll: true });
      window.scrollTo(0, gridScroll.current);
    } else {
      window.scrollTo(0, 0);
    }
  }, [page, serviceId]);

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

  function openService(id) {
    gridScroll.current = window.scrollY;
    gridFocus.current = "service-" + id;
    navigateTo("/services/" + id, { state: { fromGrid: true } });
  }

  function backToServices() {
    if (routerLocation.state?.fromGrid) navigateTo(-1);
    else navigateTo("/services");
  }

  function logout() {
    clearToken();
    setAuthenticated(false);
    setAuthMessage("");
    navigateTo("/services");
  }

  const active = services.filter((s) => s.status === "running").length;
  const selected = services.find((service) => service.id === serviceId);
  const pageTitle =
    page === "detail"
      ? selected?.name || "Dettaglio servizio"
      : NAV.find((item) => item.id === page)?.label || "Servizi";

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
      <header className="homeserver-header">
        <a
          className="home-link"
          href="#/services"
          aria-current={page === "services" ? "page" : undefined}
        >
          <img className="brand-mark" alt="" src="/icons/icon.svg" />
          <strong>HomeServer</strong>
        </a>
        <nav className="top-nav" aria-label="Navigazione principale">
          {NAV.map((item) => (
            <a
              key={item.id}
              href={"#/" + item.id}
              aria-current={page === item.id ? "page" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </header>
      <div className="work-area">
        <main className="content">
          {(page === "detail" || page === "resources") && (
            <button
              type="button"
              className="button subtle back-link"
              onClick={backToServices}
            >
              ← Tutti i servizi
            </button>
          )}
          <div className="page-heading">
            <div>
              <h1>{pageTitle}</h1>
              {page === "services" && services.length > 0 && (
                <p>
                  {active} attivi su {services.length}
                </p>
              )}
            </div>
            <div className="page-tools">
              {lastUpdated && (
                <small>
                  Aggiornato {lastUpdated.toLocaleTimeString("it-IT")}
                </small>
              )}
              <button
                className="icon-button"
                aria-label="Aggiorna"
                title="Aggiorna"
                onClick={() => refresh(true)}
              >
                ↻
              </button>
            </div>
          </div>
          {refreshError && (
            <div className="inline-error" role="alert">
              {refreshError}
            </div>
          )}
          {(stats?.setup?.missing?.length || stats?.setup?.root_owned?.length) >
            0 &&
            (page === "resources" || page === "services") && (
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
          {page === "services" && (
            <ServicesPage
              services={services}
              onAction={serviceAction}
              busyServices={busyServices}
              modes={modes}
              onMode={applyMode}
              busyMode={busyMode}
              onDetails={openService}
            />
          )}
          {page === "resources" && (
            <ResourcesPage stats={stats} services={services} />
          )}
          {page === "detail" &&
            (selected ? (
              <ServiceDetail
                service={selected}
                stats={stats?.services?.[selected.id]}
                onAction={serviceAction}
                busy={busyServices.has(selected.id)}
              />
            ) : (
              <p className="empty-state">
                {services.length
                  ? "Servizio non disponibile."
                  : "In attesa dell’elenco dei servizi…"}
              </p>
            ))}
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
          <footer className="homeserver-footer">
            <button className="text-button" onClick={logout}>
              Esci dal pannello
            </button>
          </footer>
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
