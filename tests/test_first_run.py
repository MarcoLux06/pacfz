import os

import list_packages as lp


def test_ensure_cache_db_noop_when_present(monkeypatch, cache_db):
    # DB exists -> builder must not run.
    monkeypatch.setattr(lp, 'DB_PATH', cache_db)

    def fail():
        raise AssertionError("build_cache_db should not be called")

    monkeypatch.setattr(lp, 'build_cache_db', fail)
    lp.ensure_cache_db()  # must not raise


def test_ensure_cache_db_builds_when_missing(monkeypatch, tmp_path):
    missing = os.path.join(str(tmp_path), 'packages.db')
    monkeypatch.setattr(lp, 'DB_PATH', missing)

    called = {'n': 0}

    def fake_build():
        called['n'] += 1
        open(missing, 'w').close()

    monkeypatch.setattr(lp, 'build_cache_db', fake_build)
    lp.ensure_cache_db()
    assert called['n'] == 1
