import sqlite3
import os
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Tuple

NOTES_DB_PATH = os.path.expanduser('~/.local/share/pacfz/user_data.db')
TABLE_NAME = 'user_data'


def ensure_db(db_path: str = NOTES_DB_PATH) -> None:
    """
    Create the notes DB and table if they don't exist.

    Raises:
        RuntimeError: If the directory cannot be created
    """
    db_dir = os.path.dirname(db_path)
    try:
        Path(db_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Failed to create notes DB directory {db_dir}: {e}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_data (
                name     TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT ''
            )
        ''')
        conn.commit()
    finally:
        conn.close()


def set_note(name: str, note: str, db_path: str = NOTES_DB_PATH) -> None:
    """
    Set or update the note for a package.

    Raises:
        RuntimeError: On DB error
    """
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
        print(f"✓ Note set for '{name}'")
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to set note: {e}")
    finally:
        conn.close()


def delete_note(name: str, db_path: str = NOTES_DB_PATH) -> None:
    """
    Delete the note for a package.

    Raises:
        RuntimeError: On DB error
    """
    if not os.path.exists(db_path):
        print(f"No notes DB found — nothing to delete.")
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_data WHERE name = ?', (name,))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"✓ Note deleted for '{name}'")
        else:
            print(f"No note found for '{name}'")
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete note: {e}")
    finally:
        conn.close()


def get_note(name: str, db_path: str = NOTES_DB_PATH) -> Optional[str]:
    """
    Fetch the note for a package.

    Returns None if the DB doesn't exist, the package has no note, or on error.
    Never creates the DB — safe to call in read-only contexts.
    """
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute('SELECT note FROM user_data WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def list_notes(db_path: str = NOTES_DB_PATH) -> None:
    """Print all packages that have notes, aligned in two columns."""
    if not os.path.exists(db_path):
        print("No notes DB found.")
        return

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute('SELECT name, note FROM user_data ORDER BY name')
        rows: List[Tuple[str, str]] = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return

    if not rows:
        print("No notes found.")
        return

    col_w = max(len(r[0]) for r in rows)
    for name, note in rows:
        print(f"{name:<{col_w}}  {note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Manage per-package usage notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pacfz -D firefox "daily browser"   set a note
  pacfz -D firefox -d                delete the note
  pacfz --notes-list                 list all packages with notes
""",
    )

    parser.add_argument(
        '-D', metavar='PKG', dest='pkg',
        help='Package to operate on',
    )
    parser.add_argument(
        '-d', '--delete', action='store_true',
        help='Delete the note for -D <pkg>',
    )
    parser.add_argument(
        'note', nargs='?',
        help='Note text to set (use with -D <pkg>)',
    )
    parser.add_argument(
        '--list', action='store_true',
        help='List all packages that have notes',
    )
    # --get is for internal use by previewItem.py if ever needed via subprocess
    parser.add_argument(
        '--get', metavar='PKG',
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    try:
        if args.list:
            list_notes()
        elif args.get:
            note = get_note(args.get)
            if note:
                print(note)
        elif args.pkg:
            if args.delete:
                delete_note(args.pkg)
            elif args.note is not None:
                set_note(args.pkg, args.note)
            else:
                parser.error("provide a note string or -d to delete")
        else:
            parser.print_help()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
