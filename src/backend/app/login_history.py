"""Conteggio degli accessi espliciti al pannello, aggregato per giorno UTC."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

FILE = Path("/data/panel/login-history.sqlite3")
DAYS = 7


def daily_counts(*, record: bool = False) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=DAYS - 1)
    with closing(sqlite3.connect(FILE)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS logins (day TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        if record:
            db.execute(
                "INSERT INTO logins VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET count = count + 1",
                (today.isoformat(),),
            )
            db.execute("DELETE FROM logins WHERE day < ?", (first.isoformat(),))
        counts = dict(db.execute("SELECT day, count FROM logins WHERE day >= ?", (first.isoformat(),)))
    return [
        {"day": day, "count": counts.get(day, 0)}
        for day in ((first + timedelta(days=i)).isoformat() for i in range(DAYS))
    ]
