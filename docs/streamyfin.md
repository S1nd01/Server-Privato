# Streamyfin (app per Jellyfin)

Streamyfin è un'**app per telefono e tablet** (iOS e Android) che si collega a Jellyfin. Non è un servizio del server: non c'è nessun
container da aggiungere, quindi nessuna RAM in più e nessuna superficie d'attacco in più.

## Come collegarla

1. Installate l'app dal vostro store. Su Android la distribuzione può passare anche da GitHub: scaricate solo dal progetto ufficiale.
2. Il telefono deve avere **Tailscale attivo** (il server non ha porte aperte).
3. In Streamyfin, indirizzo del server: `https://<nome>.ts.net:8096` (è la porta di Jellyfin pubblicata da Tailscale Serve).
4. Accedete con il vostro utente Jellyfin. Se usate Seerr, potete collegarlo dalle impostazioni dell'app (`https://<nome>.ts.net:5055`).

## Limiti

- **Funziona solo con Jellyfin.** Se passate a Plex serve l'app Plex.
- La qualità in streaming dipende dalla trascodifica di Jellyfin. Su un Raspberry preferite file compatibili con il dispositivo
  (*direct play*), altrimenti la trascodifica software satura la CPU.
- Esiste un plugin di Streamyfin per Jellyfin (impostazioni centralizzate): è facoltativo e **non è incluso**; installare un plugin
  significa eseguire codice di terzi dentro Jellyfin, quindi valutatelo a parte.
- L'app è un progetto di terze parti, non fa parte di Jellyfin: aggiornatela dallo store e leggete le note di versione.
