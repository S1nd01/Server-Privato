# Unbound (DNS ricorsivo dietro Pi-hole)

Di serie Pi-hole inoltra le richieste a un DNS pubblico (Google, Cloudflare...), che vede tutti i nomi che cerchi. **Unbound** le risolve da solo, interrogando i server
dei domini: Pi-hole filtra le pubblicità, Unbound risponde, e nessun DNS di terzi conosce la lista dei tuoi siti.

```
dispositivi ──▶ Pi-hole (filtra, cache) ──▶ Unbound (risolve) ──▶ server dei domini
```

Nel pannello Unbound è nello stesso gruppo di **Pi-hole** (un interruttore): senza Pi-hole non serve.

## Attivarlo

Unbound parte con il server, ma **Pi-hole continua a usare il suo upstream finché non glielo dici**: niente cambia da solo e puoi provare con calma.

```bash
docker compose up -d pihole unbound
./src/scripts/pihole-unbound.sh stato     # Unbound risponde?
./src/scripts/pihole-unbound.sh on        # Pi-hole passa a Unbound (salva l'upstream di prima)
./src/scripts/pihole-unbound.sh off       # torna indietro
```

Equivale a impostare in Pi-hole (*Settings, DNS*) l'upstream personalizzato `10.89.53.2#5335` e togliere gli altri.
Prova da un computer: `nslookup wikipedia.org <IP del server>` risponde; `doubleclick.net` resta bloccato.

## Da sapere prima

- **La prima volta è più lento.** Unbound parte con la cache vuota e per ogni nome fa più richieste (radice, `.org`, il dominio). Sulla tua rete lenta (Wi-Fi in mansarda) può
  notarsi finché non arriva il powerline: dopo qualche ora i nomi più usati sono in cache (l'opzione `prefetch` li rinnova prima che scadano) e si ritorna ai tempi di prima.
  Se dopo un giorno le pagine sono ancora lente, `./src/scripts/pihole-unbound.sh off`.
- **Se Unbound si ferma, la rete di casa non risolve i nomi** (c'è un solo upstream, di proposito: un secondo DNS pubblico farebbe uscire di nuovo le richieste).
  Un blocco breve lo copre `serve-expired` (risponde con l'ultimo valore noto per fino a 24 ore). Metti in [Uptime Kuma](uptime-kuma.md) un controllo di tipo **DNS**:
  risolutore `unbound`, porta `5335`, nome `example.com`.
- **Niente DNSSEC.** Unbound qui non convalida le firme; se vuoi la convalida, attivala in Pi-hole (*Settings, DNS, Use DNSSEC*).
- **Fuori casa con Tailscale** funziona uguale: le richieste arrivano a Pi-hole e da lì a Unbound ([setup-pihole.md](setup-pihole.md)).
- **Privacy:** i server dei domini vedono l'indirizzo pubblico di casa tuo, ma non l'elenco completo dei tuoi siti in un posto solo.
  Non è anonimato: il tuo provider vede comunque a quali indirizzi ti colleghi.

## Rete e indirizzi

Unbound sta su una rete Docker privata solo sua e di Pi-hole (`homeserver_dns`, `10.89.53.0/28`), con indirizzo fisso `10.89.53.2`: Pi-hole accetta come upstream solo un indirizzo IP.
Non pubblica nessuna porta sul computer. Se `10.89.53.0/28` coincide con una rete tua, cambia l'indirizzo in `compose.yaml` (rete `dns` e `ipv4_address`),
in `unbound/unbound.conf` (`access-control`) e in `src/scripts/pihole-unbound.sh`.

## Problemi

| Sintomo | Cosa fare |
|---|---|
| `pihole-unbound.sh on` dice che Unbound non risponde | `docker compose logs unbound` (di solito un errore nel `unbound.conf`) |
| `docker compose up` si lamenta della rete `dns` | un'altra rete usa già `10.89.53.0/28`: cambia indirizzo come sopra |
| Il pannello mostra Pi-hole «parziale» | Unbound non è stato creato: `docker compose up -d unbound` |
| Tutto lento dopo `on` | cache vuota: aspetta qualche ora; altrimenti `off` |
