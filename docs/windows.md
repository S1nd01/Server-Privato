# Windows: installazione automatica, SSD esterno, memoria

## Installazione automatica (`setup-windows.bat`)

1. Metti la cartella del progetto in un percorso **senza spazi**, per esempio `C:\homeserver`.
2. Doppio clic su `setup-windows.bat` e conferma la richiesta di amministratore.
3. Se Ubuntu non c'e', lo installa; segui le istruzioni a schermo (eventuale riavvio, scelta di nome utente e password di Ubuntu) e **rilancia il file**.
4. Lo script poi: installa Docker, prepara il `.env`, chiede (facoltativa) la chiave Tailscale, crea le cartelle, genera il token del pannello (**copialo quando compare**), avvia i servizi, imposta la RAM di WSL, fa partire WSL a ogni accesso a Windows e, se vuoi, disattiva la sospensione.
5. Pannello: http://localhost:8088

Si puo' rilanciare quando vuoi: aggiorna il codice, non tocca `.env` e dati.

Il server resta acceso solo se il PC e' acceso, con l'utente collegato a Windows e senza sospensione.

## Spostare tutto su un SSD esterno

Su Windows i dati dei servizi stanno nel disco virtuale di WSL (`ext4.vhdx`): per far girare il server dall'SSD si sposta quel file.

Requisiti: l'SSD (o una sua partizione) formattato **NTFS** (non exFAT) e senza compressione/cifratura sulla cartella.

1. Ferma tutto: da PowerShell `wsl --shutdown`.
2. Crea la cartella: `mkdir E:\WSL` (sostituisci `E:` con la lettera dell'SSD).
3. Sposta la distribuzione (WSL recente):
   ```powershell
   wsl --manage Ubuntu --move E:\WSL\Ubuntu
   ```
   Se il comando non esiste (WSL vecchio: `wsl --update`), usa export/import:
   ```powershell
   wsl --export Ubuntu E:\WSL\ubuntu-backup.tar
   dir E:\WSL\ubuntu-backup.tar          # controlla che pesi qualche GB
   wsl --unregister Ubuntu               # cancella la copia sul disco interno
   wsl --import Ubuntu E:\WSL\Ubuntu E:\WSL\ubuntu-backup.tar --version 2
   wsl -d Ubuntu -u root -e bash -c "printf '[user]\ndefault=NOMEUTENTE\n' >> /etc/wsl.conf"
   wsl --terminate Ubuntu
   ```
   (sostituisci `NOMEUTENTE` con il tuo utente Ubuntu).
4. Controlla: `wsl -l -v` mostra `Ubuntu` e `dir E:\WSL\Ubuntu` contiene `ext4.vhdx`. Poi `wsl -d Ubuntu -e docker ps`: i servizi devono tornare `Up`.
5. (Facoltativo) limita lo spazio massimo: `wsl --manage Ubuntu --resize 150GB`.

Prima di staccare l'SSD: **`wsl --shutdown`**, mai a servizi in funzione (rischio di corrompere il disco virtuale). Se l'SSD manca all'accesso a Windows, WSL non parte e i servizi restano fermi.

Giochi Steam, foto, film e archivio Restic possono restare su partizioni exFAT/NTFS dell'SSD: indica il percorso in `STEAM_GAMES_DIR`, `PHOTOS_DIR`, `MEDIA_DIR`, `RESTIC_REPO_DIR` (da WSL le vedi come `/mnt/e/...`).

## Quanto spazio e quanta RAM

Spazio per il disco virtuale (dati dei servizi), stime orientative:

| Voce | Spazio |
|---|---|
| Ubuntu, Docker e immagini dei servizi | 15-20 GB |
| Foto caricate su Immich | quanto pesano gli originali |
| Miniature e video convertiti di Immich | circa il 10-30% in piu' |
| Jellyfin (solo metadati; i film stanno altrove) | 1-5 GB |
| Vaultwarden, Pi-hole, pannello | meno di 1 GB |

Regola pratica: **30 GB + (foto x 1,3)**, con un margine di crescita. Per esempio con 50 GB di foto: circa 100 GB; sull'SSD conviene una partizione NTFS da 100-150 GB.
L'archivio Restic pesa circa come i dati salvati e va su un altro disco o partizione.

RAM per WSL (file `%UserProfile%\.wslconfig`, poi `wsl --shutdown`):

```
[wsl2]
memory=6GB
swap=4GB
```
- 4 GB: minimo, Immich ha parecchio da fare con il riconoscimento dei volti.
- 6-8 GB: comodo, con un PC da 16 GB.
- Lo script imposta da solo meta' della RAM del PC (tra 4 e 8 GB) se non hai gia' un `.wslconfig`.
