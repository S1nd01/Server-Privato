# Schermata iniziale

La pagina che si vede **prima dell'accesso**: barra in vetro sfocato, badge, titolo animato, due pulsanti, fila di marchi e, sullo sfondo, un video HLS. Si ferma lì: dopo l'accesso il pannello è quello di sempre (JavaScript puro, nessun React).

È scritta in React + Tailwind CSS 3 + `motion` (Framer Motion) + `hls.js`, in `src/hero/`, e si compila **dentro Docker** durante `docker compose build`.

## Come si comporta

- Compare solo a chi **non** è autenticato, e solo la prima volta dopo l'apertura della pagina. Chi ha già un token valido non scarica nulla (né React né il video). Un token scaduto o rifiutato porta dritto al form, con il messaggio.
- «Entra», «Entra nel pannello» e le voci della barra portano al form di accesso; le voci (Servizi, Backup, Rete, Accessi) aprono poi quella scheda. «Hai perso il token?» apre il form con l'aiuto già espanso. «Archivio» è barrata: è un segnaposto per quando esisterà.
- **L'accesso non dipende mai dall'hero.** Se il modulo non si carica (build assente, rete, errore) `app.js` passa direttamente al form.
- Con «riduci movimento» attivo nel sistema: niente animazioni e il video non parte.
- A scheda nascosta il video si ferma; all'uscita dalla schermata il player viene distrutto e smette di scaricare.

## Il video

`VIDEO_SRC` in `src/hero/src/config.js` punta a un flusso `.m3u8` di Mux. Dal browser parte quindi una richiesta verso `*.mux.com` a **ogni** apertura della schermata iniziale: Mux vede l'indirizzo IP di chi apre il pannello e quando lo fa. Per questo la CSP (`nginx/security-headers.conf`) ammette quell'host solo in `media-src` e `connect-src`, e nient'altro. Dettagli in [security.md](security.md#schermata-iniziale-e-video-esterno).

Se il flusso non parte (offline, bloccato) lo sfondo resta nero e tutto il resto funziona. **Per non dipendere da un servizio esterno:** scarica un video, mettilo in `src/frontend/public/` (per esempio `sfondo.mp4`), imposta `VIDEO_SRC = "/sfondo.mp4"` (viene riprodotto senza `hls.js`), togli `https://*.mux.com` dalla CSP e ricostruisci. `check-config.py` verifica che `VIDEO_SRC` e CSP restino coerenti.

Il testo bianco sta sopra il video senza velo scuro (scelta di progetto): la leggibilità dipende dal video. Se un fotogramma chiaro rende il titolo difficile da leggere, scegli un video più scuro.

## Modificare testi, voci, marchi

Tutto in `src/hero/src/config.js` (`COPY`, `NAV`, `BADGES`, `LOGOS`, `BRAND`). I marchi sono **segnaposto** disegnati a mano (`icons.jsx`) con il nome del servizio in testo: non ci sono loghi reali.

## Compilare e provare

```bash
docker compose up -d --build frontend     # dopo ogni modifica a src/hero o a src/frontend
```

Il frontend non è più una cartella montata: nginx serve ciò che c'è nell'immagine, quindi una modifica ai file **non si vede finché non ricostruisci**. `start.sh` ricostruisce già da solo.

Per lavorarci con Node installato:

```bash
cd src/hero && npm ci && npm run build    # produce src/hero/dist (non va nel repository)
```

La prima build scarica `node:22-alpine` e i pacchetti npm (serve rete; sul Raspberry richiede qualche minuto). Le versioni dei pacchetti sono fissate in `package-lock.json`: aggiornali con `npm install` e rifai la prova.

## Perché è fatta così (e cosa evitare)

- **Tailwind 3 con `important: '#hero-root'` e senza reset globale.** Il `style.css` del pannello è globale e non stratificato: con Tailwind 4 (che usa i *cascade layer*) le sue regole vincerebbero sull'hero, e il reset di Tailwind romperebbe il pannello. Le utility valgono solo dentro `#hero-root`.
- **Niente `<nav>` e `<main>`** nell'hero: `style.css` li stila in modo globale (barra a schede in basso, padding). Si usano `div` con `role`.
- **Niente classi che esistono già nel pannello** (è già successo con `block`, che ha `margin-bottom: 2rem`). `check-config.py` lo controlla.
- **CSS caricato con un `<link>`**, non iniettato: la CSP vieta `<style>` inline. Il percorso si calcola da `import.meta.url` in una variabile apposta, altrimenti Vite lo incorpora come `data:` URI (bloccato).
- **`hls.js` senza worker** (`enableWorker: false`): il worker nascerebbe da un blob, che `worker-src 'self'` vieta. Il costo è un po' di CPU sul thread principale, trascurabile per un solo flusso.
- **Peso:** `hero.js` ~118 KB compresso (React + motion), `hero-hls.js` ~181 KB e solo se il browser non legge HLS da solo (Safari sì).
