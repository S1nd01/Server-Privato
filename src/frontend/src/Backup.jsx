import React, { useState } from "react";
import { formatBytes, formatDate } from "./api.js";
import { Card, Empty, StateDot } from "./ui.jsx";

export default function BackupPage({ data, snapshots, logs, onJob, loading }) {
  const [confirmForget, setConfirmForget] = useState(false);
  const running = data?.job?.result === "running";
  const blocked = running || loading || data?.disk?.present === false;
  const actions = data?.initialized
    ? [
        { kind: "backup", label: "Esegui backup", primary: true },
        { kind: "check", label: "Controlla integrità" },
        { kind: "forget", label: "Pulisci vecchie copie", danger: true },
      ]
    : [{ kind: "init", label: "Prepara archivio", primary: true }];
  return (
    <div className="page-stack">
      <Card title="Stato backup" subtitle="Archivio cifrato Restic">
        {!data ? (
          <Empty>Caricamento stato backup…</Empty>
        ) : !data.configured ? (
          <>
            <div className="warning-box">Backup non configurato</div>
            <ul className="problem-list">
              {data.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <div className="backup-facts">
              <div>
                <span>Ultima copia</span>
                <strong>
                  {data.last_backup_at
                    ? formatDate(data.last_backup_at)
                    : "Nessuna copia"}
                </strong>
              </div>
              <div>
                <span>Modalità</span>
                <strong>Manuale</strong>
              </div>
              <div>
                <span>Archivio</span>
                <strong>
                  {data.initialized
                    ? "Inizializzato"
                    : data.initialized === false
                      ? "Da inizializzare"
                      : "Non verificabile"}
                </strong>
              </div>
              <div>
                <span>Conservazione</span>
                <strong>
                  {data.keep.daily} giorni · {data.keep.weekly} settimane ·{" "}
                  {data.keep.monthly} mesi
                </strong>
              </div>
            </div>
            {data.disk && (
              <div className="status-line">
                <StateDot status={data.disk.present ? "running" : "failed"} />
                {data.disk.present
                  ? "Disco esterno collegato"
                  : "Disco esterno non collegato"}
              </div>
            )}
            <div className="action-row">
              {actions.map((a) => (
                <button
                  key={a.kind}
                  className={
                    "button " +
                    (a.primary ? "primary" : a.danger ? "danger" : "subtle")
                  }
                  disabled={blocked}
                  onClick={() =>
                    a.kind === "forget" ? setConfirmForget(true) : onJob(a.kind)
                  }
                >
                  {a.label}
                </button>
              ))}
            </div>
            {confirmForget && (
              <div className="confirm-box">
                <p>
                  Confermi la pulizia? Verranno conservati {data.keep.daily}{" "}
                  backup giornalieri, {data.keep.weekly} settimanali e{" "}
                  {data.keep.monthly} mensili; gli altri verranno eliminati.
                </p>
                <button
                  className="button danger"
                  disabled={blocked}
                  onClick={() => {
                    setConfirmForget(false);
                    onJob("forget");
                  }}
                >
                  Conferma eliminazione
                </button>
                <button
                  className="button subtle"
                  onClick={() => setConfirmForget(false)}
                >
                  Annulla
                </button>
              </div>
            )}
            {data.stale && (
              <p className="warning-box">Verifica la data dell’ultima copia.</p>
            )}
            {(data.last_job_warnings || []).map((warning) => (
              <p className="warning-box" key={warning}>
                {warning}
              </p>
            ))}
            <details>
              <summary>Origini del backup</summary>
              <ul>
                {(data.sources || []).map((source) => (
                  <li key={source.path}>
                    {source.path}
                    {source.exists ? "" : " (assente)"}
                  </li>
                ))}
              </ul>
            </details>
            <p className="muted-copy">
              Percorso archivio: {data.repo || "non impostato"}. Il backup viene
              avviato manualmente.
            </p>
          </>
        )}
      </Card>
      {data?.job && (
        <Card
          title="Ultima operazione"
          subtitle={
            {
              running: "In corso",
              ok: "Riuscito",
              failed: "Non riuscito",
              warning: "Completato con avvisi",
            }[data.job.result] || data.job.result
          }
        >
          <div className="status-line">
            <StateDot
              status={
                running
                  ? "partial"
                  : data.job.result === "failed"
                    ? "failed"
                    : "running"
              }
            />
            <strong>{data.job.kind}</strong>
            <span>
              {data.job.started_at ? formatDate(data.job.started_at) : ""}
            </span>
          </div>
          <pre className="log-output">{logs || "Log non disponibile"}</pre>
        </Card>
      )}
      <Card title="Copie disponibili" subtitle="Snapshot Restic recenti">
        {!snapshots ? (
          <Empty>
            {data?.initialized
              ? "Caricamento snapshot…"
              : "Gli snapshot compariranno dopo l'inizializzazione."}
          </Empty>
        ) : snapshots.length === 0 ? (
          <Empty>Nessuno snapshot disponibile.</Empty>
        ) : (
          <div className="snapshot-list">
            {snapshots.map((s) => (
              <div className="snapshot-row" key={s.id}>
                <div>
                  <strong>{formatDate(s.time)}</strong>
                  <small>ID {s.id}</small>
                </div>
                <div>
                  <strong>{formatBytes(s.added_bytes)}</strong>
                  <small>Nuovi dati</small>
                </div>
                <div>
                  <strong>{formatBytes(s.total_bytes)}</strong>
                  <small>Elaborati</small>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
