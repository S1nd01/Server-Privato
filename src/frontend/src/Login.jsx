import React, { useState } from "react";
import { clearToken, probe, setToken } from "./api.js";
import { ErrorMessage } from "./ui.jsx";

export default function Login({ onLogin, message, help }) {
  const [token, setValue] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    if (!token.trim() || busy) return;
    setBusy(true);
    setError("");
    setToken(token.trim(), remember);
    const result = await probe();
    setBusy(false);
    if (result === "ok") {
      setValue("");
      onLogin();
    } else {
      clearToken();
      setError(
        result === "locked"
          ? "Troppi tentativi. Attendi un minuto."
          : result === "config"
            ? "Configura il token sul server e riavvia il backend."
            : result === "offline"
              ? "Il server non risponde."
              : "Token non valido.",
      );
    }
  }
  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <img className="brand-mark" alt="" src="/icons/icon.svg" />
        <h1>Accesso amministratore</h1>
        <p className="muted-copy">
          Inserisci il token del pannello per continuare.
        </p>
        <label htmlFor="api-token">Token API</label>
        <input
          id="api-token"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setValue(e.target.value)}
          required
        />
        <label className="remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />{" "}
          Ricorda su questo dispositivo
        </label>
        {(error || message) && <ErrorMessage>{error || message}</ErrorMessage>}
        <button className="button primary full" disabled={busy}>
          {busy ? "Verifica…" : "Accedi"}
        </button>
        <details className="login-foot" open={help || undefined}>
          <summary>Dove trovo il token?</summary>Generalo sul server con{" "}
          <code>./src/scripts/gen-api-token.sh</code>.
        </details>
      </form>
    </main>
  );
}
