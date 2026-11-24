// Icone segnaposto, disegnate a mano: nessun marchio reale.
const P = {
  shield: <><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z" /><path d="m9 12 2 2 4-4" /></>,
  box: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="M4 7.5 12 12l8-4.5M12 12v9" /></>,
  photo: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10.5" r="1.6" /><path d="m4 17 5-4.5 3.5 3L15 13.5l5 4.5" /></>,
  play: <><circle cx="12" cy="12" r="9" /><path d="m10 8.5 5.5 3.5-5.5 3.5z" /></>,
  key: <><circle cx="8" cy="12" r="3.5" /><path d="M11.5 12H21M17.5 12v3.5M20.5 12v2.5" /></>,
  net: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>,
  down: <><path d="M12 4v12M7 11.5l5 5 5-5M5 20h14" /></>,
};

export function Icon({ name, size = 18, className = "" }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {P[name]}
    </svg>
  );
}
