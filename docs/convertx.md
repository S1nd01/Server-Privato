# Convertitore di file (ConvertX)

Converte immagini, documenti, audio e video dal browser (FFmpeg, ImageMagick e altri strumenti dietro un'unica pagina). **Di solito resta spento**: si accende quando serve.

## Perché è così chiuso

Elabora file che non controlli con programmi che in passato hanno avuto falle: un file costruito apposta può sfruttarli. Per questo:
- rete **interna** (`convert`): niente accesso a Internet e nessun altro servizio a portata; un eventuale attacco non può mandare fuori nulla né toccare altro;
- **nessuna porta** sul computer: si apre solo da Tailscale (`https://<nome>.<rete>.ts.net:3000`);
- tetti di CPU (`CONVERTX_CPUS`, 2), RAM (`CONVERTX_MEM`, 1 GB) e processi (256); priorità bassa;
- nessuna cartella del server montata tranne la sua (`data/convertx`), utente non root, nessun privilegio;
- registrazione chiusa e login obbligatorio; i file caricati e convertiti si cancellano da soli dopo `CONVERTX_DELETE_HOURS` ore (24 di serie).

## Uso

```bash
docker compose --profile convertx up -d convertx     # la prima volta crea il container; poi basta il pannello
```

**Il primo account lo crea chiunque apra la pagina per primo** (poi la registrazione si chiude): aprila subito dopo l'avvio e registrati, da Tailscale. Dopo ogni riavvio del container devi rifare il login (la chiave delle sessioni è casuale a ogni avvio: è voluto).
Per spegnerlo: dal pannello (scheda «Convertitore di file») o `docker compose stop convertx`.

## Quando conviene e quando no

Per immagini, documenti e qualche audio va bene. Per i video sul Raspberry è lento e hai già Unmanic per la libreria. Per i PDF in particolare esistono strumenti più mirati (per esempio Stirling PDF): se ti serve solo quello, valuta quello.

## Cosa non è provato

Non l'ho potuto avviare con l'immagine reale: non so se l'app scrive in cartelle diverse da `/app/data` e `/tmp` (per questo `read_only` non è attivo). Il peso dell'immagine e il consumo a riposo vanno misurati la prima volta (`docker stats convertx`).
