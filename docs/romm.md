# RomM (libreria di ROM)

RomM organizza le ROM dei giochi **che possedete**: scansiona la cartella, riconosce piattaforma e titolo, scarica copertine e
descrizioni e permette di giocare dal browser (emulatori integrati) e di salvare partite e stati. È opzionale (profilo `romm`): non
parte con `up`. Si accende dal pannello (voce "RomM (ROM)", che avvia prima il database e poi RomM) oppure con:

```bash
docker compose --profile romm up -d romm
```

## Prima attivazione

1. `./src/scripts/sync-env.sh`: crea le cartelle `data/romm/*` e genera nel `.env` `ROMM_AUTH_SECRET_KEY`, `ROMM_DB_PASSWORD` e
   `ROMM_DB_ROOT_PASSWORD`. **Non cambiate `ROMM_DB_PASSWORD` dopo il primo avvio**: MariaDB la imposta solo alla creazione del database.
2. Mettete le ROM in `data/romm/library/roms/<piattaforma>/` (per esempio `gba/`, `snes/`): i nomi delle cartelle seguono lo schema
   di RomM (https://docs.romm.app, sezione "Folder structure"). Non mischiate piattaforme nella stessa cartella.
3. Facoltativo ma consigliato: i fornitori di metadati (senza nessuno la scansione funziona, ma senza copertine e descrizioni).
   Compilate nel `.env` quelli che volete: `ROMM_IGDB_CLIENT_ID/SECRET` (account Twitch gratuito), `ROMM_SCREENSCRAPER_USER/PASSWORD`,
   `ROMM_STEAMGRIDDB_API_KEY`, `ROMM_RETROACHIEVEMENTS_API_KEY`.
4. Avviate e aprite `https://<nome>.ts.net:8085` da un dispositivo con Tailscale. Il **primo utente** che create è l'amministratore:
   fatelo subito, finché solo voi raggiungete l'indirizzo.
5. In RomM avviate una scansione della libreria.

## Reti e sicurezza

- Nessuna porta sul computer: si raggiunge solo da Tailscale (HTTPS, porta 8085).
- Due reti: `romm` (con accesso a Internet, necessario per i metadati; solo RomM e Tailscale) e `romm_db` (**interna**: il database non
  esce su Internet e non lo vede nessun altro servizio). Nessun contatto con Jellyfin, Immich o la rete dei download.
- RomM gira col vostro utente (`PUID:PGID`), con `cap_drop: ALL` e `no-new-privileges`. MariaDB parte come root e passa a `mysql`:
  per questo ha cinque capacità (`CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER`). `read_only` non è applicato.
- Limiti: `ROMM_CPUS` (2), `ROMM_MEM` (1g), `ROMM_DB_MEM` (512m) nel `.env`.
- Le password del database stanno nel `.env` (permessi 600) come per Immich.

## Cosa conviene sapere (valutazione critica)

- **Costo in RAM.** RomM più MariaDB sono circa 1,5 GB di tetto: su un Raspberry da 8 GB, con Immich e Jellyfin accesi, tenetelo spento
  quando non lo usate (il pannello lo fa in un clic).
- **Emulazione nel browser.** Dipende dal dispositivo che usate: i giochi più pesanti (PlayStation e oltre) possono essere lenti, e
  l'audio o i controller dipendono dal browser. Il carico è sul client, non sul server.
- **Contenuti.** Usate solo ROM di giochi che possedete e che avete il diritto di copiare. Non scaricatele con qBittorrent e non
  mettete la cartella ROM dentro la libreria di Jellyfin.
- **Servizi esterni.** Con i fornitori di metadati attivi, RomM invia a IGDB, ScreenScraper e agli altri i nomi dei file che scansiona.

## Backup

Nel backup Restic ci sono `data/romm/assets` (salvataggi e stati di gioco) e `data/romm/config`. **Non** ci sono le ROM
(`romm/library`: sono i vostri file, copiateli a parte), il database (`romm/db`: copiare MariaDB a caldo non dà una copia coerente) e le
copertine (`romm/resources`: si rigenerano). Perdendo il database si rifà una scansione; si perdono preferiti, raccolte e cronologia.

## Non verificato

Immagini reali, avvio di RomM con utente non root e `cap_drop ALL`, nomi delle variabili d'ambiente rispetto alla versione che scaricate,
healthcheck di MariaDB (`healthcheck.sh`) e il gioco nel browser tramite Tailscale non sono stati provati. Se RomM non parte, `docker
logs romm` e `docker logs romm-db` dicono se è un permesso, una capacità o una variabile: riferitemelo.
