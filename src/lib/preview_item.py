import argparse
import os
import re
import sqlite3
import sys
from typing import Dict, Optional

from config import cache_db_path
from notes_db import get_note

DB_PATH = cache_db_path()
TABLE_NAME = 'packages'
NAME_FIELD = 'Name'

# Color codes (matching the shell config).
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
RESET = COLORS['RESET']

# Real table fields (kept as a comment so it can't masquerade as live data):
#   Architecture, Build Date, Conflicts With, Depends On, Description, Groups,
#   Install Date, Install Reason, Install Script, Installed Size, Licenses,
#   Name, Optional Deps, Optional For, Packager, Provides, Replaces,
#   Required By, URL, Validated By, Version, is foreign

# Format: label -> (label_color, value_color). 'break*' entries render a blank
# line. 'Note' is injected at runtime unless --hide-notes is passed; it is
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

# Keyword -> color, applied only to the fields where these words are a
# meaningful status rather than incidental free text. Restricting this set
# stops words like "none"/"no" inside a Description from being recolored.
KEYWORD_COLORS = {
    'Explicitly installed': COLORS['GREEN'],
    'Installed as a dependency for another package': COLORS['YELLOW'],
    'Yes': COLORS['GREEN'],
    'No': COLORS['BRIGHT_BLACK'],
    'None': COLORS['BRIGHT_BLACK'],
}
KEYWORD_FIELDS = {'is foreign', 'Install Reason'}

COLON_COLOR = COLORS['BRIGHT_BLACK']
FALLBACK_LABEL_COLOR = COLORS['BRIGHT_BLACK']
FALLBACK_VALUE_COLOR = RESET


def colorize_value(value: str) -> str:
    """Apply keyword-specific colors to whole-word matches in ``value``."""
    result = value
    for keyword, color in KEYWORD_COLORS.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        replacement = f"{color}{keyword}{RESET}"
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def format_line(label: str, value: str) -> str:
    """Format a single label-value line with colors."""
    label_color, value_color = LABEL_FORMAT.get(
        label, (FALLBACK_LABEL_COLOR, FALLBACK_VALUE_COLOR)
    )

    if label in KEYWORD_FIELDS:
        colored_value = colorize_value(value)
        if colored_value == value:  # no keyword matched
            colored_value = f"{value_color}{value}{RESET}"
    else:
        colored_value = f"{value_color}{value}{RESET}"

    return (
        f"{label_color}{label:<16}{RESET}"
        f"{COLON_COLOR}: {RESET}{colored_value}"
    )


def bytes_to_human(bytes_value) -> str:
    """Convert a byte count to a human-readable string (e.g. 2.34 MiB)."""
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


def query_database(db_path: Optional[str] = None,
                   name: str = None) -> Optional[Dict[str, str]]:
    """Fetch a single package row as a dict, with '_' replaced by ' ' in keys."""
    if db_path is None:
        db_path = DB_PATH

    query = f'SELECT * FROM {TABLE_NAME} WHERE {NAME_FIELD}=? LIMIT 1'
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query, (name,)).fetchone()
        if not row:
            return None
        return {key.replace('_', ' '): value for key, value in dict(row).items()}
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return None
    finally:
        conn.close()


def _formatted_line_for(key: str, data: Dict[str, str]) -> Optional[str]:
    """Return the formatted line for `key` against `data`.

    Returns '' for a break marker (renders as a blank line), or None if
    `key` isn't present in `data` at all (e.g. 'Note' when no note exists),
    so callers can skip it entirely.
    """
    if 'break' in key:
        return ''

    value = data.get(key)
    if value is None:
        return None

    if key == 'is foreign':
        value = {1: 'Yes', 0: 'No'}.get(int(value), 'No')

    if key == 'Installed Size':
        value = bytes_to_human(value)

    return format_line(key, value)


def print_line(key: str, data: Dict[str, str]) -> None:
    line = _formatted_line_for(key, data)
    if line is not None:
        print(line)


def render_preview(data: Dict[str, str]) -> str:
    """Build the full multi-line ANSI-colored preview for `data` as one string.

    Same content `print_line` prints line-by-line for the CLI, joined into a
    single string — meant for reuse by other frontends (e.g. a TUI, via
    Rich's `Text.from_ansi()`), so the formatting logic — colors, field
    order, keyword highlighting — only ever lives in this one place.
    """
    lines = []
    for category in LABEL_FORMAT:
        line = _formatted_line_for(category, data)
        if line is not None:
            lines.append(line)
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(usage=argparse.SUPPRESS)
    parser.add_argument(
        '--hide-notes', action='store_true',
        help='do not fetch or display the user note for this package',
    )
    parser.add_argument(
        'pkg', nargs='?',
        help='package name (falls back to stdin when omitted)',
    )
    args = parser.parse_args()

    # Priority: stdin (pipe from fzf) -> positional arg -> exit.
    if not sys.stdin.isatty():
        line = sys.stdin.readline().strip()
    elif args.pkg:
        line = args.pkg.strip()
    else:
        sys.exit(1)

    if not line:
        sys.exit(0)

    data = query_database(db_path=DB_PATH, name=line)
    if not data:
        sys.exit(0)

    # Inject the user note unless suppressed. When --hide-notes is set the
    # notes DB is never opened.
    if not args.hide_notes:
        note = get_note(line)
        if note:
            data['Note'] = note

    for category in LABEL_FORMAT:
        print_line(category, data)


if __name__ == '__main__':
    main()
