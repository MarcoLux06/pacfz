import os
import sqlite3
import subprocess
import sys

import pytest


def run_list(lib_dir, *args):
    """Run list_packages.py as a subprocess; return stdout lines."""
    script = os.path.join(str(lib_dir), 'list_packages.py')
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    return [ln for ln in result.stdout.splitlines() if ln]


def run_preview(lib_dir, pkg, *args):
    script = os.path.join(str(lib_dir), 'preview_item.py')
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


def test_no_args_lists_all_sorted(lib_dir, cache_db):
    names = run_list(lib_dir)
    expected = _db_scalar(cache_db, 'SELECT COUNT(*) FROM packages')
    assert len(names) == expected
    assert names == sorted(names)  # default ASC by Name


def test_foreign_filter(lib_dir, cache_db):
    names = run_list(lib_dir, '-m')
    expected = _db_scalar(cache_db, 'SELECT COUNT(*) FROM packages WHERE is_foreign = 1')
    assert len(names) == expected


def test_orphan_count_matches_direct_sql(lib_dir, cache_db):
    # H2: '= None' must return exactly what the semantic query does.
    names = run_list(lib_dir, '-o')
    expected = _db_scalar(
        cache_db,
        "SELECT COUNT(*) FROM packages WHERE "
        "Install_Reason = 'Installed as a dependency for another package' "
        "AND Required_By = 'None'",
    )
    assert len(names) == expected


def test_explicit_field_search(lib_dir):
    names = run_list(lib_dir, '-f', 'Name', 'python')
    assert names, "expected at least one python* package"
    assert all('python' in n.lower() for n in names)


def test_sort_by_size_desc_default(lib_dir, cache_db):
    names = run_list(lib_dir, '-s')
    # First name should be the largest package by Installed_Size.
    conn = sqlite3.connect(cache_db)
    try:
        largest = conn.execute(
            'SELECT Name FROM packages ORDER BY Installed_Size DESC LIMIT 1'
        ).fetchone()[0]
    finally:
        conn.close()
    assert names[0] == largest


def test_has_note_filter(lib_dir):
    names = run_list(lib_dir, '--has-note')
    assert names == ['lavat-git']


def test_no_note_filter_excludes_noted(lib_dir):
    names = run_list(lib_dir, '--no-note')
    assert 'lavat-git' not in names
    assert names  # everything else


def test_total_size_respects_filter(lib_dir, cache_db):
    # B2: filtered total must equal the SUM over just the foreign packages,
    # and must be strictly less than the grand total.
    foreign_total = _db_scalar(
        cache_db, 'SELECT SUM(Installed_Size) FROM packages WHERE is_foreign = 1'
    )
    grand_total = _db_scalar(cache_db, 'SELECT SUM(Installed_Size) FROM packages')

    from preview_item import bytes_to_human
    out_foreign = run_list(lib_dir, '-t', '-m')
    out_all = run_list(lib_dir, '-t')

    # -t now prints a descriptive sentence first, then the number on its own
    # line — check the number specifically (the last line), not the whole
    # output, since the description text itself is covered by its own tests.
    assert out_foreign[-1] == bytes_to_human(foreign_total)
    assert out_all[-1] == bytes_to_human(grand_total)
    assert foreign_total < grand_total  # sanity: the filter actually narrowed


def test_total_size_with_notes_filter(lib_dir, cache_db):
    # B2 + notes composition: total over only the noted packages.
    from preview_item import bytes_to_human
    noted_size = _db_scalar(
        cache_db, "SELECT SUM(Installed_Size) FROM packages WHERE Name = 'lavat-git'"
    )
    out = run_list(lib_dir, '-t', '--has-note')
    assert out[-1] == bytes_to_human(noted_size)


def test_pacq_totalsize_has_no_description(project_root):
    # pacq is the scriptable front-end — its -t output must be just the
    # number, nothing else, unlike pacfz/the raw script's default of
    # printing a descriptive sentence first.
    pacq = os.path.join(str(project_root), 'src', 'pacq')
    result = subprocess.run(
        [pacq, '-e', '-t'], capture_output=True, text=True, env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.splitlines() if ln]
    assert len(lines) == 1, f"expected exactly one line, got: {lines!r}"


def test_totalsize_description_default(lib_dir):
    # No filters at all -> the plain generic fallback sentence.
    out = run_list(lib_dir, '-t')
    assert out[0] == "total package size:"


def test_totalsize_description_single_filter(lib_dir):
    out = run_list(lib_dir, '-m', '-t')
    assert out[0] == "total size of foreign packages:"


def test_totalsize_description_combines_filters(lib_dir):
    # Order follows _describe_active_filters' own iteration order
    # (foreign before explicit), not the order flags were passed on the
    # command line.
    out = run_list(lib_dir, '-e', '-m', '-t')
    assert out[0] == "total size of foreign, explicitly installed packages:"


def test_totalsize_description_field_search(lib_dir):
    out = run_list(lib_dir, '-f', 'Name', 'vim', '-t')
    assert out[0] == 'total package size where Name matches "vim":'


def test_totalsize_description_filter_and_field_search_combine(lib_dir):
    out = run_list(lib_dir, '-e', '-f', 'Licenses', 'GPL', '-t')
    assert out[0] == 'total size of explicitly installed packages where Licenses matches "GPL":'


def test_scoped_invert(lib_dir, cache_db):
    # explicit packages where NOT(notadep) == explicit AND required by something
    names = run_list(lib_dir, '-e', '-v', 'notadep')
    expected = _db_scalar(
        cache_db,
        "SELECT COUNT(*) FROM packages WHERE "
        "Install_Reason = 'Explicitly installed' "
        "AND NOT (Required_By = 'None')",
    )
    assert len(names) == expected


def test_preview_renders_note(lib_dir):
    res = run_preview(lib_dir, 'lavat-git')
    assert res.returncode == 0
    assert 'Build from source' in res.stdout  # the note text
    assert 'Note' in res.stdout


def test_preview_hide_notes(lib_dir):
    res = run_preview(lib_dir, 'lavat-git', '--hide-notes')
    assert res.returncode == 0
    assert 'Build from source' not in res.stdout
