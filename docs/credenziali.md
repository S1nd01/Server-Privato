# Recupero di credenziali e password

Hai dimenticato una password del server? Il recupero si fa **dal terminale del server**, nella cartella del progetto, con:

```bash
./src/scripts/recupera-credenziali.sh            # elenco dei comandi
```

Nel pannello la scheda **Accessi** elenca ogni credenziale, dove sta e il comando da copiare. Il pannello **non** mostra e **non** reimposta nessuna password, per scelta:
chi ruba il token del pannello (che comanda Docker) non deve ottenere anche tutto il resto. Il recupero richiede di essere davanti al server, cioè di essere tu.

Non lanciare lo script con `sudo`: i file dei dati devono restare tuoi. Le password nuove si mostrano **una volta sola**: salvale nel password manager.

## Cosa si può fare, servizio per servizio

| Credenziale | Dove sta | Recupero |
|---|---|---|
| **Token del pannello** | solo l'hash nel `.env` | `recupera-credenziali.sh pannello`: ne genera uno nuovo, il vecchio smette di funzionare |
| **Pi-hole** | in chiaro nel `.env` | `mostra pihole` per rileggerla, `pihole` per sceglierne una nuova |
| **Immich, amministratore** | database di Immich | `immich`: password casuale nuova |
| **Immich, database** | in chiaro nel `.env` | `mostra immich-db` (non è la password con cui entri; se Immich non parte: `fix-immich-db.sh`) |
| **Vaultwarden, pagina /admin** | hash nel `.env` | `vaultwarden-admin`: genera un nuovo hash da incollare nel `.env` |
| **Vaultwarden, password master** | **non esiste sul server** | **non recuperabile** (vedi sotto) |
| **Jellyfin / Seerr** | database di Jellyfin | «Password dimenticata» nella pagina di accesso di Jellyfin (dal server o dalla rete di casa); un altro amministratore può reimpostarla da Dashboard, Utenti |
| **Radarr, Sonarr, Prowlarr** | database di ciascuno | `arr radarr` (o `sonarr`, `prowlarr`): toglie la richiesta di password e la reimposti subito dal browser |
| **qBittorrent** | hash nella sua configurazione | `qbittorrent`: password temporanea nel log |
| **ntfy** | database di ntfy | `ntfy NOME` (senza nome elenca gli utenti) |
| **Uptime Kuma** | database | `kuma` |
| **Portainer** | database | `portainer` |
| **Beszel** | database | `beszel LA_TUA_EMAIL` |
| **Bazarr** | `data/bazarr/config/config/config.yaml` | ferma Bazarr, nella sezione `auth:` metti `type: null` (e `password:` vuota), riavvia e reimposta dal browser |
| **Passphrase di Restic e dei backup di Vaultwarden** | file sul server | `mostra restic`, `mostra backup-vaultwarden`. **Se il file è perso, i backup non si aprono più** |
| **Tailscale** | nessuna sul server | si entra con il tuo account; il link di accesso del server è nella sezione Rete |

### Non recuperabile, per progetto

- **Password master di Vaultwarden.** Il vault è cifrato con la tua password sul tuo dispositivo: il server non la conosce, quindi nessuno può rigenerarla, nemmeno tu dal server.
  Cosa fare *prima* che succeda: tieni una copia della password master e dei **codici di recupero della 2FA** fuori dal server (carta, cassaforte). Se sei ancora collegato da un'app
  o da un'estensione, **esporta subito il vault** (file cifrato) prima di uscire.
- **Passphrase dei backup.** Senza, l'archivio Restic e i backup di Vaultwarden sono illeggibili. Tienile in un posto diverso dal server.

## Se non entri più nel pannello

È il caso più comune: il token si prova a rileggere e non si può, perché sul server c'è solo il suo hash. Dalla schermata di accesso, «Hai perso il token?» ripete la procedura:

```bash
cd cartella-del-progetto
./src/scripts/recupera-credenziali.sh pannello
```

Se non puoi aprire un terminale sul server (per esempio SSH non è attivo e non hai tastiera), il pannello non può aiutarti da remoto, ed è il motivo per cui non lo fa.
Da Tailscale con SSH, da una tastiera collegata, oppure da Portainer (*Containers, backend, Console*) hai comunque un accesso.

## Cosa fa e cosa non fa lo script

- Chiede conferma prima di ogni cambiamento (`HS_SI=1` la salta, per gli script).
- Per Radarr, Sonarr, Prowlarr e qBittorrent salva una copia del file di configurazione prima di modificarlo (`config.xml.bak-AAAAMMGG-HHMMSS`): contiene la chiave API, cancellala a cose fatte.
- Dopo `arr` e `qbittorrent` il servizio resta **senza password o con una temporanea** finché non ne imposti una: fallo subito, soprattutto se è raggiungibile da Tailscale.
- I comandi che usano il database di un servizio (`immich`, `kuma`, `ntfy`, `beszel`, `portainer`) sono quelli indicati dai rispettivi progetti; se una versione futura li cambia, lo script dice
  l'errore e il servizio resta com'era. Non ho potuto provarli su un server reale: la prima volta, fallo con calma e con un backup recente.
