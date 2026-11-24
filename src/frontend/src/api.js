const TOKEN_KEY = "hs_token";
const getStore = (kind) => {
  try {
    return kind === "local" ? localStorage : sessionStorage;
  } catch {
    return null;
  }
};

export function getToken() {
  for (const kind of ["session", "local"]) {
    try {
      const value = getStore(kind)?.getItem(TOKEN_KEY);
      if (value) return value;
    } catch {}
  }
  return "";
}
export function setToken(value, remember) {
  clearToken();
  try {
    getStore(remember ? "local" : "session")?.setItem(TOKEN_KEY, value);
  } catch {}
}
export function clearToken() {
  for (const kind of ["session", "local"]) {
    try {
      getStore(kind)?.removeItem(TOKEN_KEY);
    } catch {}
  }
}
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}
export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["X-API-Token"] = token;
  let body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  let response;
  try {
    response = await fetch("/api" + path, {
      method: options.method || "GET",
      headers,
      body,
      cache: "no-store",
      signal: options.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Server non raggiungibile", 0);
  }
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("hs:auth-lost"));
    const data = await response.json().catch(() => ({}));
    const detail =
      typeof data.detail === "string" ? data.detail : response.statusText;
    throw new ApiError(detail || "Errore", response.status);
  }
  if (response.status === 204) return null;
  return response.json();
}
export async function probe() {
  try {
    await api("/session");
    return "ok";
  } catch (error) {
    if (error.status === 401) return "token";
    if (error.status === 429) return "locked";
    if (error.status === 503) return "config";
    return "offline";
  }
}
export const formatBytes = (n) => {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return (
    n.toLocaleString("it-IT", { maximumFractionDigits: i ? 1 : 0 }) +
    " " +
    units[i]
  );
};
export const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("it-IT", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
};
export const formatDuration = (seconds) => {
  if (seconds == null) return "—";
  if (seconds < 60) return "<1 min";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min";
  if (seconds < 86400)
    return (
      Math.floor(seconds / 3600) +
      " h " +
      Math.floor((seconds % 3600) / 60) +
      " min"
    );
  return (
    Math.floor(seconds / 86400) +
    " g " +
    Math.floor((seconds % 86400) / 3600) +
    " h"
  );
};
