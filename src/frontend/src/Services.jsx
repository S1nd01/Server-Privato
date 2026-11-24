import React from "react";
import { formatBytes, formatDate, formatDuration } from "./api.js";
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
      detail: formatBytes(host.mem_used) + " / " + formatBytes(host.mem_total),
    },
    ...disks.map((d) => ({
      label: "Disco · " + d.label,
      value: d.total ? (d.used / d.total) * 100 : null,
      detail: formatBytes(d.used) + " / " + formatBytes(d.total),
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

function ServiceCard({ service, stats, onAction, busy }) {
  const active = service.status === "running" || service.status === "partial";
  const usage = stats?.cpu_host_percent;
  const url =
    service.url_port &&
    (!service.ts_only || location.hostname.endsWith(".ts.net"))
      ? (location.hostname.endsWith(".ts.net") ? "https" : service.scheme) +
        "://" +
        location.hostname +
        ":" +
        service.url_port +
        (service.path || "")
      : null;
  return (
    <article className="service-card">
      <div className="service-title">
        <StateDot status={busy ? "partial" : service.status} />
        <div className="service-name">
          <strong>{service.name}</strong>
          <small>{service.description}</small>
        </div>
        <span
          className={"status-pill " + (STATUS_CLASS[service.status] || "muted")}
        >
          {STATUS[service.status] || service.status}
        </span>
      </div>
      <div className="service-stat">
        <strong>
          {active && usage != null
            ? usage.toFixed(1) + "%"
            : active
              ? "—"
              : "OFF"}
        </strong>
        <span>{active ? "CPU host" : "Servizio non attivo"}</span>
      </div>
      {stats && active && (
        <div className="service-meta">
          <span>RAM {formatBytes(stats.mem_bytes)}</span>
          <span>Uptime {formatDuration(stats.uptime_s)}</span>
          <span>Riavvii {stats.restarts ?? 0}</span>
        </div>
      )}
      <div className="service-actions">
        <button
          className="button subtle"
          disabled={
            busy || !service.can_stop || service.status === "not_created"
          }
          onClick={() => onAction(service, "restart")}
        >
          Riavvia
        </button>
        {url && active && (
          <a
            className="button subtle"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Apri servizio ↗
          </a>
        )}
        <button
          className={"button " + (active ? "danger" : "primary")}
          disabled={busy || (active && !service.can_stop)}
          onClick={() => onAction(service, active ? "stop" : "start")}
        >
          {active ? "Arresta" : "Avvia"}
        </button>
      </div>
      {service.containers?.length > 0 && (
        <details className="container-details">
          <summary>Container ({service.containers.length})</summary>
          {service.containers.map((c) => (
            <div className="container-row" key={c.name}>
              <StateDot status={c.status} />
              <span>{c.name}</span>
              <small>
                {STATUS[c.status] || c.status}
                {stats?.containers?.[c.name]?.health
                  ? " · " + stats.containers[c.name].health
                  : ""}
              </small>
            </div>
          ))}
        </details>
      )}
    </article>
  );
}

export function Overview({ services, stats, backup, network, onNavigate }) {
  const active = services.filter((s) => s.status === "running").length;
  const partial = services.filter((s) => s.status === "partial").length;
  const down = services.length - active - partial;
  return (
    <div className="dashboard-grid">
      <Card
        title="Servizi"
        subtitle={services.length + " gruppi configurati"}
        action={
          <button
            className="text-button"
            onClick={() => onNavigate("services")}
          >
            Tutti i servizi ↗
          </button>
        }
      >
        <div className="overview-services">
          {services.slice(0, 8).map((s) => (
            <div className="overview-service" key={s.id}>
              <StateDot status={s.status} />
              <span>{s.name}</span>
              <small>{STATUS[s.status] || s.status}</small>
            </div>
          ))}
        </div>
        <div className="summary-strip">
          <span className="good-text">{active} attivi</span>
          <span className="warn-text">{partial} parziali</span>
          <span className="bad-text">{down} fermi</span>
        </div>
      </Card>
      <HostPanel host={stats?.host} />
      <Card
        title="Backup"
        subtitle="Protezione dei dati"
        action={
          <button className="text-button" onClick={() => onNavigate("backup")}>
            Apri backup ↗
          </button>
        }
      >
        {backup ? (
          <>
            <div className="big-stat">
              {backup.last_backup_at
                ? formatDate(backup.last_backup_at)
                : "Nessuna copia"}
            </div>
            <p className="muted-copy">
              {backup.configured
                ? backup.stale
                  ? "Attenzione: backup da verificare."
                  : "Configurazione presente"
                : "Configurazione incompleta"}
            </p>
            {backup.disk && (
              <div className="status-line">
                <StateDot status={backup.disk.present ? "running" : "failed"} />
                {backup.disk.present
                  ? "Disco backup collegato"
                  : "Disco backup scollegato"}
              </div>
            )}
          </>
        ) : (
          <Empty>Stato backup non disponibile.</Empty>
        )}
      </Card>
      <Card
        title="Rete Tailscale"
        subtitle="Accesso remoto sicuro"
        action={
          <button className="text-button" onClick={() => onNavigate("network")}>
            Dettagli ↗
          </button>
        }
      >
        {network ? (
          <>
            <div className="status-line">
              <StateDot
                status={network.state === "Running" ? "running" : "partial"}
              />
              <strong>
                {network.state === "Running" ? "Connesso" : network.state}
              </strong>
            </div>
            <p className="muted-copy">{network.tailnet || "Rete privata"}</p>
            {network.https_url && (
              <a
                className="external-link"
                href={network.https_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {network.https_url}
              </a>
            )}
          </>
        ) : (
          <Empty>Stato rete non disponibile.</Empty>
        )}
      </Card>
    </div>
  );
}

export function ServicesPage({
  services,
  stats,
  onAction,
  busyServices,
  modes,
  onMode,
  busyMode,
}) {
  const regular = services.filter((s) => s.group !== "utility");
  const utilities = services.filter((s) => s.group === "utility");
  return (
    <div className="page-stack">
      {modes.length > 0 && (
        <Card
          title="Modalità operative"
          subtitle="Avvio e arresto coordinato dei gruppi"
        >
          <div className="mode-list">
            {modes.map((m) => (
              <button
                className="button subtle"
                key={m.id}
                disabled={busyMode}
                title={m.description}
                onClick={() => onMode(m)}
              >
                {m.name}
              </button>
            ))}
          </div>
        </Card>
      )}
      <Card title="Servizi" subtitle="Gestione dei container Docker">
        <div className="service-grid">
          {regular.map((s) => (
            <ServiceCard
              key={s.id}
              service={s}
              stats={stats?.services?.[s.id]}
              busy={busyServices.has(s.id)}
              onAction={onAction}
            />
          ))}
        </div>
      </Card>
      {utilities.length > 0 && (
        <Card title="Utility" subtitle="Servizi di supporto">
          {
            <div className="service-grid">
              {utilities.map((s) => (
                <ServiceCard
                  key={s.id}
                  service={s}
                  stats={stats?.services?.[s.id]}
                  busy={busyServices.has(s.id)}
                  onAction={onAction}
                />
              ))}
            </div>
          }
        </Card>
      )}
    </div>
  );
}
