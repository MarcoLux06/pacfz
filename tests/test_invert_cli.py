import os
import sqlite3
import subprocess
import sys

import pytest


def run_list_raw(lib_dir, *args):
    """Like test_cli.py's run_list, but returns the full CompletedProcess
    (not just stdout lines) — several of these tests need to check
    returncode/stderr for the invalid-combination cases, not just stdout.
    """
    script = os.path.join(str(lib_dir), 'list_packages.py')
    return subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, env=os.environ.copy(),
    )


def _db_scalar(cache_db, sql):
    conn = sqlite3.connect(cache_db)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def test_bare_invert_negates_a_single_filter(lib_dir, cache_db):
    # pacq -m -v -> NOT foreign
    result = run_list_raw(lib_dir, '-m', '-v')
    assert result.returncode == 0, result.stderr
    names = [ln for ln in result.stdout.splitlines() if ln]
    expected = _db_scalar(cache_db, "SELECT COUNT(*) FROM packages WHERE is_foreign != 1")
    assert len(names) == expected


def test_bare_invert_with_field_search(lib_dir, cache_db):
    # pacq -f Name python -v -> NOT (Name contains "python")
    result = run_list_raw(lib_dir, '-f', 'Name', 'python', '-v')
    assert result.returncode == 0, result.stderr
    names = [ln for ln in result.stdout.splitlines() if ln]
    expected = _db_scalar(
        cache_db, "SELECT COUNT(*) FROM packages WHERE Name NOT LIKE '%python%'"
    )
    assert len(names) == expected


def test_bare_invert_with_nothing_to_invert_is_rejected(lib_dir):
    # -v with no other active filter has nothing to negate — build_query()
    # itself raises ValueError for this (see test_build_query.py), and
    # main() must translate that into a clean CLI error, not a traceback.
    result = run_list_raw(lib_dir, '-v')
    assert result.returncode != 0
    assert 'nothing to invert' in result.stderr.lower()


def test_bare_and_named_invert_together_is_rejected(lib_dir):
    # -v -v foreign: one bare, one named. argparse's action="append" with
    # nargs="?"/const="__ALL__" means this parses to invert_args =
    # ['__ALL__', 'foreign'] — main() must reject the combination outright
    # rather than silently picking one interpretation.
    result = run_list_raw(lib_dir, '-v', '-v', 'foreign')
    assert result.returncode != 0
    assert 'combine -v either bare' in result.stderr


def test_named_invert_unknown_filter_name_is_rejected(lib_dir):
    result = run_list_raw(lib_dir, '-v', 'not-a-real-filter')
    assert result.returncode != 0
    assert 'unknown filter' in result.stderr.lower()
    # the error should name the valid options, not just say "invalid"
    assert 'foreign' in result.stderr.lower()


@pytest.mark.parametrize("alias,canonical", [
    ('m', 'foreign'), ('o', 'orphan'), ('e', 'explicit'),
    ('d', 'deps'), ('n', 'notadep'), ('k', 'notoptdep'),
])
def test_named_invert_short_letter_aliases(lib_dir, cache_db, alias, canonical):
    # -v accepts both the full name (e.g. "foreign") and its short letter
    # (e.g. "m") — both must resolve to the identical filter.
    result_full = run_list_raw(lib_dir, '-e', '-v', canonical)
    result_short = run_list_raw(lib_dir, '-e', '-v', alias)
    assert result_full.returncode == 0, result_full.stderr
    assert result_short.returncode == 0, result_short.stderr
    assert result_full.stdout == result_short.stdout


def test_multiple_named_inverts_scoped_together(lib_dir, cache_db):
    # -v notadep -v notoptdep: both named filters get AND'd together
    # inside ONE negation (NOT(A AND B)), scoped separately from the -e
    # precondition — this is the exact case the README's worked example
    # uses ("explicit packages that ARE required by something, optionally
    # or not").
    result = run_list_raw(lib_dir, '-e', '-v', 'notadep', '-v', 'notoptdep')
    assert result.returncode == 0, result.stderr
    names = [ln for ln in result.stdout.splitlines() if ln]
    expected = _db_scalar(
        cache_db,
        "SELECT COUNT(*) FROM packages WHERE "
        "Install_Reason = 'Explicitly installed' "
        "AND NOT (Required_By = 'None' AND Optional_For = 'None')",
    )
    assert len(names) == expected
