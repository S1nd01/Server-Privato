# Il pannello come app sul telefono

Il pannello è una PWA: si installa e si apre a schermo intero come un'app, con la sua icona.

**Serve HTTPS**: i browser installano le app solo da indirizzi sicuri. Quindi l'indirizzo è quello di Tailscale (`https://<nome>.ts.net`, vedi `tailscale.md`), non `http://IP:8088`.

## Android (Chrome)

1. Accendi Tailscale sul telefono.
2. Apri `https://<nome>.ts.net`, inserisci il token.
3. Menu (tre puntini), *Installa app* (o *Aggiungi a schermata Home*). Oppure sezione Rete del pannello, pulsante *Installa l'app*.

## iPhone (Safari)

1. Accendi Tailscale, apri l'indirizzo in **Safari** e inserisci il token.
2. Tasto Condividi, *Aggiungi alla schermata Home*.

## Token

All'accesso spunta *Ricorda su questo dispositivo* per non reinserirlo ogni volta (è salvato solo nel telefono; usalo se il telefono ha il blocco schermo). *Esci da questo dispositivo* (sezione Rete) lo cancella.

## Offline

Senza rete si apre la schermata dell'app ma non i dati: stato e comandi arrivano sempre dal server, non vengono mai salvati nel telefono.
