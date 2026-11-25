import React, { useEffect, useState } from "react";
import { api, formatBytes, formatDuration } from "./api.js";
import {
  Card,
  Empty,
  Progress,
  StateDot,
  STATUS,
  STATUS_CLASS,
} from "./ui.jsx";

function HostPanel({ host }) {
  if (!host)
    return (
      <Card title="Risorse server">
        <Empty>Dati del server non disponibili.</Empty>
      </Card>
    );
  const mem = host.mem_total ? (host.mem_used / host.mem_total) * 100 : null;
  const disks = host.disks || [];
  const values = [
    { label: "CPU", value: host.cpu_percent, detail: host.cores + " core" },
    {
      label: "Memoria",
      value: mem,
      detail:
        host.mem_used == null || host.mem_total == null
          ? "—"
          : `${formatBytes(host.mem_used)} occupati · ${formatBytes(Math.max(0, host.mem_total - host.mem_used))} disponibili`,
    },
    ...disks.map((d) => ({
      label: "Disco · " + d.label,
      value: d.total ? (d.used / d.total) * 100 : null,
      detail: `${formatBytes(d.used)} occupati · ${formatBytes(Math.max(0, d.total - d.used))} disponibili`,
    })),
  ];
  return (
    <Card
      title="Risorse del server"
      subtitle={"Attivo da " + formatDuration(host.uptime_s)}
      className="host-panel"
    >
      <div className="resource-grid">
        {values.map((item) => (
          <div className="resource" key={item.label}>
            <div className="resource-heading">
              <span>{item.label}</span>
              <strong>
                {item.value == null ? "—" : item.value.toFixed(1) + "%"}
              </strong>
            </div>
            <Progress value={item.value} />
            <small>{item.detail}</small>
          </div>
        ))}
      </div>
      <div className="host-meta">
        <span>{host.cores} core logici</span>
        <span>Carico {host.load ? host.load.join(" · ") : "—"}</span>
        <span>
          Temperatura {host.temp_c == null ? "n/d" : host.temp_c + " °C"}
        </span>
      </div>
    </Card>
  );
}

function ServiceActions({
  service,
  onAction,
  busy,
  detailed = false,
  children,
}) {
  const active = service.status === "running" || service.status === "partial";
  const onTailnet = location.hostname.endsWith(".ts.net");
  const url =
    service.url_port && (!service.ts_only || onTailnet)
      ? `${onTailnet ? "https" : service.scheme}://${location.hostname}:${service.url_port}${service.path || ""}`
      : null;

  return (
    <div className="service-actions">
      {detailed && url && active && (
        <a
          className="button subtle"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Apri ${service.name}`}
        >
          Apri ↗
        </a>
      )}
      <button
        className={"button " + (active ? "danger" : "primary")}
        disabled={busy || (active && !service.can_stop)}
        onClick={() => onAction(service, active ? "stop" : "start")}
      >
        {active ? "Arresta" : "Avvia"}
      </button>
      {detailed && (
        <button
          className="button subtle"
          disabled={
            busy || !service.can_stop || service.status === "not_created"
          }
          onClick={() => onAction(service, "restart")}
        >
          Riavvia
        </button>
      )}
      {children}
    </div>
  );
}

function ServiceStatus({ service }) {
  return (
    <span
      className={"status-pill " + (STATUS_CLASS[service.status] || "muted")}
    >
      {STATUS[service.status] || service.status}
    </span>
  );
}

function ServiceCard({ service, onAction, busy, onDetails }) {
  return (
    <article className="service-card" aria-busy={busy}>
      <ServiceStatus service={service} />
      <h3 className="card-service-name">{service.name}</h3>
      <ServiceActions service={service} onAction={onAction} busy={busy}>
        <a
          className="button subtle"
          id={"service-" + service.id}
          href={"#/services/" + service.id}
          aria-label={`Dettagli ${service.name}`}
          onClick={(event) => {
            if (
              event.button !== 0 ||
              event.metaKey ||
              event.ctrlKey ||
              event.shiftKey ||
              event.altKey
            )
              return;
            event.preventDefault();
            onDetails(service.id);
          }}
        >
          Dettagli
        </a>
      </ServiceActions>
    </article>
  );
}

export function ServiceDetail({ service, stats, onAction, busy }) {
  const warnings = (service.containers || []).filter(
    ({ name, status }) =>
      ["restarting", "dead"].includes(status) ||
      (service.status === "partial" && status !== "running") ||
      stats?.containers?.[name]?.health === "unhealthy",
  );
  return (
    <div className="detail-grid" aria-busy={busy}>
      <Card
        title="Stato del servizio"
        action={<ServiceStatus service={service} />}
      >
        <p>{service.description}</p>
        <ServiceActions
          service={service}
          onAction={onAction}
          busy={busy}
          detailed
        />
        {stats && (
          <dl className="detail-metrics">
            <div>
              <dt>CPU host</dt>
              <dd>
                {stats.cpu_host_percent == null
                  ? "—"
                  : stats.cpu_host_percent.toFixed(1) + "%"}
              </dd>
            </div>
            <div>
              <dt>RAM</dt>
              <dd>{formatBytes(stats.mem_bytes)}</dd>
            </div>
            <div>
              <dt>Tempo di attività</dt>
              <dd>{formatDuration(stats.uptime_s)}</dd>
            </div>
            <div>
              <dt>Riavvii</dt>
              <dd>{stats.restarts ?? "—"}</dd>
            </div>
          </dl>
        )}
      </Card>
      <Card title="Container associati">
        {service.containers?.length ? (
          <ul className="container-list">
            {service.containers.map((container) => (
              <li className="container-row" key={container.name}>
                <StateDot status={container.status} />
                <span>{container.name}</span>
                <small>{STATUS[container.status] || container.status}</small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Nessun container associato.</Empty>
        )}
      </Card>
      {warnings.length > 0 && (
        <Card title="Avvisi" className="service-warnings">
          <ul>
            {warnings.map(({ name, status }) => (
              <li key={name}>
                {name}:{" "}
                {stats?.containers?.[name]?.health === "unhealthy"
                  ? "controllo di salute fallito"
                  : STATUS[status] || status}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function AdminActivity() {
  const [days, setDays] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api("/session/history", { signal: controller.signal })
      .then(setDays)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, []);

  const maximum = Math.max(1, ...(days || []).map((day) => day.count));
  return (
    <Card
      title="Amministratore"
      subtitle="Accessi al pannello negli ultimi 7 giorni (UTC)"
    >
      {error ? (
        <Empty>Storico accessi non disponibile.</Empty>
      ) : !days ? (
        <Empty>Caricamento storico…</Empty>
      ) : (
        <ul className="login-chart">
          {days.map(({ day, count }) => {
            const label = new Intl.DateTimeFormat("it-IT", {
              day: "numeric",
              month: "short",
              timeZone: "UTC",
            }).format(new Date(day));
            return (
              <li key={day}>
                <span>{label}</span>
                <progress
                  aria-label={`Accessi del ${label}`}
                  value={count}
                  max={maximum}
                />
                <strong>{count}</strong>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function ResourcesPage({ stats, services }) {
  return (
    <div className="page-stack">
      <AdminActivity />
      <HostPanel host={stats?.host} />
      <Card title="Consumi per servizio">
        {stats && services.length ? (
          <div className="resource-table">
            <table>
              <thead>
                <tr>
                  <th scope="col">Servizio</th>
                  <th scope="col">CPU host</th>
                  <th scope="col">RAM</th>
                </tr>
              </thead>
              <tbody>
                {services.map((service) => {
                  const usage = stats.services?.[service.id];
                  return (
                    <tr key={service.id}>
                      <th scope="row">
                        <a href={"#/services/" + service.id}>{service.name}</a>
                      </th>
                      <td>
                        {usage?.cpu_host_percent == null
                          ? "—"
                          : usage.cpu_host_percent.toFixed(1) + "%"}
                      </td>
                      <td>{formatBytes(usage?.mem_bytes)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Consumi dei servizi non disponibili.</Empty>
        )}
      </Card>
    </div>
  );
}

export function ServicesPage({
  services,
  onAction,
  busyServices,
  modes,
  onMode,
  busyMode,
  onDetails,
}) {
  const groups = [
    {
      title: "Servizi",
      rows: services.filter((service) => service.group !== "utility"),
    },
    {
      title: "Utility",
      rows: services.filter((service) => service.group === "utility"),
    },
  ];
  return (
    <div className="page-stack">
      {modes.length > 0 && (
        <div
          className="mode-list service-modes"
          aria-label="Modalità operative"
        >
          {modes.map((mode) => (
            <button
              className="button subtle"
              key={mode.id}
              disabled={busyMode}
              title={mode.description}
              onClick={() => onMode(mode)}
            >
              {mode.name}
            </button>
          ))}
        </div>
      )}
      {!services.length && <Empty>In attesa dell’elenco dei servizi…</Empty>}
      {groups.map(
        ({ title, rows }) =>
          rows.length > 0 && (
            <section className="service-section" aria-label={title} key={title}>
              {title === "Utility" && <h2>{title}</h2>}
              <div className="service-grid">
                {rows.map((service) => (
                  <ServiceCard
                    key={service.id}
                    service={service}
                    busy={busyServices.has(service.id)}
                    onAction={onAction}
                    onDetails={onDetails}
                  />
                ))}
              </div>
            </section>
          ),
      )}
    </div>
  );
}
