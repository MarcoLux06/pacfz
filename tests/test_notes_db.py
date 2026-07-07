import notes_db


def test_set_get_delete_roundtrip(fresh_notes_db):
    assert notes_db.get_note('pkg', fresh_notes_db) is None

    notes_db.set_note('pkg', 'hello', fresh_notes_db)
    assert notes_db.get_note('pkg', fresh_notes_db) == 'hello'

    # upsert
    notes_db.set_note('pkg', 'updated', fresh_notes_db)
    assert notes_db.get_note('pkg', fresh_notes_db) == 'updated'

    assert notes_db.delete_note('pkg', fresh_notes_db) is True
    assert notes_db.get_note('pkg', fresh_notes_db) is None
    # deleting again is a no-op, not an error
    assert notes_db.delete_note('pkg', fresh_notes_db) is False


def test_get_missing_db_returns_none(fresh_notes_db):
    # path doesn't exist yet, get must not create it
    assert notes_db.get_note('x', fresh_notes_db) is None
    import os
    assert not os.path.exists(fresh_notes_db)


def test_packages_with_notes_and_listing(notes_db_path_fixture):
    import sqlite3
    conn = sqlite3.connect(notes_db_path_fixture)
    try:
        expected_names = {row[0] for row in conn.execute('SELECT name FROM user_data')}
    finally:
        conn.close()
    assert expected_names, "fixture notes.db should have at least one note for this test to mean anything"

    names = notes_db.get_packages_with_notes(notes_db_path_fixture)
    assert names == expected_names

    rows = notes_db.list_notes_rows(notes_db_path_fixture)
    assert {name for name, _ in rows} == expected_names


def test_delete_missing_db_returns_false(fresh_notes_db):
    assert notes_db.delete_note('anything', fresh_notes_db) is False
