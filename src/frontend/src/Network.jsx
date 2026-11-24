import React, { useState } from "react";
import { formatDate, getToken } from "./api.js";
import { Card, Empty, StateDot } from "./ui.jsx";

export function NetworkPage({ data, onLogout, installPrompt }) {
  return (
    <div className="page-stack">
      <Card title="Tailscale" subtitle="Connessione privata al server">
        {!data ? (
          <Empty>Caricamento stato rete…</Empty>
        ) : (
          <>
            <div className="status-line">
              <StateDot
                status={
                  data.state === "Running"
                    ? "running"
                    : data.state === "NeedsLogin"
                      ? "partial"
                      : "stopped"
                }
              />
              <strong>
                {data.state === "Running" ? "Connesso" : data.state}
              </strong>
              <span>{data.tailnet || ""}</span>
            </div>
            {data.login_url && (
              <a
                className="button primary"
                href={data.login_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Completa accesso Tailscale ↗
              </a>
            )}
            {data.https_url ? (
              <div className="remote-address">
                <span>Indirizzo HTTPS del server</span>
                <strong>{data.https_url}</strong>
                <div className="action-row">
                  <a
                    className="button primary"
                    href={data.https_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Apri pannello
                  </a>
                  <button
                    className="button subtle"
                    onClick={() =>
                      navigator.clipboard?.writeText(data.https_url)
                    }
                  >
                    Copia indirizzo
                  </button>
                </div>
              </div>
            ) : (
              <p className="muted-copy">
                Per l'accesso HTTPS abilita MagicDNS e HTTPS Certificates nella
                console Tailscale.
              </p>
            )}
            {(data.health || []).map((item, i) => (
              <div className="warning-box" key={i}>
                {item}
              </div>
            ))}
          </>
        )}
      </Card>
      <Card
        title="Dispositivi nella rete"
        subtitle={(data?.peers?.length || 0) + " dispositivi conosciuti"}
      >
        {data?.peers?.length ? (
          <div className="peer-list">
            {data.peers.map((p) => (
              <div className="peer-row" key={p.ips?.[0] || p.name}>
                <StateDot status={p.online ? "running" : "stopped"} />
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {p.os || "Sistema non identificato"} ·{" "}
                    {p.online
                      ? "Online"
                      : "Ultimo accesso " + formatDate(p.last_seen)}
                  </small>
                </div>
                <span>{p.ips?.[0] || ""}</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty>Nessun dispositivo o dati non disponibili.</Empty>
        )}
      </Card>
      <Card title="Applicazione" subtitle="Sessione e installazione">
        <p className="muted-copy">
          La sessione è conservata{" "}
          {getToken() ? "nel browser" : "per questa scheda"}.
        </p>
        {installPrompt && (
          <button
            className="button primary"
            onClick={async () => {
              await installPrompt.prompt();
            }}
          >
            Installa applicazione
          </button>
        )}
        <button className="button danger" onClick={onLogout}>
          Esci da questo dispositivo
        </button>
      </Card>
    </div>
  );
}

export function AccessPage({ data }) {
  const [copied, setCopied] = useState("");
  async function copy(command) {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(command);
      setTimeout(() => setCopied(""), 1800);
    } catch {
      setCopied("");
    }
  }
  const label = {
    mostra: "Si può rileggere",
    reimposta: "Si può reimpostare",
    impossibile: "Non recuperabile",
  };
  return (
    <Card
      title="Accessi e recupero"
      subtitle="Le password non vengono mostrate dal pannello"
    >
      <p className="muted-copy">
        Il recupero delle credenziali avviene dal terminale del server. Questa
        schermata non espone segreti.
      </p>
      {!data ? (
        <Empty>Caricamento…</Empty>
      ) : (
        <div className="access-list">
          {data.items.map((item) => (
            <div className="access-item" key={item.id}>
              <StateDot
                status={
                  item.ok === false
                    ? "failed"
                    : item.recovery === "impossibile"
                      ? "muted"
                      : "running"
                }
              />
              <div className="access-content">
                <div className="access-heading">
                  <strong>{item.name}</strong>
                  <span className="status-pill muted">
                    {label[item.recovery] || item.recovery}
                  </span>
                </div>
                <p>{item.where}</p>
                {item.note && <small>{item.note}</small>}
                {item.ok === false && (
                  <div className="warning-box">
                    Configurazione non rilevata.
                  </div>
                )}
                {item.command && (
                  <div className="command-line">
                    <code>{item.command}</code>
                    <button
                      className="text-button"
                      onClick={() => copy(item.command)}
                    >
                      {copied === item.command ? "Copiato" : "Copia"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
