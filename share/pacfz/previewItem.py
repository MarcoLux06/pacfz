import sqlite3
from typing import Optional, Dict
import re
import os
import sys
import argparse

DB_PATH = os.path.expanduser('~/.cache/pacman_packages.db')
NOTES_DB_PATH = os.path.expanduser('~/.local/share/pacfz/user_data.db')
TABLE_NAME = 'packages'
NAME_FIELD = 'Name'

# Color codes from your shell config
COLORS = {
    'GREEN': '\033[32m',
    'CYAN': '\033[36m',
    'RED': '\033[31m',
    'YELLOW': '\033[33m',
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'BRIGHT_BLACK': '\033[90m',
    'RESET': '\033[0m',
}

# all available table fields:
"""
Architecture
Build Date
Conflicts With
Depends On
Description
Groups
Install Date
Install Reason
Install Script
Installed Size
Licenses
Name
Optional Deps
Optional For
Packager
Provides
Replaces
Required By
URL
Validated By
Version
is foreign
"""
# Format: label -> (label_color, value_color)
# 'Note' is injected at runtime unless --hide-notes is passed; it will be
# skipped silently if the key is absent from the data dict.
LABEL_FORMAT = {
    'Name': (COLORS['GREEN'], COLORS['GREEN']),
    'Version': (COLORS['CYAN'], COLORS['CYAN']),
    'Description': (COLORS['CYAN'], COLORS['CYAN']),
    'Groups': (COLORS['GREEN'], COLORS['GREEN']),
    'break0': None,

    'Depends On': (COLORS['YELLOW'], COLORS['YELLOW']),
    'Optional Deps': (COLORS['YELLOW'], COLORS['YELLOW']),
    'Required By': (COLORS['YELLOW'], COLORS['YELLOW']),
    'Optional For': (COLORS['YELLOW'], COLORS['YELLOW']),
    'break1': None,

    'Installed Size': (COLORS['BLUE'], COLORS['BLUE']),
    'Install Reason': (COLORS['BLUE'], COLORS['BLUE']),

    'break2': None,
    'Architecture': (COLORS['BRIGHT_BLACK'], COLORS['BRIGHT_BLACK']),
    'Licenses': (COLORS['BRIGHT_BLACK'], COLORS['BRIGHT_BLACK']),
    'Build Date': (COLORS['BRIGHT_BLACK'], COLORS['BRIGHT_BLACK']),
    'Validated By': (COLORS['BRIGHT_BLACK'], COLORS['BRIGHT_BLACK']),

    'break3': None,
    'is foreign': (COLORS['BRIGHT_BLACK'], COLORS['BRIGHT_BLACK']),
    'Note': (COLORS['MAGENTA'], COLORS['MAGENTA']),
}

# Keyword colors: keyword -> color (overwrites value color for that keyword only)
KEYWORD_COLORS = {
    # install reasons:
    'Explicitly installed': COLORS['GREEN'],
    'Installed as a dependency for another package': COLORS['YELLOW'],

    # misc
    'Yes': COLORS['GREEN'],
    'No': COLORS['BRIGHT_BLACK'],
    'None': COLORS['BRIGHT_BLACK'],
}

COLON_COLOR = COLORS['BRIGHT_BLACK']
FALLBACK_LABEL_COLOR = COLORS['BRIGHT_BLACK']
FALLBACK_VALUE_COLOR = COLORS['RESET']


def colorize_value(input_value):
    """Apply keyword-specific colors to value, overwriting value_color for matched keywords."""
    result = input_value

    for keyword, color in KEYWORD_COLORS.items():
        # Use word boundaries to match whole words only
        pattern = r'\b' + re.escape(keyword) + r'\b'
        replacement = f"{color}{keyword}{COLORS['RESET']}"
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def format_line(input_label, input_value):
    """Format a single label-value line with colors."""
    # Get colors from dict or use fallback
    if input_label in LABEL_FORMAT:
        label_color, value_color = LABEL_FORMAT[input_label]
    else:
        label_color = FALLBACK_LABEL_COLOR
        value_color = FALLBACK_VALUE_COLOR

    # Colorize value with keyword highlighting
    colored_value = colorize_value(input_value)

    # If no keywords were matched, apply the default value color
    if colored_value == input_value:
        colored_value = f"{value_color}{input_value}{COLORS['RESET']}"

    return f"{label_color}{input_label:<16}{COLORS['RESET']}{COLON_COLOR}: {COLORS['RESET']}{colored_value}"


def bytes_to_human(bytes_value) -> str:
    """
    Convert bytes to human-readable format (e.g., 2.34 MiB, 1929.95 KiB).
    """
    if bytes_value is None or bytes_value == '':
        return ''

    try:
        bytes_value = int(bytes_value)
    except (ValueError, TypeError):
        return str(bytes_value)

    units = [
        ('TiB', 1024 ** 4),
        ('GiB', 1024 ** 3),
        ('MiB', 1024 ** 2),
        ('KiB', 1024),
        ('B', 1),
    ]

    for unit, divisor in units:
        if bytes_value >= divisor:
            size = bytes_value / divisor
            if unit == 'B':
                return f"{int(size)}.00 {unit}"
            return f"{size:.2f} {unit}"

    return f"{bytes_value}.00 B"


def get_note(name: str) -> Optional[str]:
    """
    Fetch the user note for a package from the notes DB.

    Never creates the DB — returns None if it doesn't exist, if there is
    no note for this package, or on any DB error.
    """
    if not os.path.exists(NOTES_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(f'file:{NOTES_DB_PATH}?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute('SELECT note FROM user_data WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def query_database(db_path: str = None, name: str = None) -> Optional[Dict[str, str]]:
    query = f'SELECT * FROM {TABLE_NAME} WHERE {NAME_FIELD}=? LIMIT 1'

    if db_path is None:
        db_path = DB_PATH

    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(query, (name,))  # safer than string formatting
        row = cursor.fetchone()
        # replace _ with space
        return {key.replace('_', ' '): _value for key, _value in dict(row).items()} if row else None
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return None
    finally:
        conn.close()


def print_line(key: str, dic: Dict[str, str]):
    if 'break' in key:
        print()
        return

    # Use .get() so that keys present in LABEL_FORMAT but absent from the
    # data dict (e.g. 'Note' when --hide-notes is set) are silently skipped.
    _value = dic.get(key)
    if _value is None:
        return

    # maps 0/1 to yes and no
    # also look out for KEYWORD_COLORS
    if key == 'is foreign':
        mapping = {1: 'Yes', 0: 'No'}
        _value = mapping.get(int(_value), 'No')  # Fallback to 'No' if _value isn't 1 or 0

    # transform raw bytes into human-readable string
    if key == 'Installed Size':
        _value = bytes_to_human(_value)

    print(format_line(key, _value))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(usage=argparse.SUPPRESS)
    parser.add_argument(
        '--hide-notes', action='store_true',
        help='Do not fetch or display the user note for this package',
    )
    parser.add_argument(
        'pkg', nargs='?',
        help='Package name (falls back to stdin when omitted)',
    )
    args = parser.parse_args()

    # Priority: stdin (pipe from fzf) → positional arg → exit
    if not sys.stdin.isatty():
        line = sys.stdin.readline().strip()
    elif args.pkg:
        line = args.pkg.strip()
    else:
        sys.exit(1)

    if not line:
        sys.exit(0)

    # Query the pacman packages DB
    data = query_database(db_path=DB_PATH, name=line)

    if not data:
        sys.exit(0)

    # Inject the user note unless explicitly suppressed.
    # Skipped entirely when --hide-notes is set — notes DB is never opened.
    if not args.hide_notes:
        note = get_note(line)
        if note:
            data['Note'] = note

    # Print formatted output
    for category in LABEL_FORMAT:
        print_line(category, data)
