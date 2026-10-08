# Immich

Backup e galleria foto. Quattro container: `immich_server` (web + API, porta 2283), `immich_machine_learning`
(riconoscimento volti e ricerca intelligente), `immich_redis` (coda) e `immich_postgres` (database).

## Dove stanno i dati

| Cosa | Dove |
|---|---|
| Database | `$DATA_DIR/immich/postgres` — **solo ext4**, mai exFAT/NTFS né condivisioni di rete |
| Miniature, video ricodificati, eventuali caricamenti | `$DATA_DIR/immich/upload` |
| Le tue foto già esistenti | `$PHOTOS_DIR` (default `$DATA_DIR/photos`), visibili a Immich come `/mnt/photos` in sola lettura |

`IMMICH_DB_PASSWORD`: usa solo lettere e numeri e **sceglila prima del primo avvio**. Il database viene creato con
quella password: cambiarla dopo richiede di cancellare `$DATA_DIR/immich/postgres` (e perdere l'indice).

## Primo avvio

```bash
docker compose up -d immich-server immich-machine-learning immich-redis immich-postgres
```

La prima volta scarica diversi GB. Poi apri `http://localhost:2283`, crea l'utente amministratore e:

1. Amministrazione → **Librerie esterne** → crea una libreria per il tuo utente.
2. Aggiungi come percorso di importazione `/mnt/photos`.
3. Avvia la scansione. Immich indicizza le foto **senza copiarle né modificarle**; sul disco finiscono solo
   miniature e database. Il nome esatto delle voci di menu può cambiare tra versioni.

Con una libreria esterna Immich non cancella né sposta i file originali. Le foto nuove scattate dal telefono
si caricano invece con l'app Immich e finiscono in `$DATA_DIR/immich/upload`.

## Quanto pesa

L'indicizzazione iniziale (volti, ricerca intelligente) è il momento più pesante: CPU al massimo per un po'
e parecchia RAM (Immich consiglia almeno 4 GB). Per alleggerire:
- ferma il machine learning: `docker compose stop immich-machine-learning` (la galleria funziona, ma senza
  volti e ricerca intelligente);
- su WSL limita la memoria con `.wslconfig` (`memory=6GB`).

## Aggiornamenti

Immich cambia spesso. Con `IMMICH_VERSION=release` prende l'ultima versione a ogni `pull`; per più controllo
fissa una versione (es. `v2.1.0`). Leggi sempre le note di rilascio prima di aggiornare e fai prima una copia
di `$DATA_DIR/immich/postgres`.

```bash
docker compose pull immich-server immich-machine-learning
docker compose up -d immich-server immich-machine-learning
```
