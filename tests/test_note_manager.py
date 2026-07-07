import os
import subprocess
import sys


def run_note_manager(lib_dir, notes_db_path, *args, input_text=None):
    """Run note_manager.py as a subprocess against an isolated notes DB.

    note_manager.py reads PACFZ_NOTES_DB_PATH at import time (same
    frozen-at-import pattern as list_packages.py/preview_item.py's DB_PATH),
    so isolation has to happen via the subprocess's own environment, not a
    Python-level fixture — each call gets its own env dict so tests never
    share state through a real ~/.local/share notes DB.
    """
    script = os.path.join(str(lib_dir), 'note_manager.py')
    env = os.environ.copy()
    env['PACFZ_NOTES_DB_PATH'] = notes_db_path
    return subprocess.run(
        [sys.executable, script, *args],
        input=input_text, capture_output=True, text=True, env=env,
    )


def test_set_note(lib_dir, fresh_notes_db):
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'daily browser')
    assert result.returncode == 0, result.stderr
    assert "Note set for 'firefox'" in result.stdout


def test_set_note_then_get_it_back(lib_dir, fresh_notes_db):
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'daily browser')
    result = run_note_manager(lib_dir, fresh_notes_db, '--get', 'firefox')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'daily browser'


def test_set_note_upsert_overwrites(lib_dir, fresh_notes_db):
    # setting a note twice for the same package must update, not duplicate
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'first note')
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'second note')
    result = run_note_manager(lib_dir, fresh_notes_db, '--get', 'firefox')
    assert result.stdout.strip() == 'second note'


def test_delete_existing_note(lib_dir, fresh_notes_db):
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'daily browser')
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', '-d')
    assert result.returncode == 0, result.stderr
    assert "Note deleted for 'firefox'" in result.stdout

    # confirm it's actually gone
    result2 = run_note_manager(lib_dir, fresh_notes_db, '--get', 'firefox')
    assert result2.stdout.strip() == ''


def test_delete_nonexistent_note_reports_not_found(lib_dir, fresh_notes_db):
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'nosuchpkg', '-d')
    assert result.returncode == 0, result.stderr
    assert "No note found for 'nosuchpkg'" in result.stdout


def test_list_notes_empty(lib_dir, fresh_notes_db):
    result = run_note_manager(lib_dir, fresh_notes_db, '--list')
    assert result.returncode == 0, result.stderr
    assert "No notes found." in result.stdout


def test_list_notes_shows_all(lib_dir, fresh_notes_db):
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'daily browser')
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'vim', 'editor of choice')
    result = run_note_manager(lib_dir, fresh_notes_db, '--list')
    assert result.returncode == 0, result.stderr
    assert 'firefox' in result.stdout
    assert 'daily browser' in result.stdout
    assert 'vim' in result.stdout
    assert 'editor of choice' in result.stdout


def test_pkg_with_no_note_and_no_delete_flag_errors(lib_dir, fresh_notes_db):
    # -D pkg with neither a note string nor -d is an argparse usage error
    # (parser.error(...)), not a silent no-op.
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox')
    assert result.returncode != 0
    assert 'provide a note string or -d to delete' in result.stderr


def test_no_args_prints_help(lib_dir, fresh_notes_db):
    result = run_note_manager(lib_dir, fresh_notes_db)
    assert result.returncode == 0, result.stderr
    assert 'usage' in result.stdout.lower() or 'Manage per-package' in result.stdout


def test_get_missing_package_prints_nothing(lib_dir, fresh_notes_db):
    # --get on a package with no note should succeed silently, not error --
    # callers (preview_item.py) rely on "empty output" meaning "no note".
    result = run_note_manager(lib_dir, fresh_notes_db, '--get', 'nosuchpkg')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ''


def test_note_text_matching_a_real_flag_is_misparsed(lib_dir, fresh_notes_db):
    # KNOWN BUG (U2, code review): note_manager.py has no `--` separator
    # handling, so a note whose text happens to match a REGISTERED flag
    # (e.g. "-d", which is also --delete) is silently treated as that flag
    # instead of as the note's text. This is worse than a parse error: the
    # command below sets no note at all and instead deletes any existing
    # one for "firefox", because argparse sees -D firefox -d and reads it
    # as "delete firefox's note", not "set firefox's note to the text -d".
    run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', 'existing note')
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', '-d')
    assert result.returncode == 0, result.stderr
    # Today: silently deletes instead of setting the note to the text "-d".
    # If this assertion ever starts failing, it likely means U2 got fixed
    # (e.g. via a -- separator) — update this test to assert the note was
    # actually SET to "-d" instead.
    assert "Note deleted for 'firefox'" in result.stdout

    get_result = run_note_manager(lib_dir, fresh_notes_db, '--get', 'firefox')
    assert get_result.stdout.strip() == '', "note should be gone, not set to '-d'"


def test_note_text_matching_no_flag_fails_loudly_not_silently(lib_dir, fresh_notes_db):
    # KNOWN BUG (U2, code review), the other half: a note text that starts
    # with '-' but ISN'T a registered flag (e.g. "-x") is at least rejected
    # with a clear argparse error, rather than silently doing the wrong
    # thing — but it still means such a note can never be set at all.
    result = run_note_manager(lib_dir, fresh_notes_db, '-D', 'firefox', '-x')
    assert result.returncode != 0
    assert 'unrecognized arguments' in result.stderr
