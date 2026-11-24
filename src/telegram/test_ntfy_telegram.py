#!/usr/bin/env python3
"""Prove del ponte ntfy -> Telegram, senza rete e senza Docker: ntfy e l'API di Telegram sono due piccoli server finti.

    python3 -I src/telegram/test_ntfy_telegram.py

Il formato degli eventi segue la documentazione di ntfy (flusso /<argomento>/json: eventi `open`, `message`, `keepalive`).
"""
import contextlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "ntfy-telegram.py"
spec = importlib.util.spec_from_file_location("bridge", SCRIPT)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

BOT_TOKEN = "123456789:AAH-segretissimo_TOKEN"
NTFY_TOKEN = "tk_provaprovaprovaprovaprova1"


class FakeNtfy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), self._handler())
        self.messages: list[dict] = []   # eventi `message` in ordine
        self.drop_after: int | None = None   # chiude la connessione dopo N messaggi inviati in questa connessione
        self.requests: list[tuple[str, str]] = []
        self.stop = False
        self.drop_when_done = False   # chiude la connessione quando ha gia' consegnato (o saltato) tutti i messaggi
        self.junk_first = False
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def add(self, text, title=None, priority=3, **extra):
        n = len(self.messages) + 1
        ev = {"id": f"id{n:04d}", "time": int(time.time()) + n, "event": "message", "topic": "homeserver", "message": text, "priority": priority}
        if title:
            ev["title"] = title
        ev.update(extra)
        self.messages.append(ev)
        return ev

    def _handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                srv.requests.append((self.path, self.headers.get("Authorization", "")))
                if self.headers.get("Authorization") != f"Bearer {NTFY_TOKEN}":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"code":40101,"http":401,"error":"unauthorized"}')
                    return
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                since = dict(p.split("=", 1) for p in q.split("&") if "=" in p).get("since", "")
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                w = self.wfile
                w.write(b'{"id":"o1","time":1,"event":"open","topic":"homeserver"}\n')
                if srv.junk_first:
                    w.write(b"questo non e' json\n")
                    w.write(b'{"id":"k0","event":"keepalive","topic":"homeserver"}\n')
                    w.write(b'{"id":"d0","event":"message_delete","topic":"homeserver"}\n')
                sent_ids = set()
                sent = 0
                try:
                    while not srv.stop:
                        for ev in list(srv.messages):
                            if ev["id"] in sent_ids:
                                continue
                            # since: id di un messaggio gia' visto, oppure un timestamp unix
                            if since.startswith("id"):
                                if ev["id"] <= since:
                                    sent_ids.add(ev["id"])
                                    continue
                            elif since.isdigit() and ev["time"] < int(since):
                                sent_ids.add(ev["id"])
                                continue
                            w.write(json.dumps(ev).encode() + b"\n")
                            w.flush()
                            sent_ids.add(ev["id"])
                            sent += 1
                            if srv.drop_after is not None and sent >= srv.drop_after:
                                return
                        if srv.drop_when_done and all(e["id"] in sent_ids for e in srv.messages):
                            return
                        time.sleep(0.03)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        return H


class FakeTelegram(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), self._handler())
        self.calls: list[dict] = []
        self.script: list[tuple[int, dict]] = []   # risposte da dare, nell'ordine; poi 200
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def texts(self):
        return [c["body"]["text"] for c in self.calls if c["status"] == 200]

    def _handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                code, payload = srv.script.pop(0) if srv.script else (200, {"ok": True, "result": {}})
                srv.calls.append({"path": self.path, "body": body, "status": code, "ctype": self.headers.get("Content-Type")})
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return H


class Base(unittest.TestCase):
    def setUp(self):
        self.ntfy, self.tg_srv = FakeNtfy(), FakeTelegram()
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(self.state)
        bridge.NTFY_URL, bridge.TELEGRAM_API, bridge.STATE_DIR = self.ntfy.url, self.tg_srv.url, self.state
        self.sleeps: list[float] = []
        self.tg = bridge.Telegram(BOT_TOKEN, "42", sleep=self.sleeps.append)
        self.lim = bridge.Limiter(100, 0, sleep=lambda s: None)

    def tearDown(self):
        self.ntfy.stop = True
        self.ntfy.shutdown()
        self.tg_srv.shutdown()
        self.tmp.cleanup()

    def run_bridge(self, token=NTFY_TOKEN):
        """Una connessione a ntfy; ntfy la chiude dopo l'ultimo messaggio. Ritorna il testo scritto nei log."""
        self.ntfy.drop_when_done = True
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bridge.run_once("homeserver", token, self.tg, self.lim)
        return buf.getvalue()

    def cursor(self):
        return bridge.load_cursor()


class Inoltro(Base):
    def test_testo_semplice_verso_il_chat_giusto(self):
        self.ntfy.add("Importato: Film", title="Radarr", priority=3)
        self.ntfy.add("Disco quasi pieno", title="Server", priority=5)
        self.ntfy.add("senza titolo")
        self.ntfy.messages[0]["time"] = self.ntfy.messages[1]["time"] = self.ntfy.messages[2]["time"] = int(time.time()) + 5
        self.run_bridge()
        calls = self.tg_srv.calls
        self.assertEqual(len(calls), 3)
        for c in calls:
            self.assertEqual(c["path"], f"/bot{BOT_TOKEN}/sendMessage")
            self.assertEqual(c["body"]["chat_id"], "42")
            self.assertNotIn("parse_mode", c["body"])
            self.assertEqual(c["body"]["disable_web_page_preview"], True)
        self.assertEqual(self.tg_srv.texts(), ["Radarr\nImportato: Film", "🚨 Server\nDisco quasi pieno", "senza titolo"])

    def test_il_token_ntfy_viaggia_nell_header(self):
        self.ntfy.add("x")
        self.run_bridge()
        self.assertEqual(self.ntfy.requests[0][1], f"Bearer {NTFY_TOKEN}")
        self.assertNotIn(NTFY_TOKEN, self.ntfy.requests[0][0])   # mai nell'indirizzo

    def test_token_ntfy_sbagliato(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.run_bridge(token="tk_sbagliato")
        self.assertEqual(cm.exception.code, 401)
        self.assertEqual(self.tg_srv.calls, [])

    def test_eventi_non_message_e_righe_rotte_ignorati(self):
        self.ntfy.junk_first = True
        self.ntfy.add("vero")
        out = self.run_bridge()
        self.assertEqual(self.tg_srv.texts(), ["vero"])
        self.assertIn("riga non valida", out)

    def test_battito(self):
        self.ntfy.add("x")
        self.run_bridge()
        self.assertLess(time.time() - os.path.getmtime(os.path.join(self.state, "alive")), 10)

    def test_testo_lungo_e_vuoto(self):
        self.assertLessEqual(len(bridge.format_message({"message": "a" * 10000})), 3900)
        self.assertEqual(bridge.format_message({"message": ""}), "(notifica senza testo)")
        self.assertEqual(bridge.format_message({"title": "T", "message": "m", "click": "https://x.y/z"}), "T\nm\nhttps://x.y/z")

    def test_il_testo_non_e_interpretato(self):
        # niente parse_mode: asterischi, underscore e HTML restano testo
        t = bridge.format_message({"message": "*grassetto* _x_ <b>h</b> [l](http://a)"})
        self.assertEqual(t, "*grassetto* _x_ <b>h</b> [l](http://a)")


class Cursore(Base):
    def test_riprende_dall_ultimo_messaggio(self):
        for t in ("uno", "due"):
            self.ntfy.add(t)
        self.run_bridge()
        self.assertEqual(self.cursor(), "id0002")
        self.ntfy.add("tre")
        self.run_bridge()
        self.assertEqual(self.tg_srv.texts(), ["uno", "due", "tre"])   # nessun doppione dopo il "riavvio"

    def test_primo_avvio_salta_i_vecchi(self):
        old = self.ntfy.add("vecchio")
        old["time"] = int(time.time()) - 3600
        new = self.ntfy.add("nuovo")
        new["time"] = int(time.time()) + 2
        self.run_bridge()
        self.assertEqual(self.tg_srv.texts(), ["nuovo"])


class Errori(Base):
    def test_429_aspetta_retry_after_poi_consegna(self):
        self.tg_srv.script = [(429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}})]
        self.ntfy.add("a")
        self.run_bridge()
        self.assertEqual(self.tg_srv.texts(), ["a"])
        self.assertEqual(len(self.tg_srv.calls), 2)
        self.assertEqual(self.sleeps, [8.0])
        self.assertEqual(self.cursor(), "id0001")

    def test_rifiuto_definitivo_scarta_e_prosegue(self):
        self.tg_srv.script = [(400, {"ok": False, "description": f"Bad Request: chat not found {BOT_TOKEN}"})]
        self.ntfy.add("perso")
        self.ntfy.add("ok")
        out = self.run_bridge()
        self.assertEqual(self.tg_srv.texts(), ["ok"])
        self.assertEqual(self.cursor(), "id0002")
        self.assertIn("chat not found", out)
        self.assertNotIn(BOT_TOKEN, out)   # nemmeno se e' Telegram a ripeterlo

    def test_telegram_giu_non_perde_il_messaggio(self):
        self.tg_srv.script = [(502, {"ok": False})] * bridge.SEND_ATTEMPTS
        self.ntfy.add("importante")
        with contextlib.redirect_stdout(io.StringIO()):
            self.ntfy.drop_when_done = True
            with self.assertRaises(RuntimeError):
                bridge.run_once("homeserver", NTFY_TOKEN, self.tg, self.lim)
        self.assertEqual(self.cursor(), "")   # il cursore non e' avanzato
        self.run_bridge()                     # al giro dopo (Telegram di nuovo su) arriva
        self.assertEqual(self.tg_srv.texts(), ["importante"])

    def test_telegram_irraggiungibile_non_stampa_il_token(self):
        bridge.TELEGRAM_API = "http://127.0.0.1:9"   # porta chiusa
        self.ntfy.add("x")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.ntfy.drop_when_done = True
            with self.assertRaises(RuntimeError) as cm:
                bridge.run_once("homeserver", NTFY_TOKEN, self.tg, self.lim)
        self.assertNotIn(BOT_TOKEN, buf.getvalue() + str(cm.exception))


class Limite(unittest.TestCase):
    def test_riassunto_dopo_la_raffica(self):
        now = [0.0]
        sent: list[str] = []

        class T:
            def send(self, text):
                sent.append(text)

        lim = bridge.Limiter(3, 0, clock=lambda: now[0], sleep=lambda s: None)
        for i in range(6):
            bridge.forward({"message": f"m{i}"}, T(), lim)
        self.assertEqual(sent, ["m0", "m1", "m2"])
        self.assertEqual(lim.suppressed, 3)
        now[0] = 61
        bridge.forward({"message": "dopo"}, T(), lim)
        self.assertEqual(len(sent), 5)
        self.assertIn("3 notifiche non inoltrate", sent[3])
        self.assertEqual(sent[4], "dopo")
        self.assertEqual(lim.suppressed, 0)

    def test_distanza_minima(self):
        waits: list[float] = []
        now = [0.0]
        lim = bridge.Limiter(100, 1.0, clock=lambda: now[0], sleep=waits.append)
        lim.mark_sent()
        now[0] = 0.25
        lim.wait_gap()
        self.assertEqual(waits, [0.75])


class Processo(unittest.TestCase):
    """Lo script vero, come lo avvia Docker: variabili d'ambiente, segreti in file, SIGTERM."""

    def setUp(self):
        self.ntfy, self.tg_srv = FakeNtfy(), FakeTelegram()
        self.tmp = tempfile.TemporaryDirectory()
        self.secrets = os.path.join(self.tmp.name, "secrets")
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(self.secrets)
        Path(self.secrets, "telegram_bot_token").write_text(BOT_TOKEN + "\n")
        Path(self.secrets, "ntfy_token").write_text(NTFY_TOKEN + "\n")

    def tearDown(self):
        self.ntfy.stop = True
        self.ntfy.shutdown()
        self.tg_srv.shutdown()
        self.tmp.cleanup()

    def start(self, **over):
        env = {"PATH": os.environ["PATH"], "NTFY_URL": self.ntfy.url, "TELEGRAM_API": self.tg_srv.url, "TELEGRAM_CHAT_ID": "-100123",
               "NTFY_TOPIC": "homeserver", "SECRETS_DIR": self.secrets, "STATE_DIR": self.state, "MIN_GAP": "0", "PYTHONUNBUFFERED": "1"}
        env.update(over)
        return subprocess.Popen([sys.executable, "-I", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def wait_for(self, cond, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def test_si_riconnette_e_si_ferma_con_sigterm(self):
        p = self.start()
        try:
            time.sleep(1.2)   # connessione aperta: i messaggi con timestamp da "adesso" in poi
            self.ntfy.drop_after = 1
            self.ntfy.add("primo")
            self.assertTrue(self.wait_for(lambda: len(self.tg_srv.texts()) == 1), "primo messaggio non inoltrato")
            # ntfy ha chiuso la connessione: il ponte deve riconnettersi (attesa 4s) e riprendere dal cursore
            self.ntfy.drop_after = None
            self.ntfy.add("secondo")
            self.assertTrue(self.wait_for(lambda: len(self.tg_srv.texts()) == 2, 20), "non si e' riconnesso")
            self.assertEqual(self.tg_srv.texts(), ["primo", "secondo"])
            self.assertEqual(self.tg_srv.calls[0]["body"]["chat_id"], "-100123")
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=10), 0)
            out = p.stdout.read()
            self.assertNotIn(BOT_TOKEN, out)
            self.assertNotIn(NTFY_TOKEN, out)
        finally:
            if p.poll() is None:
                p.kill()

    def test_configurazione_incompleta(self):
        for over, frag in (({"TELEGRAM_CHAT_ID": ""}, "TELEGRAM_CHAT_ID"), ({"TELEGRAM_CHAT_ID": "abc"}, "TELEGRAM_CHAT_ID"),
                           ({"SECRETS_DIR": self.tmp.name}, "telegram_bot_token")):
            p = self.start(**over)
            out, _ = p.communicate(timeout=10)
            self.assertNotEqual(p.returncode, 0, over)
            self.assertIn(frag, out)
        Path(self.secrets, "ntfy_token").write_text("\n")
        p = self.start()
        out, _ = p.communicate(timeout=10)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("vuoto", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
