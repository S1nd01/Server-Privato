# Controllo remoto del desktop (RustDesk, solo client)

Per fare manutenzione da lontano su un computer con interfaccia grafica (il tuo PC fisso, quello di un familiare) basta il **client** RustDesk. **Il server RustDesk non serve e non è nel progetto.**

## Perché niente server

Il server di RustDesk (`hbbs`/`hbbr`) vuole porte raggiungibili da fuori (UDP 21116 e TCP 21115-21119): vorrebbe dire aprire porte sul router, contro il principio del progetto («nessuna porta aperta»),
e Tailscale Serve inoltra solo TCP/HTTPS, non UDP. Ma se i due dispositivi sono sullo stesso tailnet, si parlano direttamente e il server è superfluo: ci si collega all'**indirizzo Tailscale** dell'altro (quello che comincia per `100.`).

## Come

1. Installa Tailscale e RustDesk su **entrambi** i computer.
2. Sul computer da controllare, nelle impostazioni di RustDesk (rete/sicurezza) abilita l'accesso diretto via IP (la porta usata è la 21118) e imposta una **password permanente lunga**.
3. Dal tuo computer, in RustDesk scrivi come ID l'indirizzo Tailscale del primo (`100.x.y.z`) e inserisci la password.

Le voci esatte cambiano tra le versioni di RustDesk: se non le trovi, cerca nelle impostazioni «direct IP» / «accesso diretto IP».

## Attenzione

- Un accesso permanente al desktop vale quanto stare seduti davanti al computer: usa una password lunga e generata, e tieni RustDesk aggiornato.
- Con le ACL di Tailscale puoi limitare chi può raggiungere quel computer sulla porta 21118.
- **Il Raspberry è senza schermo: non serve RustDesk, si usa SSH** (anche `tailscale ssh`, se lo abiliti). Per il pannello e i servizi si usa già il browser.
- Se un dispositivo non può stare sul tailnet (per esempio il computer di un familiare), l'unica via diretta richiede il server RustDesk con le porte aperte: in quel caso valuta prima Tailscale sul loro computer (è gratuito e più sicuro).

## Cosa non è provato

Non ho aggiunto nulla al progetto (non c'è un container) e non ho provato RustDesk in questa configurazione: la procedura segue la documentazione pubblica del client.
