# Syncthing

Sincronizza cartelle tra i tuoi dispositivi (PC, telefono, server), cifrato e **senza server centrale**: ogni dispositivo parla direttamente con gli altri.
Qui è configurato per non usare nulla di pubblico: niente server di scoperta globale, niente relay, niente UPnP, niente scoperta in LAN, niente statistiche.
I dispositivi si raggiungono **solo dal tailnet**: la porta di sincronizzazione (22000) non è pubblicata sul computer, la inoltra Tailscale come TCP puro (`tailscale/serve.json`).

## Primo avvio

```bash
docker compose up -d syncthing
./src/scripts/syncthing-setup.sh     # utente e password, opzioni di rete; mostra l'ID del dispositivo
```

Fallo subito: finché non imposti utente e password, l'interfaccia (`https://<nome>.<rete>.ts.net:8384`) è aperta a chiunque sia sul tuo tailnet.
`./src/scripts/syncthing-setup.sh --stato` mostra le impostazioni attuali senza cambiarle.

## Collegare un dispositivo

1. Installa Syncthing sul dispositivo (e Tailscale: senza, non raggiunge il server).
2. Sul dispositivo, «Aggiungi dispositivo» con l'ID del server; sul server accetta la richiesta (interfaccia web, di solito compare un avviso).
3. Nelle impostazioni del dispositivo remoto (sul server **e** sul dispositivo) metti come indirizzo `tcp://<nome>.<rete>.ts.net:22000` al posto di `dynamic`, e togli la spunta ai relay.
4. Le cartelle del server si creano sotto **`/sync`** (per esempio `/sync/documenti` = `data/sync/documenti` sul computer): qualsiasi altro percorso sta nel container e va perso.

Il protocollo è solo TCP (Tailscale Serve non inoltra UDP, quindi niente QUIC): per sincronizzare va benissimo.

## Cose da sapere

- **Syncthing non è un backup**: una cancellazione o un file rovinato si propaga a tutti. Su ogni cartella importante attiva il «versionamento dei file» (per esempio «scaglionato»).
- Nel backup Restic finisce solo `data/syncthing` (identità del dispositivo e cartelle configurate), non i file sincronizzati: quelli sono già sugli altri dispositivi.
- Se cambi nome al server Tailscale, l'indirizzo `tcp://…` cambia: va aggiornato sugli altri dispositivi.
- Alternativa più semplice per un file singolo: Taildrop di Tailscale, o lo scambio file (Copyparty).

## Cosa non è provato

Non l'ho potuto avviare con l'immagine reale. Lo script usa l'API di Syncthing (`/rest/config/gui` e `/rest/config/options`, metodo PATCH) con `curl` dentro il container e controlla alla fine che l'interfaccia rifiuti le richieste senza credenziali; se un passaggio fallisce si ferma e dice quale (le stesse impostazioni si fanno a mano da «Azioni → Impostazioni»).
Se `docker logs syncthing` lamenta una scrittura su un percorso, togli `read_only: true` dal compose e dimmelo.
