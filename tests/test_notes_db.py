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
    names = notes_db.get_packages_with_notes(notes_db_path_fixture)
    assert 'lavat-git' in names

    rows = notes_db.list_notes_rows(notes_db_path_fixture)
    assert any(name == 'lavat-git' for name, _ in rows)


def test_delete_missing_db_returns_false(fresh_notes_db):
    assert notes_db.delete_note('anything', fresh_notes_db) is False
