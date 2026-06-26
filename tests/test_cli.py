import os
import sqlite3
import subprocess
import sys

import pytest


def run_list(project_root, *args):
    """Run list_packages.py as a subprocess; return stdout lines."""
    script = os.path.join(str(project_root), 'list_packages.py')
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    return [ln for ln in result.stdout.splitlines() if ln]


def run_preview(project_root, pkg, *args):
    script = os.path.join(str(project_root), 'preview_item.py')
    result = subprocess.run(
        [sys.executable, script, *args],
        input=pkg + '\n', capture_output=True, text=True, env=os.environ.copy(),
    )
    return result


def _db_scalar(cache_db, sql):
    conn = sqlite3.connect(cache_db)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def test_no_args_lists_all_sorted(project_root, cache_db):
    names = run_list(project_root)
    expected = _db_scalar(cache_db, 'SELECT COUNT(*) FROM packages')
    assert len(names) == expected
    assert names == sorted(names)  # default ASC by Name


def test_foreign_filter(project_root, cache_db):
    names = run_list(project_root, '-m')
    expected = _db_scalar(cache_db, 'SELECT COUNT(*) FROM packages WHERE is_foreign = 1')
    assert len(names) == expected


def test_orphan_count_matches_direct_sql(project_root, cache_db):
    # H2: '= None' must return exactly what the semantic query does.
    names = run_list(project_root, '-o')
    expected = _db_scalar(
        cache_db,
        "SELECT COUNT(*) FROM packages WHERE "
        "Install_Reason = 'Installed as a dependency for another package' "
        "AND Required_By = 'None'",
    )
    assert len(names) == expected


def test_explicit_field_search(project_root):
    names = run_list(project_root, '-f', 'Name', 'python')
    assert names, "expected at least one python* package"
    assert all('python' in n.lower() for n in names)


def test_sort_by_size_desc_default(project_root, cache_db):
    names = run_list(project_root, '-s')
    # First name should be the largest package by Installed_Size.
    conn = sqlite3.connect(cache_db)
    try:
        largest = conn.execute(
            'SELECT Name FROM packages ORDER BY Installed_Size DESC LIMIT 1'
        ).fetchone()[0]
    finally:
        conn.close()
    assert names[0] == largest


def test_has_note_filter(project_root):
    names = run_list(project_root, '--has-note')
    assert names == ['lavat-git']


def test_no_note_filter_excludes_noted(project_root):
    names = run_list(project_root, '--no-note')
    assert 'lavat-git' not in names
    assert names  # everything else


def test_total_size_respects_filter(project_root, cache_db):
    # B2: filtered total must equal the SUM over just the foreign packages,
    # and must be strictly less than the grand total.
    foreign_total = _db_scalar(
        cache_db, 'SELECT SUM(Installed_Size) FROM packages WHERE is_foreign = 1'
    )
    grand_total = _db_scalar(cache_db, 'SELECT SUM(Installed_Size) FROM packages')

    from preview_item import bytes_to_human
    out_foreign = run_list(project_root, '-t', '-m')
    out_all = run_list(project_root, '-t')

    assert out_foreign == [bytes_to_human(foreign_total)]
    assert out_all == [bytes_to_human(grand_total)]
    assert foreign_total < grand_total  # sanity: the filter actually narrowed


def test_total_size_with_notes_filter(project_root, cache_db):
    # B2 + notes composition: total over only the noted packages.
    from preview_item import bytes_to_human
    noted_size = _db_scalar(
        cache_db, "SELECT SUM(Installed_Size) FROM packages WHERE Name = 'lavat-git'"
    )
    out = run_list(project_root, '-t', '--has-note')
    assert out == [bytes_to_human(noted_size)]


def test_scoped_invert(project_root, cache_db):
    # explicit packages where NOT(notadep) == explicit AND required by something
    names = run_list(project_root, '-e', '-v', 'notadep')
    expected = _db_scalar(
        cache_db,
        "SELECT COUNT(*) FROM packages WHERE "
        "Install_Reason = 'Explicitly installed' "
        "AND NOT (Required_By = 'None')",
    )
    assert len(names) == expected


def test_preview_renders_note(project_root):
    res = run_preview(project_root, 'lavat-git')
    assert res.returncode == 0
    assert 'Build from source' in res.stdout  # the note text
    assert 'Note' in res.stdout


def test_preview_hide_notes(project_root):
    res = run_preview(project_root, 'lavat-git', '--hide-notes')
    assert res.returncode == 0
    assert 'Build from source' not in res.stdout
