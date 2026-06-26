"""All access to the user-notes database lives here.

Previously this logic was copy-pasted across preview_item.py, note_manager.py
and list_packages.py; keeping it in one module stops the copies from drifting
apart. These functions are deliberately I/O-only and never print - the CLI
layer (note_manager.py) is responsible for user-facing messages.
"""
import os
import sqlite3
from pathlib import Path
from typing import List, Optional, Set, Tuple

from config import notes_db_path

TABLE_NAME = 'user_data'


def _path(db_path: Optional[str]) -> str:
    return db_path if db_path is not None else notes_db_path()


def ensure_db(db_path: Optional[str] = None) -> None:
    """Create the notes DB and table if they don't exist.

    Raises:
        RuntimeError: if the parent directory cannot be created.
    """
    db_path = _path(db_path)
    db_dir = os.path.dirname(db_path)
    if db_dir:
        try:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Failed to create notes DB directory {db_dir}: {e}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS user_data (
                name TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT ''
            )
            '''
        )
        conn.commit()
    finally:
        conn.close()


def get_note(name: str, db_path: Optional[str] = None) -> Optional[str]:
    """Return the note for a package, or None.

    Never creates the DB - safe in read-only contexts. Returns None if the DB
    doesn't exist, the package has no note, or on any DB error.
    """
    db_path = _path(db_path)
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            row = conn.execute(
                'SELECT note FROM user_data WHERE name = ?', (name,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def get_packages_with_notes(db_path: Optional[str] = None) -> Set[str]:
    """Return the set of package names that have a note.

    Returns an empty set if the DB doesn't exist yet or on any error, so
    callers don't need to special-case those.
    """
    db_path = _path(db_path)
    if not os.path.exists(db_path):
        return set()
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            return {row[0] for row in conn.execute('SELECT name FROM user_data')}
        finally:
            conn.close()
    except sqlite3.Error:
        return set()


def list_notes_rows(db_path: Optional[str] = None) -> List[Tuple[str, str]]:
    """Return all (name, note) rows ordered by name.

    Raises:
        RuntimeError: on a DB error (a missing DB is not an error - returns []).
    """
    db_path = _path(db_path)
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            return list(
                conn.execute('SELECT name, note FROM user_data ORDER BY name')
            )
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to read notes: {e}")


def set_note(name: str, note: str, db_path: Optional[str] = None) -> None:
    """Create or update the note for a package.

    Raises:
        RuntimeError: on a DB error.
    """
    db_path = _path(db_path)
    ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            '''
            INSERT INTO user_data (name, note) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET note = excluded.note
            ''',
            (name, note),
        )
        conn.commit()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to set note: {e}")
    finally:
        conn.close()


def delete_note(name: str, db_path: Optional[str] = None) -> bool:
    """Delete the note for a package.

    Returns True if a note was removed, False if there was nothing to remove
    (no DB, or no row for that package).

    Raises:
        RuntimeError: on a DB error.
    """
    db_path = _path(db_path)
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute('DELETE FROM user_data WHERE name = ?', (name,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete note: {e}")
    finally:
        conn.close()
