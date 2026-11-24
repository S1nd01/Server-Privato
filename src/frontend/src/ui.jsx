import React from "react";

export const STATUS = {
  running: "Attivo",
  partial: "Parziale",
  stopped: "Fermo",
  not_created: "Non creato",
  failed: "Errore",
  exited: "Terminato",
  created: "In avvio",
  restarting: "Riavvio",
};
export const STATUS_CLASS = {
  running: "good",
  partial: "warn",
  stopped: "muted",
  not_created: "muted",
  failed: "bad",
  exited: "good",
  created: "warn",
  restarting: "warn",
};

export function Card({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={"panel " + className}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Progress({ value }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <progress
      className={pct >= 85 ? "danger" : ""}
      value={pct}
      max="100"
      aria-label="Utilizzo"
    />
  );
}
export function StateDot({ status }) {
  return (
    <span
      className={"state-dot " + (STATUS_CLASS[status] || "muted")}
      aria-label={STATUS[status] || status}
    />
  );
}
export function Empty({ children }) {
  return <div className="empty-state">{children}</div>;
}
export function ErrorMessage({ children }) {
  return (
    <div className="inline-error" role="alert">
      {children}
    </div>
  );
}
