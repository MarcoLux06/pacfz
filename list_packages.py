import argparse
import os
import sqlite3
import subprocess
import sys
from typing import Iterator, List, Optional, Tuple

from config import cache_db_path
from notes_db import get_packages_with_notes
from preview_item import bytes_to_human

DB_PATH = cache_db_path()
TABLE_NAME = 'packages'
NAME_FIELD = 'Name'
SIZE_FIELD = 'Installed_Size'
INSTALL_REASON_FIELD = 'Install_Reason'
FOREIGN_FIELD = 'is_foreign'
REQUIRED_BY_FIELD = 'Required_By'
OPT_REQUIRED_BY_FIELD = 'Optional_For'

# Canned WHERE clauses.
#
# NOTE: 'None' below is pacman's *literal output string* (what `pacman -Qi`
# prints for an empty field), stored verbatim as TEXT — it is NOT SQL NULL.
# Use '=' here, not 'IS' / 'IS NULL'.
WHERE_CLAUSES = {
    'foreign': f"{FOREIGN_FIELD} = 1",
    'orphan': (
        f"{INSTALL_REASON_FIELD} = 'Installed as a dependency for another package' "
        f"AND {REQUIRED_BY_FIELD} = 'None'"
    ),
    'explicit': f"{INSTALL_REASON_FIELD} = 'Explicitly installed'",
    'deps': f"{INSTALL_REASON_FIELD} = 'Installed as a dependency for another package'",
    'notadep': f"{REQUIRED_BY_FIELD} = 'None'",
    'notoptdep': f"{OPT_REQUIRED_BY_FIELD} = 'None'",
}

# Maps every short letter / long spelling to its WHERE_CLAUSES key, for
# resolving the -v/--invert FILTER argument.
CANNED_FILTER_ALIASES = {
    'm': 'foreign', 'foreign': 'foreign',
    'o': 'orphan', 'orphan': 'orphan', 'orphans': 'orphan',
    'e': 'explicit', 'explicit': 'explicit',
    'd': 'deps', 'deps': 'deps',
    'n': 'notadep', 'notadep': 'notadep',
    'k': 'notoptdep', 'notoptdep': 'notoptdep',
}


# ---------------------------------------------------------------------------
# First-run cache build (B1)
# ---------------------------------------------------------------------------
def build_cache_db() -> None:
    """Build the package cache by invoking create_db.py. Raises on failure."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'create_db.py')
    subprocess.run(
        [sys.executable, script, '--quiet', '--path', DB_PATH], check=True
    )


def ensure_cache_db() -> None:
    """Build the cache DB on first use if it doesn't exist yet.

    Without this, the very first `pacfz`/`pacq` invocation would fail with a
    cryptic "unable to open database file" from the read-only connection.
    """
    if os.path.exists(DB_PATH):
        return
    print("Building package cache (first run)...", file=sys.stderr)
    try:
        build_cache_db()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        print(f"Error: failed to build package cache: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Name resolution helpers
# ---------------------------------------------------------------------------
def resolve_canned_filter_name(name: str) -> str:
    """Resolve a -v/--invert FILTER argument to its WHERE_CLAUSES key.

    Raises:
        ValueError: if the name doesn't match any canned filter.
    """
    key = CANNED_FILTER_ALIASES.get(name.strip().lower())
    if key is None:
        valid = ', '.join(sorted(set(CANNED_FILTER_ALIASES.values())))
        raise ValueError(
            f"Unknown filter '{name}' for -v/--invert. Valid filters: {valid}"
        )
    return key


def get_table_columns(db_path: str = DB_PATH, table: str = TABLE_NAME) -> List[str]:
    """Return the real column names of ``table``.

    Raises:
        sqlite3.Error: on DB error (caller decides how to present it).
    """
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        cursor = conn.execute(f'PRAGMA table_info("{table}")')
        return [row[1] for row in cursor.fetchall()]
    finally:
        conn.close()


def resolve_field_name(field: str, valid_columns: List[str]) -> str:
    """Resolve a user-supplied field name to its exact column name.

    Case-insensitive and tolerant of spaces vs. underscores.

    Raises:
        ValueError: if no column matches.
    """
    normalized = field.strip().replace(' ', '_').lower()
    for col in valid_columns:
        if col.lower() == normalized:
            return col
    raise ValueError(
        f"Unknown field '{field}'. Valid fields: {', '.join(valid_columns)}"
    )


# ---------------------------------------------------------------------------
# Query building (M2)
# ---------------------------------------------------------------------------
def _field_condition(col: str, value: str, exact: bool) -> Tuple[str, str]:
    """Build a single ``-f/--field`` condition and its bound parameter."""
    if exact:
        return f'"{col}" = ?', value
    return f'"{col}" LIKE ?', f'%{value}%'


def _any_field_condition(valid_columns: List[str], value: str,
                         exact: bool) -> Tuple[str, List[str]]:
    """Build a single ``-a/--any`` condition (OR'd across all columns)."""
    op = '=' if exact else 'LIKE'
    bound = value if exact else f'%{value}%'
    clause = '(' + ' OR '.join(f'"{c}" {op} ?' for c in valid_columns) + ')'
    return clause, [bound] * len(valid_columns)


def build_query(where_clauses=None, invert_clauses=None, invert_all=False,
                field_searches=None, any_field_searches=None, exact_match=False,
                sort_field=None, sort_direction=None, db_path=DB_PATH,
                select_cols='"Name"', include_order=True):
    """Build a dynamic SQL query and its bound parameters.

    The model: a set of "precondition" conditions are always AND'd together
    untouched (defining a working universe T); optionally a second group is
    AND'd internally and wrapped in NOT(...) before being AND'd on, giving
    T - A.

    Args:
        where_clauses: WHERE_CLAUSES keys applied as preconditions.
        invert_clauses: WHERE_CLAUSES keys AND'd together then negated as a
            group (what `-v FILTER` builds). Mutually exclusive with invert_all.
        invert_all: bare `-v`. Moves where_clauses, field_searches and
            any_field_searches into one group that is AND'd and negated as a
            whole. Mutually exclusive with invert_clauses.
        field_searches: list of (field, value) from -f/--field.
        any_field_searches: list of values from -a/--any (each OR'd across all
            columns).
        exact_match: if True, -f/-a use equality instead of LIKE substring.
        sort_field: column to sort by (resolved against the real schema).
        sort_direction: 'ASC' or 'DESC'; defaults to DESC for Installed_Size,
            ASC otherwise.
        db_path: used only for the schema lookup.
        select_cols: the SELECT list (default just Name). Pass e.g.
            'SUM("Installed_Size")' to reuse the same WHERE for totals.
        include_order: append ORDER BY when True (skip it for aggregates).

    Returns:
        (query, params) — query has '?' placeholders, params is the bind list.

    Raises:
        ValueError: on unknown field/filter names, or invert_all with nothing
            to invert.
    """
    base_conditions: List[str] = []
    base_params: List[str] = []
    invert_group: List[str] = []
    invert_params: List[str] = []

    valid_columns = None
    if field_searches or any_field_searches or (sort_field and include_order):
        try:
            valid_columns = get_table_columns(db_path)
        except sqlite3.Error as e:
            raise ValueError(f"Could not read database schema: {e}")

    if invert_all:
        # Everything given is AND'd internally then negated as one unit.
        if where_clauses:
            invert_group.extend(
                WHERE_CLAUSES[c] for c in where_clauses if c in WHERE_CLAUSES
            )
        for field, value in (field_searches or []):
            clause, param = _field_condition(
                resolve_field_name(field, valid_columns), value, exact_match
            )
            invert_group.append(clause)
            invert_params.append(param)
        for value in (any_field_searches or []):
            clause, params = _any_field_condition(valid_columns, value, exact_match)
            invert_group.append(clause)
            invert_params.extend(params)

        if not invert_group:
            raise ValueError(
                "--invert has nothing to invert — combine it with at least one "
                "filter (-m/-o/-e/-d/-n/-k/--has-note/--no-note/-f/-a), or use "
                "-v FILTER to invert just one specific filter"
            )
    else:
        # Preconditions (untouched); only invert_clauses gets negated.
        if where_clauses:
            base_conditions.extend(
                WHERE_CLAUSES[c] for c in where_clauses if c in WHERE_CLAUSES
            )
        for field, value in (field_searches or []):
            clause, param = _field_condition(
                resolve_field_name(field, valid_columns), value, exact_match
            )
            base_conditions.append(clause)
            base_params.append(param)
        for value in (any_field_searches or []):
            clause, params = _any_field_condition(valid_columns, value, exact_match)
            base_conditions.append(clause)
            base_params.extend(params)
        if invert_clauses:
            invert_group.extend(
                WHERE_CLAUSES[c] for c in invert_clauses if c in WHERE_CLAUSES
            )

    query = f'SELECT {select_cols} FROM {TABLE_NAME}'

    all_clauses = list(base_conditions)
    if invert_group:
        all_clauses.append('NOT (' + ' AND '.join(invert_group) + ')')
    if all_clauses:
        query += ' WHERE ' + ' AND '.join(all_clauses)

    params = base_params + invert_params

    if include_order:
        sort_col = resolve_field_name(sort_field, valid_columns) if sort_field else NAME_FIELD
        direction = sort_direction or ('DESC' if sort_col == SIZE_FIELD else 'ASC')
        query += f' ORDER BY "{sort_col}" {direction}'

    return query, params


# ---------------------------------------------------------------------------
# Execution (M4)
# ---------------------------------------------------------------------------
def _passes_notes_filter(name: str, notes_filter: Optional[str],
                         noted: Optional[set]) -> bool:
    if notes_filter == 'has_note':
        return name in noted
    if notes_filter == 'no_note':
        return name not in noted
    return True


def iter_names(query: str, params=None, notes_filter: Optional[str] = None,
               db_path: str = DB_PATH) -> Iterator[str]:
    """Yield package names from ``query``, applying the notes filter in Python.

    The noted-package set is fetched once up front, not once per row.
    """
    noted = get_packages_with_notes() if notes_filter else None
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        cursor = conn.execute(query, params or [])
        for row in cursor:
            name = row[0]
            if _passes_notes_filter(name, notes_filter, noted):
                yield name
    finally:
        conn.close()


def compute_total_size(query_kwargs: dict, notes_filter: Optional[str],
                       db_path: str = DB_PATH) -> int:
    """Sum Installed_Size over the filtered package set (B2).

    Without a notes filter this is a single SUM in SQL. With one, we fetch
    (name, size) and sum in Python — avoiding a giant `IN (...)` that would
    blow past SQLite's bound-variable limit on large systems.
    """
    if notes_filter:
        query, params = build_query(
            **query_kwargs,
            select_cols='"Name", "Installed_Size"',
            include_order=False,
        )
        noted = get_packages_with_notes()
        total = 0
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            for name, size in conn.execute(query, params):
                if _passes_notes_filter(name, notes_filter, noted):
                    total += size or 0
        finally:
            conn.close()
        return total

    query, params = build_query(
        **query_kwargs, select_cols='SUM("Installed_Size")', include_order=False
    )
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        row = conn.execute(query, params).fetchone()
        return row[0] or 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Query pacman package database with flexible filtering and sorting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-m", "--foreign", action="store_true", help="only foreign packages")
    parser.add_argument("-o", "--orphans", action="store_true", help="only orphan packages")
    parser.add_argument("-e", "--explicit", action="store_true", help="only explicitly installed packages")
    parser.add_argument("-d", "--deps", action="store_true", help="only dependency packages")
    parser.add_argument("-n", "--notadep", action="store_true", help="not a dependency package")
    parser.add_argument("-k", "--notoptdep", action="store_true", help="not an optional dependency package")
    parser.add_argument("--has-note", action="store_true", help="only packages that have a user note")
    parser.add_argument("--no-note", action="store_true", help="only packages without a user note")

    parser.add_argument(
        "-f", "--field", nargs=2, metavar=("FIELD", "VALUE"), action="append",
        dest="field_searches",
        help="only packages where FIELD matches VALUE (repeatable; e.g. -f Name vim)",
    )
    parser.add_argument(
        "-a", "--any", metavar="VALUE", action="append", dest="any_field_searches",
        help="only packages where ANY field matches VALUE (repeatable)",
    )
    parser.add_argument(
        "-x", "--exact-match", action="store_true",
        help="use exact equality instead of substring matching for -f and -a",
    )

    parser.add_argument(
        "-s", "--size", "--sort-by", nargs="?", const=SIZE_FIELD, default=None,
        metavar="FIELD", dest="sort_field",
        help=f"sort by FIELD (default: Name; bare -s/--sort-by means {SIZE_FIELD})",
    )
    direction_group = parser.add_mutually_exclusive_group()
    direction_group.add_argument("--asc", action="store_true", help="sort ascending")
    direction_group.add_argument("--desc", action="store_true", help="sort descending")

    parser.add_argument("-t", "--totalsize", action="store_true", help="total size of the (filtered) packages")
    parser.add_argument(
        "-v", "--invert", nargs="?", const="__ALL__", default=None, action="append",
        metavar="FILTER", dest="invert_args",
        help="invert the result. Bare -v inverts everything else you specified. "
             "-v FILTER (repeatable) inverts only that one canned filter, leaving "
             "every other active filter as a precondition. FILTER is one of: "
             "foreign, orphan, explicit, deps, notadep, notoptdep (or m/o/e/d/n/k)",
    )

    args = parser.parse_args()

    ensure_cache_db()

    where_filters = []
    if args.foreign:
        where_filters.append('foreign')
    if args.orphans:
        where_filters.append('orphan')
    if args.explicit:
        where_filters.append('explicit')
    if args.deps:
        where_filters.append('deps')
    if args.notadep:
        where_filters.append('notadep')
    if args.notoptdep:
        where_filters.append('notoptdep')

    sort_direction = 'ASC' if args.asc else ('DESC' if args.desc else None)

    invert_all = False
    invert_clauses = None
    if args.invert_args:
        if '__ALL__' in args.invert_args:
            if len(args.invert_args) > 1:
                print(
                    "Error: combine -v either bare (invert everything) or with "
                    "specific filter names, not both.",
                    file=sys.stderr,
                )
                sys.exit(1)
            invert_all = True
        else:
            try:
                invert_clauses = [
                    resolve_canned_filter_name(name) for name in args.invert_args
                ]
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            where_filters = [f for f in where_filters if f not in invert_clauses]

    notes_filter = None
    if args.has_note:
        notes_filter = 'has_note'
    elif args.no_note:
        notes_filter = 'no_note'

    query_kwargs = dict(
        where_clauses=where_filters or None,
        invert_clauses=invert_clauses,
        invert_all=invert_all,
        field_searches=args.field_searches,
        any_field_searches=args.any_field_searches,
        exact_match=args.exact_match,
        sort_field=args.sort_field,
        sort_direction=sort_direction,
    )

    try:
        if args.totalsize:
            total = compute_total_size(query_kwargs, notes_filter)
            print(bytes_to_human(total))
            return

        query, params = build_query(**query_kwargs)
        for name in iter_names(query, params, notes_filter):
            print(name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except BrokenPipeError:
        # A downstream reader (head, less, fzf) closed the pipe early. Redirect
        # stdout to devnull so the interpreter's shutdown flush doesn't raise
        # again, then exit quietly.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)


if __name__ == "__main__":
    main()
