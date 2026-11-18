import sqlite3

from pipeline import f1db


def make_db(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE "season" ("year" INTEGER NOT NULL)')
    con.execute('CREATE TABLE "race" ("id" INTEGER, "year" INTEGER, "sprint" BOOLEAN, "distance" DECIMAL(6,3), "date" DATE)')
    con.executemany('INSERT INTO "season" VALUES (?)', [(y,) for y in range(1950, 2027)])
    con.executemany('INSERT INTO "race" VALUES (?,?,?,?,?)', [(i, 2026, i % 2, 305.879, "2026-11-08") for i in range(2500)])
    con.commit()
    con.close()


def test_load_chunks_types_and_counts(tmp_path, monkeypatch):
    p = str(tmp_path / "f.db")
    make_db(p)
    monkeypatch.setattr(f1db, "CHUNK", 1000)
    calls = []
    def call(t, rows, wipe):
        calls.append((t, len(rows), wipe, rows[0] if rows else None))
        return len(rows)
    counts = f1db.load(p, call)
    assert counts == {"race": 2500, "season": 77}
    race = [c for c in calls if c[0] == "race"]
    assert [(n, w) for _, n, w, _ in race] == [(1000, True), (1000, False), (500, False)]  # wipe only on the first chunk
    first = race[0][3]
    assert first["sprint"] is False and race[1][3]["sprint"] is False and isinstance(first["distance"], float)


def test_count_mismatch_fails(tmp_path):
    p = str(tmp_path / "f.db")
    make_db(p)
    try:
        f1db.load(p, lambda t, rows, wipe: max(0, len(rows) - 1))
    except RuntimeError as e:
        assert "F1DB has" in str(e)
    else:
        raise AssertionError("a short write must fail the load")


def test_send_splits_on_timeout():
    from pipeline import f1db
    calls = []

    def call(t, rows, wipe):
        calls.append((len(rows), wipe))
        if len(rows) > 100:
            raise RuntimeError("{'message': 'canceling statement due to statement timeout', 'code': '57014'}")
        return len(rows)

    assert f1db._send(call, "race_data", list(range(400)), True) == 400
    assert [w for n, w in calls if n <= 100] == [True, False, False, False]  # wipe only once, on the first piece


def test_send_other_errors_raise():
    import pytest
    from pipeline import f1db
    with pytest.raises(RuntimeError):
        f1db._send(lambda t, r, w: (_ for _ in ()).throw(RuntimeError("boom")), "x", [1, 2], True)
