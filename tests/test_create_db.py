import os
import sqlite3

import create_db


SAMPLE_PACKAGES = [
    {
        'Name': 'firefox', 'Version': '1.0-1', 'Description': 'browser',
        'Install_Reason': 'Explicitly installed', 'Installed_Size': '2.34 MiB',
        'Required_By': 'None', 'Optional_For': 'None',
    },
    {
        'Name': 'yay', 'Version': '12-1', 'Description': 'aur helper',
        'Install_Reason': 'Explicitly installed', 'Installed_Size': '5.00 MiB',
        'Required_By': 'None', 'Optional_For': 'None',
    },
]
FOREIGN = {'yay'}


def _build(tmp_path):
    db = os.path.join(tmp_path, 'sub', 'packages.db')
    create_db.create_database(
        db, packages=SAMPLE_PACKAGES, foreign_packages=FOREIGN, verbose=False
    )
    return db


def test_creates_valid_db(tmp_path):
    db = _build(str(tmp_path))
    assert os.path.exists(db)
    conn = sqlite3.connect(db)
    try:
        rows = dict(conn.execute('SELECT Name, is_foreign FROM packages'))
        assert rows == {'firefox': 0, 'yay': 1}
        # Installed_Size stored as integer bytes
        size = conn.execute(
            "SELECT Installed_Size FROM packages WHERE Name='firefox'"
        ).fetchone()[0]
        assert size == int(2.34 * 1024 ** 2)
        assert isinstance(size, int)
        # integrity
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        conn.close()


def test_no_leftover_temp_file(tmp_path):
    db = _build(str(tmp_path))
    leftovers = [f for f in os.listdir(os.path.dirname(db)) if f.startswith('.pkgdb-')]
    assert leftovers == []


def test_atomic_rebuild_clears_stale_wal_sidecar(tmp_path):
    db = _build(str(tmp_path))
    # Simulate a stale WAL sidecar from an older WAL-mode build.
    open(db + '-wal', 'w').close()
    open(db + '-shm', 'w').close()
    # Rebuild; sidecars must be gone afterward.
    create_db.create_database(
        db, packages=SAMPLE_PACKAGES, foreign_packages=FOREIGN, verbose=False
    )
    assert not os.path.exists(db + '-wal')
    assert not os.path.exists(db + '-shm')


def test_corrupt_build_does_not_replace_good_db(tmp_path, monkeypatch):
    db = _build(str(tmp_path))
    good_mtime = os.path.getmtime(db)

    # Force the integrity check to fail; the good DB must remain untouched and
    # no temp file should be left behind.
    def boom(_path):
        raise RuntimeError("integrity check failed: simulated")

    monkeypatch.setattr(create_db, 'verify_database_integrity', boom)
    try:
        create_db.create_database(
            db, packages=SAMPLE_PACKAGES, foreign_packages=FOREIGN, verbose=False
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass

    assert os.path.getmtime(db) == good_mtime  # not replaced
    leftovers = [f for f in os.listdir(os.path.dirname(db)) if f.startswith('.pkgdb-')]
    assert leftovers == []
