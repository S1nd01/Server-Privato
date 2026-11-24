#!/usr/bin/env python3
"""Ponte ntfy -> Telegram (docs/telegram.md).

Si iscrive agli argomenti ntfy del server (flusso JSON, http://ntfy:80) e inoltra ogni messaggio al TUO chat Telegram.
Solo in uscita: non ascolta nessuna porta e non legge i messaggi che arrivano al bot, quindi dal bot non si puo' comandare nulla.
Solo libreria standard di Python: nessun pacchetto da installare.

Configurazione (variabili d'ambiente, impostate da compose.yaml):
  TELEGRAM_CHAT_ID      chat a cui scrivere (lo ricava src/scripts/telegram-setup.sh)
  NTFY_TOPIC            argomento, o piu' argomenti separati da virgola (di serie: homeserver)
  NTFY_URL              indirizzo di ntfy (di serie: http://ntfy:80)
  TELEGRAM_API          indirizzo dell'API Telegram (di serie: https://api.telegram.org; cambia solo nelle prove)
  MAX_PER_MIN           massimo di messaggi a Telegram al minuto; il resto viene riassunto in un solo messaggio (di serie: 15)
  SECRETS_DIR           cartella dei segreti, in sola lettura (di serie: /run/secrets)
                          telegram_bot_token   token del bot (BotFather)
                          ntfy_token           token ntfy con permesso di SOLA LETTURA sugli argomenti
  STATE_DIR             cartella scrivibile (di serie: /state): `cursor` (ultimo messaggio inoltrato) e `alive` (battito per il healthcheck)

Il token del bot sta nell'indirizzo delle chiamate a Telegram: non viene mai scritto nei log.
"""
import collections
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NTFY_URL = os.environ.get("NTFY_URL", "http://ntfy:80").rstrip("/")
TELEGRAM_API = os.environ.get("TELEGRAM_API", "https://api.telegram.org").rstrip("/")
SECRETS_DIR = os.environ.get("SECRETS_DIR", "/run/secrets")
STATE_DIR = os.environ.get("STATE_DIR", "/state")
MAX_PER_MIN = int(os.environ.get("MAX_PER_MIN", "15"))
MIN_GAP = float(os.environ.get("MIN_GAP", "1.1"))   # Telegram: circa un messaggio al secondo verso la stessa chat
READ_TIMEOUT = float(os.environ.get("READ_TIMEOUT", "100"))   # ntfy manda un battito ogni 45 secondi
MAX_TEXT = 3900   # il limite di Telegram e' 4096 caratteri
SEND_ATTEMPTS = 6

PRIORITY_MARK = {5: "🚨 ", 4: "⚠️ "}


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def read_secret(name: str, required: bool = True) -> str:
    try:
        with open(os.path.join(SECRETS_DIR, name), encoding="utf-8") as f:
            value = f.read().strip()
    except OSError as e:
        if required:
            sys.exit(f"ERRORE: non riesco a leggere il segreto '{name}' in {SECRETS_DIR}: {e.strerror}")
        return ""
    if required and not value:
        sys.exit(f"ERRORE: il segreto '{name}' e' vuoto")
    return value


def format_message(ev: dict) -> str:
    """Testo semplice (niente parse_mode: nessun carattere speciale da proteggere, nessuna injection di formattazione)."""
    title = str(ev.get("title") or "").strip()
    body = str(ev.get("message") or "").strip()
    mark = PRIORITY_MARK.get(ev.get("priority"), "")
    parts = []
    if title:
        parts.append(f"{mark}{title}")
        if body:
            parts.append(body)
    else:
        parts.append(f"{mark}{body}" if body else f"{mark}(notifica senza testo)")
    click = str(ev.get("click") or "").strip()
    if click:
        parts.append(click)
    text = "\n".join(parts)
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1] + "…"
    return text


class Limiter:
    """Al massimo `limit` invii negli ultimi 60 secondi, distanziati di `gap`. Il resto si conta e si riassume."""

    def __init__(self, limit: int, gap: float, clock=time.monotonic, sleep=time.sleep):
        self.limit, self.gap, self.clock, self.sleep = limit, gap, clock, sleep
        self.sent: collections.deque = collections.deque()
        self.suppressed = 0
        self.last = -1e9

    def _trim(self, now: float) -> None:
        while self.sent and now - self.sent[0] >= 60:
            self.sent.popleft()

    def allow(self) -> bool:
        now = self.clock()
        self._trim(now)
        return len(self.sent) < self.limit

    def wait_gap(self) -> None:
        delta = self.gap - (self.clock() - self.last)
        if delta > 0:
            self.sleep(delta)

    def mark_sent(self) -> None:
        self.last = self.clock()
        self.sent.append(self.last)


class Telegram:
    def __init__(self, token: str, chat_id: str, sleep=time.sleep):
        self.token, self.chat_id, self.sleep = token, chat_id, sleep

    def _scrub(self, s: str) -> str:
        return s.replace(self.token, "<token>")

    def send(self, text: str) -> bool:
        """True = consegnato; False = scartato per un errore definitivo (es. chat inesistente).
        Con errori temporanei (rete, 429, 5xx) riprova con attesa crescente; se non ce la fa solleva RuntimeError
        e il messaggio resta da inoltrare (il cursore non avanza)."""
        url = f"{TELEGRAM_API}/bot{self.token}/sendMessage"
        data = json.dumps({"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        delay = 2.0
        for attempt in range(1, SEND_ATTEMPTS + 1):
            wait = delay
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    r.read()
                return True
            except urllib.error.HTTPError as e:
                try:
                    info = json.loads(e.read().decode("utf-8", "replace"))
                except ValueError:
                    info = {}
                desc = self._scrub(str(info.get("description", "")))
                if e.code == 429:
                    wait = float((info.get("parameters") or {}).get("retry_after", delay)) + 1
                    log(f"Telegram: troppe richieste, riprovo tra {wait:.0f}s")
                elif e.code >= 500:
                    log(f"Telegram: errore {e.code}, riprovo")
                else:
                    log(f"Telegram ha rifiutato il messaggio (HTTP {e.code}: {desc}). Scartato.")
                    if e.code in (401, 403, 404):
                        log("  Controlla il token del bot e TELEGRAM_CHAT_ID (e che tu abbia scritto /start al bot).")
                    return False
            except (urllib.error.URLError, OSError) as e:
                log(f"Telegram non raggiungibile ({self._scrub(type(e).__name__)}), riprovo")
            if attempt < SEND_ATTEMPTS:
                self.sleep(min(wait, 300))
                delay = min(delay * 2, 60)
        raise RuntimeError("Telegram non risponde: il messaggio verra' ritentato")


def load_cursor() -> str:
    try:
        with open(os.path.join(STATE_DIR, "cursor"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_cursor(value: str) -> None:
    path = os.path.join(STATE_DIR, "cursor")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(value)
    os.replace(tmp, path)


def beat() -> None:
    try:
        with open(os.path.join(STATE_DIR, "alive"), "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def stream(topics: str, ntfy_token: str, since: str):
    """Genera gli eventi JSON di ntfy; chiude al primo errore (il chiamante riconnette)."""
    url = f"{NTFY_URL}/{urllib.parse.quote(topics, safe=',')}/json?since={urllib.parse.quote(since)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {ntfy_token}"})
    with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as r:
        for raw in r:
            beat()
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except ValueError:
                log("riga non valida da ntfy, ignorata")


def forward(ev: dict, tg: Telegram, lim: Limiter) -> None:
    """Inoltra un messaggio. Solleva RuntimeError se Telegram non e' raggiungibile (il cursore resta indietro)."""
    if not lim.allow():
        lim.suppressed += 1
        return
    if lim.suppressed:
        # in coda al giro: prima il riassunto di quanto e' stato trattenuto, poi il messaggio corrente
        lim.wait_gap()
        tg.send(f"{lim.suppressed} notifiche non inoltrate (troppe in un minuto). Le trovi nell'app ntfy.")
        lim.mark_sent()
        lim.suppressed = 0
        if not lim.allow():
            lim.suppressed += 1
            return
    lim.wait_gap()
    tg.send(format_message(ev))
    lim.mark_sent()


def run_once(topics: str, ntfy_token: str, tg: Telegram, lim: Limiter) -> None:
    cursor = load_cursor()
    since = cursor or str(int(time.time()))   # al primo avvio: solo i messaggi da adesso in poi
    log(f"Connesso a ntfy (argomenti: {topics}, da: {since})")
    for ev in stream(topics, ntfy_token, since):
        if ev.get("event") != "message":
            continue
        forward(ev, tg, lim)
        if ev.get("id"):
            save_cursor(str(ev["id"]))


def main() -> None:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    topics = os.environ.get("NTFY_TOPIC", "homeserver").strip() or "homeserver"
    if not chat_id.lstrip("-").isdigit():
        sys.exit("ERRORE: TELEGRAM_CHAT_ID mancante o non numerico: lancia ./src/scripts/telegram-setup.sh")
    bot_token = read_secret("telegram_bot_token")
    ntfy_token = read_secret("ntfy_token")
    os.makedirs(STATE_DIR, exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    tg = Telegram(bot_token, chat_id)
    lim = Limiter(MAX_PER_MIN, MIN_GAP)
    backoff = 2.0
    beat()
    while True:
        started = time.monotonic()
        try:
            run_once(topics, ntfy_token, tg, lim)
            log("ntfy ha chiuso la connessione")
        except urllib.error.HTTPError as e:
            log(f"ntfy ha risposto HTTP {e.code}" + (" (token ntfy rifiutato o senza permesso di lettura)" if e.code in (401, 403) else ""))
        except RuntimeError as e:
            log(str(e))
        except (urllib.error.URLError, OSError) as e:
            log(f"ntfy non raggiungibile: {type(e).__name__}")
        # attesa crescente, ma riparte da capo se la connessione e' durata a lungo
        backoff = 2.0 if time.monotonic() - started > 60 else min(backoff * 2, 60)
        beat()
        time.sleep(backoff)


if __name__ == "__main__":
    main()
