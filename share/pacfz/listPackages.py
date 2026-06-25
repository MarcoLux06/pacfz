import sqlite3
import sys
import os
import argparse

from previewItem import bytes_to_human

DB_PATH = os.path.expanduser('~/.cache/pacman_packages.db')
NOTES_DB_PATH = os.path.expanduser('~/.local/share/pacfz/user_data.db')
TABLE_NAME = 'packages'
NAME_FIELD = 'Name'
SIZE_FIELD = 'Installed_Size'
INSTALL_REASON_FIELD = 'Install_Reason'
FOREIGN_FIELD = 'is_foreign'
REQUIRED_BY_FIELD = 'Required_By'
OPT_REQUIRED_BY_FIELD = 'Optional_For'

# WHERE clause definitions
WHERE_CLAUSES = {
    'foreign': f'{FOREIGN_FIELD} = 1',
    'orphan': f"{INSTALL_REASON_FIELD} = 'Installed as a dependency for another package' AND {REQUIRED_BY_FIELD} IS 'None'",
    'explicit': f"{INSTALL_REASON_FIELD} = 'Explicitly installed'",
    'deps': f"{INSTALL_REASON_FIELD} = 'Installed as a dependency for another package'",
    'notadep': f"{REQUIRED_BY_FIELD} IS 'None'",
    'notoptdep': f"{OPT_REQUIRED_BY_FIELD} IS 'None'",
}

# Accepted spellings for each canned filter, used to resolve -v/--invert's
# FILTER argument. Maps every short letter and long flag spelling (with or
# without dashes) to its WHERE_CLAUSES key.
CANNED_FILTER_ALIASES = {
    'm': 'foreign', 'foreign': 'foreign',
    'o': 'orphan', 'orphan': 'orphan', 'orphans': 'orphan',
    'e': 'explicit', 'explicit': 'explicit',
    'd': 'deps', 'deps': 'deps',
    'n': 'notadep', 'notadep': 'notadep',
    'k': 'notoptdep', 'notoptdep': 'notoptdep',
}


def resolve_canned_filter_name(name):
    """
    Resolve a user-supplied -v/--invert FILTER argument to its WHERE_CLAUSES key.

    Accepts either the short letter (m, o, e, d, n, k) or the long flag spelling
    (foreign, orphan/orphans, explicit, deps, notadep, notoptdep), case-insensitive.

    Raises:
        ValueError: if the name doesn't match any canned filter
    """
    key = CANNED_FILTER_ALIASES.get(name.strip().lower())
    if key is None:
        valid = ', '.join(sorted(set(CANNED_FILTER_ALIASES.values())))
        raise ValueError(f"Unknown filter '{name}' for -v/--invert. Valid filters: {valid}")
    return key


TOTAL_SIZE = f'''
            Select SUM(Installed_Size)
            FROM {TABLE_NAME}
        '''


def get_table_columns(db_path=DB_PATH, table=TABLE_NAME):
    """
    Return the list of actual column names in the packages table.

    Used to validate user-supplied field names for -f/--field and to build
    the -a/--any wildcard search, instead of trusting a hardcoded list.

    Raises:
        sqlite3.Error: on DB error (caller decides how to present this)
    """
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        cursor = conn.cursor()
        cursor.execute(f'PRAGMA table_info("{table}")')
        return [row[1] for row in cursor.fetchall()]
    finally:
        conn.close()


def resolve_field_name(field, valid_columns):
    """
    Resolve a user-supplied field name to its exact column name.

    Matching is case-insensitive and tolerant of spaces vs underscores, so
    'installed size', 'Installed_Size', and 'INSTALLED_SIZE' all resolve to
    the real 'Installed_Size' column.

    Raises:
        ValueError: if no column matches
    """
    normalized = field.strip().replace(' ', '_').lower()
    for col in valid_columns:
        if col.lower() == normalized:
            return col
    raise ValueError(f"Unknown field '{field}'. Valid fields: {', '.join(valid_columns)}")


def get_packages_with_notes() -> set:
    """
    Return the set of package names that have a user note.

    Opens the notes DB read-only. Returns an empty set if the DB doesn't
    exist yet or on any error — callers don't need to special-case this.
    """
    if not os.path.exists(NOTES_DB_PATH):
        return set()
    try:
        conn = sqlite3.connect(f'file:{NOTES_DB_PATH}?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM user_data')
        names = {row[0] for row in cursor.fetchall()}
        conn.close()
        return names
    except sqlite3.Error:
        return set()


def build_query(where_clauses=None, invert_clauses=None, invert_all=False,
                 field_searches=None, any_field_searches=None, exact_match=False,
                 sort_field=None, sort_direction=None, db_path=DB_PATH):
    """
    Build a dynamic SQL query based on provided WHERE and ORDER BY clauses.

    The model: there's a set of "precondition" conditions that are always AND'd
    together untouched (these define the working universe T), and optionally a
    second group of conditions that get AND'd together internally to form a set A,
    then wrapped in NOT(...) before being AND'd onto the preconditions. That gives
    T - A, where T is whatever the preconditions narrow things down to (the whole
    table if there are none) and A is just the named group — not the whole query.

    Args:
        where_clauses: list of WHERE_CLAUSES keys applied as preconditions — always
            AND'd in untouched, never part of what gets inverted.
        invert_clauses: list of WHERE_CLAUSES keys to AND together and then negate
            as a group (this is what -v FILTER, used with an explicit name, builds).
            Mutually exclusive with invert_all.
        invert_all: legacy/bare -v behavior. Moves where_clauses, field_searches,
            and any_field_searches ALL into a single group that's AND'd together and
            then wrapped in NOT(...) as a whole — i.e. T - A where A is everything
            given and T is the entire table. This is what -v with no FILTER argument
            does, preserved for backward compatibility. Mutually exclusive with
            invert_clauses.
        field_searches: list of (field, value) pairs from -f/--field; each becomes its
            own condition. In the default/scoped-invert case these are always
            preconditions (never inverted); under invert_all they're folded into the
            inverted group along with everything else. Field names are resolved
            against the real DB schema (case/space-insensitive).
        any_field_searches: list of values from -a/--any; each becomes a single
            condition that is true if ANY column matches that value (OR'd across
            columns). Follows the same precondition/invert_all placement as
            field_searches.
        exact_match: if True, -f/-a use exact equality instead of case-insensitive
            substring (LIKE) matching.
        sort_field: column to sort by, resolved against the real schema the same way
            -f/--field is (case/space-insensitive). Defaults to Name if not given.
        sort_direction: 'ASC' or 'DESC'. If not given, defaults to DESC when sorting by
            Installed_Size (preserving the historic bare -s behavior) and ASC for every
            other field — but an explicit --asc/--desc always overrides this default,
            regardless of which field is being sorted.
        db_path: only used to look up the schema when field_searches, any_field_searches,
            or sort_field are given.

    Returns:
        (query, params) tuple — query is the SQL string with '?' placeholders,
        params is the ordered list of values to bind.

    Raises:
        ValueError: if an unknown field/filter name is given, or invert_all is set
            with nothing at all to invert (which would otherwise silently return
            nothing).
    """
    base_conditions = []
    base_params = []
    invert_group = []
    invert_params = []

    valid_columns = None
    if field_searches or any_field_searches or sort_field:
        try:
            valid_columns = get_table_columns(db_path)
        except sqlite3.Error as e:
            raise ValueError(f"Could not read database schema: {e}")

    if invert_all:
        # Legacy behavior: everything given gets AND'd together internally, then
        # the whole thing is negated as one unit (T - A over the entire table).
        if where_clauses:
            invert_group.extend(WHERE_CLAUSES[c] for c in where_clauses if c in WHERE_CLAUSES)

        if field_searches:
            for field, value in field_searches:
                col = resolve_field_name(field, valid_columns)
                if exact_match:
                    invert_group.append(f'"{col}" = ?')
                    invert_params.append(value)
                else:
                    invert_group.append(f'"{col}" LIKE ?')
                    invert_params.append(f'%{value}%')

        if any_field_searches:
            for value in any_field_searches:
                if exact_match:
                    invert_group.append('(' + ' OR '.join(f'"{c}" = ?' for c in valid_columns) + ')')
                    invert_params.extend([value] * len(valid_columns))
                else:
                    invert_group.append('(' + ' OR '.join(f'"{c}" LIKE ?' for c in valid_columns) + ')')
                    invert_params.extend([f'%{value}%'] * len(valid_columns))

        if not invert_group:
            raise ValueError(
                "--invert has nothing to invert — combine it with at least one filter "
                "(-m/-o/-e/-d/-n/-k/--has-note/--no-note/-f/-a), or use -v FILTER to "
                "invert just one specific filter"
            )
    else:
        # Scoped behavior: where_clauses and all field/any searches are
        # preconditions (untouched, always AND'd in); only invert_clauses gets
        # AND'd together internally and then negated as its own group.
        if where_clauses:
            base_conditions.extend(WHERE_CLAUSES[c] for c in where_clauses if c in WHERE_CLAUSES)

        if field_searches:
            for field, value in field_searches:
                col = resolve_field_name(field, valid_columns)
                if exact_match:
                    base_conditions.append(f'"{col}" = ?')
                    base_params.append(value)
                else:
                    base_conditions.append(f'"{col}" LIKE ?')
                    base_params.append(f'%{value}%')

        if any_field_searches:
            for value in any_field_searches:
                if exact_match:
                    base_conditions.append('(' + ' OR '.join(f'"{c}" = ?' for c in valid_columns) + ')')
                    base_params.extend([value] * len(valid_columns))
                else:
                    base_conditions.append('(' + ' OR '.join(f'"{c}" LIKE ?' for c in valid_columns) + ')')
                    base_params.extend([f'%{value}%'] * len(valid_columns))

        if invert_clauses:
            invert_group.extend(WHERE_CLAUSES[c] for c in invert_clauses if c in WHERE_CLAUSES)

    query = f'SELECT {NAME_FIELD} FROM {TABLE_NAME}'

    all_clauses = list(base_conditions)
    if invert_group:
        all_clauses.append('NOT (' + ' AND '.join(invert_group) + ')')

    if all_clauses:
        query += ' WHERE ' + ' AND '.join(all_clauses)

    params = base_params + invert_params

    sort_col = resolve_field_name(sort_field, valid_columns) if sort_field else NAME_FIELD
    if sort_direction:
        direction = sort_direction
    else:
        direction = 'DESC' if sort_col == SIZE_FIELD else 'ASC'
    query += f' ORDER BY "{sort_col}" {direction}'

    return query, params


def query_db(query, params=None, output=True, notes_filter=None):
    # Fetch the noted-packages set once up front if needed, so we don't
    # hit the notes DB once per row. Returns an empty set when the DB is
    # absent, which makes 'has_note' yield nothing and 'no_note' pass all.
    noted = get_packages_with_notes() if notes_filter else None

    conn = None
    try:
        conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
        cursor = conn.cursor()

        cursor.execute(query, params or [])

        if output:
            for row in cursor:
                name = row[0]
                if noted is not None:
                    if notes_filter == 'has_note' and name not in noted:
                        continue
                    if notes_filter == 'no_note' and name in noted:
                        continue
                print(name)
        else:
            ary = []
            for row in cursor:
                name = row[0]
                if noted is not None:
                    if notes_filter == 'has_note' and name not in noted:
                        continue
                    if notes_filter == 'no_note' and name in noted:
                        continue
                ary.append(name)
            return ary
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            try:
                conn.close()
            except sqlite3.ProgrammingError as e:
                # Connection was already closed or invalid
                print(f"Database error: {e}", file=sys.stderr)
            except OSError as e:
                # File system error
                print(f"Warning: Failed to close database connection: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Query pacman package database with flexible filtering and sorting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Filter options
    parser.add_argument("-m", "--foreign", action="store_true", help="only foreign packages")
    parser.add_argument("-o", "--orphans", action="store_true", help="only orphan packages")
    parser.add_argument("-e", "--explicit", action="store_true", help="only explicitly installed packages")
    parser.add_argument("-d", "--deps", action="store_true", help="only dependency packages")
    parser.add_argument("-n", "--notadep", action="store_true", help="not a dependency package")
    parser.add_argument("-k", "--notoptdep", action="store_true", help="not an optional dependency package")
    parser.add_argument("--has-note", action="store_true", help="only packages that have a user note")
    parser.add_argument("--no-note", action="store_true", help="only packages without a user note")

    # Generic field search
    parser.add_argument(
        "-f", "--field", nargs=2, metavar=("FIELD", "VALUE"), action="append", dest="field_searches",
        help="only packages where FIELD matches VALUE (repeatable, AND-combined; e.g. -f Name vim)",
    )
    parser.add_argument(
        "-a", "--any", metavar="VALUE", action="append", dest="any_field_searches",
        help="only packages where ANY field matches VALUE (repeatable, AND-combined with everything else)",
    )
    parser.add_argument(
        "-x", "--exact-match", action="store_true",
        help="use exact equality instead of substring matching for -f/--field and -a/--any",
    )

    # Sort options
    parser.add_argument(
        "-s", "--size", "--sort-by", nargs="?", const=SIZE_FIELD, default=None,
        metavar="FIELD", dest="sort_field",
        help=f"sort by FIELD (default: Name; bare -s/--sort-by means {SIZE_FIELD}); "
             "FIELD is validated against the real DB schema the same way -f is",
    )
    direction_group = parser.add_mutually_exclusive_group()
    direction_group.add_argument(
        "--asc", action="store_true",
        help="sort ascending (applies to whichever field is being sorted)",
    )
    direction_group.add_argument(
        "--desc", action="store_true",
        help="sort descending (applies to whichever field is being sorted)",
    )

    # Special options
    parser.add_argument("-t", "--totalsize", action="store_true", help="total size of all packages")
    parser.add_argument(
        "-v", "--invert", nargs="?", const="__ALL__", default=None, action="append",
        metavar="FILTER", dest="invert_args",
        help="invert the result. Bare -v inverts everything else you specified "
             "(the original full-invert behavior). -v FILTER (repeatable) instead "
             "inverts only that one canned filter's condition, leaving every other "
             "active filter as an untouched precondition — e.g. '-e -v notadep "
             "-v notoptdep' means explicit packages where NOT(notadep AND notoptdep). "
             "FILTER is one of: foreign, orphan, explicit, deps, notadep, notoptdep "
             "(or their short letters m/o/e/d/n/k)",
    )

    args = parser.parse_args()

    # Handle total size separately
    if args.totalsize:
        result = query_db(TOTAL_SIZE, output=False)
        if result:
            print(bytes_to_human(result[0]))
        return

    # Build list of where clauses
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

    # Determine sort direction; argparse's mutually_exclusive_group already
    # guarantees at most one of these is set.
    sort_direction = 'ASC' if args.asc else ('DESC' if args.desc else None)

    # Resolve -v/--invert into either full-invert mode (bare -v, preserved for
    # backward compatibility) or scoped mode (-v FILTER, repeatable). In scoped
    # mode, any named filter moves out of where_filters (preconditions) and into
    # invert_clauses, even if its bare flag (e.g. -n) wasn't also passed.
    invert_all = False
    invert_clauses = None
    if args.invert_args:
        if '__ALL__' in args.invert_args:
            if len(args.invert_args) > 1:
                print(
                    "Error: combine -v either bare (invert everything) or with "
                    "specific filter names (e.g. -v notadep -v notoptdep), not both.",
                    file=sys.stderr,
                )
                sys.exit(1)
            invert_all = True
        else:
            try:
                invert_clauses = [resolve_canned_filter_name(name) for name in args.invert_args]
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            where_filters = [f for f in where_filters if f not in invert_clauses]

    # Determine notes filter (mutually exclusive; --has-note wins if both given)
    notes_filter = None
    if args.has_note:
        notes_filter = 'has_note'
    elif args.no_note:
        notes_filter = 'no_note'

    # Build and execute query
    try:
        query, params = build_query(
            where_filters if where_filters else None,
            invert_clauses=invert_clauses,
            invert_all=invert_all,
            field_searches=args.field_searches,
            any_field_searches=args.any_field_searches,
            exact_match=args.exact_match,
            sort_field=args.sort_field,
            sort_direction=sort_direction,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    query_db(query, params=params, notes_filter=notes_filter)


if __name__ == "__main__":
    main()
