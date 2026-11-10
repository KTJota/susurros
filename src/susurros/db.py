"""History, dictionary and settings in a single local SQLite database."""
from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from .config import DEFAULTS, data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    raw_text    TEXT,
    words       INTEGER NOT NULL,
    duration_s  REAL    NOT NULL,
    language    TEXT,
    mode        TEXT,
    app         TEXT,
    engine      TEXT,
    raw_words   INTEGER,   -- NULL for dictations older than the cleanup metrics
    fillers     INTEGER,
    fixes       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_transcriptions_created ON transcriptions(created_at DESC);
CREATE TABLE IF NOT EXISTS dictionary (
    word TEXT PRIMARY KEY COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

TYPING_WPM = 40  # baseline for estimating the time saved


def _fold(text: str | None) -> str:
    """Lowercase and without accents, for searching."""
    decomposed = unicodedata.normalize("NFD", (text or "").casefold())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else data_dir() / "susurros.db"
        self.recovered_from: Path | None = None   # copy of the damaged file, if we had to start from scratch
        try:
            self._open()
        except sqlite3.DatabaseError as exc:
            if isinstance(exc, sqlite3.OperationalError):
                raise   # locked or no permissions: not corruption, the file is left alone
            # Damaged file: it is set aside (not deleted) and we start with a fresh database.
            self.conn.close()
            self.recovered_from = self.path.with_name(
                f"{self.path.name}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
            self.path.replace(self.recovered_from)
            self._open()

    def _open(self) -> None:
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("fold", 1, _fold, deterministic=True)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(transcriptions)")}
        # Internal values that used to be stored in Spanish.
        for column, old, new in (("engine", "reglas", "rules"), ("engine", "directo", "live"),
                                 ("mode", "manos libres", "hands-free")):
            self.conn.execute(f"UPDATE transcriptions SET {column}=? WHERE {column}=?", (new, old))
        for old, new in (("burbuja", "bubble"), ("acorde", "chord"), ("notas", "notes"), ("toc", "knock")):
            self.conn.execute("UPDATE settings SET value=? WHERE key='sound_set' AND value=?", (new, old))
        for column in ("raw_words", "fillers", "fixes"):  # databases created before these columns
            if column not in existing:
                self.conn.execute(f"ALTER TABLE transcriptions ADD COLUMN {column} INTEGER")
        self.conn.commit()

    # -- settings --------------------------------------------------------
    def get(self, key: str) -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else DEFAULTS.get(key, "")

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def set(self, key: str, value: str | bool) -> None:
        if isinstance(value, bool):
            value = "1" if value else "0"
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    # -- history ---------------------------------------------------------
    def add_transcription(self, text: str, *, raw_text: str | None = None,
                          duration_s: float = 0.0, language: str = "", mode: str = "",
                          app: str = "", engine: str = "", raw_words: int | None = None,
                          fillers: int | None = None, fixes: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO transcriptions(created_at, text, raw_text, words, duration_s,"
            " language, mode, app, engine, raw_words, fillers, fixes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), text, raw_text,
             len(text.split()), duration_s, language, mode, app, engine, raw_words, fillers, fixes))
        self.conn.commit()
        return cur.lastrowid

    def list_transcriptions(self, query: str = "", limit: int = 300) -> list[sqlite3.Row]:
        if query.strip():
            # Case- and accent-insensitive ("cafe" finds "Café"); %, _ and \ are literal.
            needle = _fold(query.strip())
            for special in ("\\", "%", "_"):
                needle = needle.replace(special, "\\" + special)
            return self.conn.execute(
                "SELECT * FROM transcriptions WHERE fold(text) LIKE ? ESCAPE '\\' "
                "ORDER BY id DESC LIMIT ?", (f"%{needle}%", limit)).fetchall()
        return self.conn.execute(
            "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def delete_transcription(self, row_id: int) -> None:
        self.conn.execute("DELETE FROM transcriptions WHERE id=?", (row_id,))
        self.conn.commit()

    def clear_history(self) -> None:
        self.conn.execute("DELETE FROM transcriptions")
        self.conn.commit()

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(words),0) AS words,"
            " COALESCE(SUM(duration_s),0) AS seconds,"
            # Savings are computed per dictation: a slow one does not erase what the others gained.
            " COALESCE(SUM(MAX(0, words / ? - duration_s / 60.0)),0) AS saved_min"
            " FROM transcriptions", (float(TYPING_WPM),)).fetchone()
        seconds, words = row["seconds"], row["words"]
        wpm = round(words / (seconds / 60)) if seconds >= 1 else 0
        saved_min = row["saved_min"]
        # Cleanup metrics only exist for the dictations that recorded them.
        fx = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(raw_words),0) AS raw_words,"
            " COALESCE(SUM(fillers),0) AS fillers, COALESCE(SUM(fixes),0) AS fixes"
            " FROM transcriptions WHERE raw_words IS NOT NULL").fetchone()
        return {"count": row["n"], "words": words, "wpm": wpm, "saved_min": saved_min,
                "measured": fx["n"], "fillers": fx["fillers"], "fixes": fx["fixes"],
                "fixes_per": fx["fixes"] / fx["n"] if fx["n"] else 0.0,
                "fixes_pct": 100 * fx["fixes"] / fx["raw_words"] if fx["raw_words"] else 0.0}

    # -- dictionary ------------------------------------------------------
    def words(self) -> list[str]:
        return [r["word"] for r in self.conn.execute(
            "SELECT word FROM dictionary ORDER BY word COLLATE NOCASE")]

    def add_word(self, word: str) -> bool:
        word = " ".join(word.split())
        if not word:
            return False
        cur = self.conn.execute("INSERT OR IGNORE INTO dictionary(word) VALUES(?)", (word,))
        self.conn.commit()
        return cur.rowcount > 0

    def remove_word(self, word: str) -> None:
        self.conn.execute("DELETE FROM dictionary WHERE word=?", (word,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
