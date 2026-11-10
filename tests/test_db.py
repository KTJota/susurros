from susurros.db import Store


def test_history_settings_and_dictionary(tmp_path):
    store = Store(tmp_path / "t.db")
    assert store.get("language") == "es" and store.get_bool("llm_enabled")
    store.set("sounds", False)
    assert not store.get_bool("sounds")

    store.add_transcription("Hola mundo, esto es una prueba.", duration_s=3.0, app="Code", engine="rules")
    row_id = store.add_transcription("Un 100% de descuento.", duration_s=2.0)
    assert store.list_transcriptions()[0]["text"] == "Un 100% de descuento."
    assert len(store.list_transcriptions("prueba")) == 1
    assert len(store.list_transcriptions("100%")) == 1
    assert store.list_transcriptions("_") == []

    stats = store.stats()
    assert stats["count"] == 2 and stats["words"] == 10 and stats["wpm"] == 120

    store.delete_transcription(row_id)
    assert store.stats()["count"] == 1

    assert store.add_word("  PySide  ") and not store.add_word("pyside") and not store.add_word(" ")
    assert store.words() == ["PySide"]
    store.remove_word("PySide")
    assert store.words() == []

    reopened = Store(tmp_path / "t.db")
    assert not reopened.get_bool("sounds") and reopened.stats()["count"] == 1


def test_cleanup_metrics_and_migration(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)  # database created by the first version, without the metric columns
    old.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
                " text TEXT NOT NULL, raw_text TEXT, words INTEGER NOT NULL, duration_s REAL NOT NULL,"
                " language TEXT, mode TEXT, app TEXT, engine TEXT)")
    old.execute("INSERT INTO transcriptions(created_at, text, words, duration_s) VALUES('2026-11-10T03:39:24','Hola',1,2.0)")
    old.commit(); old.close()

    store = Store(path)
    assert store.stats()["measured"] == 0 and store.stats()["fixes_per"] == 0
    store.add_transcription("Quedamos a las cinco.", duration_s=3.0, raw_words=8, fillers=1, fixes=4)
    store.add_transcription("Vale.", duration_s=1.0, raw_words=2, fillers=1, fixes=1)
    stats = store.stats()
    assert (stats["count"], stats["measured"], stats["fixes"], stats["fillers"]) == (3, 2, 5, 2)
    assert stats["fixes_per"] == 2.5 and stats["fixes_pct"] == 50.0


def test_search_ignores_case_and_accents_and_treats_wildcards_literally(tmp_path):
    store = Store(tmp_path / "t.db")
    for text in ("Árbol grande", "Un café solo", r"Está en C:\Users\yo", "ab", "termina en %"):
        store.add_transcription(text, duration_s=1.0)
    find = lambda q: [r["text"] for r in store.list_transcriptions(q)]
    assert find("arbol") == ["Árbol grande"] and find("CAFÉ") == ["Un café solo"]
    assert find(r"C:\Users") == [r"Está en C:\Users\yo"]
    assert find("\\") == [r"Está en C:\Users\yo"] and find(r"a\b") == []
    assert find("%") == ["termina en %"]


def test_time_saved_is_computed_per_dictation(tmp_path):
    store = Store(tmp_path / "t.db")
    store.add_transcription(" ".join(["palabra"] * 400), duration_s=120.0)   # saves 8 min
    store.add_transcription("cinco palabras nada más aquí", duration_s=600.0)   # saves nothing, subtracts nothing
    assert round(store.stats()["saved_min"], 1) == 8.0


def test_corrupt_database_is_set_aside_not_fatal(tmp_path):
    path = tmp_path / "susurros.db"
    path.write_bytes(b"this is not a database" * 200)
    store = Store(path)
    assert store.recovered_from is not None and store.recovered_from.exists()
    assert store.stats()["count"] == 0
    store.add_transcription("Funciona.", duration_s=1.0)
    assert Store(path).stats()["count"] == 1
