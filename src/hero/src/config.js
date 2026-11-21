// Tutto cio' che si cambia per adattare l'hero sta qui.

// Flusso HLS dello sfondo. Dal browser parte una richiesta verso *.mux.com a ogni apertura della schermata iniziale
// (la CSP in nginx/security-headers.conf lo consente solo per media-src e connect-src). Per non dipendere da un servizio esterno:
// scarica il video, mettilo in src/frontend/ e metti qui un percorso locale (es. "/sfondo.mp4": il VideoPlayer lo riproduce senza hls.js).
export const VIDEO_SRC = "https://stream.mux.com/9JXDljEVWYwWu01PUkAemafDugK89o01BR6zqJ3aS9u00A.m3u8";

export const BRAND = "Homeserver";

// Voci della barra. `go` e' la scheda del pannello che si apre dopo l'accesso; `soon` = barrata (non ancora disponibile).
export const NAV = [
  { label: "Servizi", go: "servizi", active: true },
  { label: "Backup", go: "backup" },
  { label: "Rete", go: "rete" },
  { label: "Archivio", go: "servizi", soon: true },
  { label: "Accessi", go: "accessi" },
];

export const BADGES = [
  { label: "Tailscale", icon: "shield" },
  { label: "Docker", icon: "box" },
  { label: "Immich", icon: "photo" },
];

// Segnaposto: marchi generici disegnati qui, con il nome del servizio in testo. Niente loghi reali.
export const LOGOS = [
  { label: "Jellyfin", icon: "play" },
  { label: "Immich", icon: "photo" },
  { label: "Vaultwarden", icon: "key" },
  { label: "Pi-hole", icon: "shield" },
  { label: "Tailscale", icon: "net" },
  { label: "qBittorrent", icon: "down" },
];

export const COPY = {
  ctaNav: "Entra",
  badgeLead: "Integrato con",
  title: "Il tuo server di casa, sotto controllo",
  subtitle: "Film, foto, password e download su un unico server privato. Accendi, spegni e tieni d'occhio ogni servizio da un solo pannello, anche fuori casa.",
  primary: "Entra nel pannello",
  secondary: "Hai perso il token?",
};
