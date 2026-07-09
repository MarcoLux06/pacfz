# Architecture overview

This is the "why is it shaped this way" doc, one level up from `docs/internals.md`, which covers specific hidden
flags, and `docs/flags.md`, which covers exactly how a flag travels through the system. Read this first if you're
new to the codebase, the other two make more sense once you have this picture.

## Three front-ends, one shared engine

```
pacfz    (bash)  interactive, fzf + live preview + notes
pacq     (bash)  non-interactive, prints results and exits
pactui   (Python, Textual)  full-screen TUI, experimental
    \       |        /
     \      |       /
      src/lib/*.py  (the actual query engine and data layer)
```

All three front-ends are genuinely thin. None of them contain filtering logic, SQL, or parsing of their own, that
all lives in `src/lib/`, and every front-end just calls into it. `pacfz` and `pacq` do it by shelling out to Python
scripts and reading stdout/stderr; `pactui` does it with a real Python import, since it's Python itself. The point
of keeping it this way is that a filter or bug fix in `src/lib/list_packages.py` is automatically correct everywhere
at once, nobody has to remember to also fix `pacq`, or `pactui`, because neither of them re-implements anything.

## `src/lib/` isn't a real Python package, on purpose

There's no `__init__.py`, and the modules import each other directly (`from config import cache_db_path`, not
`from lib.config import cache_db_path`). This is a deliberate choice, not an oversight, both `pacfz`/`pacq` (as
subprocesses) and `pactui` (running the actual `src/pactui` file directly) need to add `lib/`'s directory straight
onto `sys.path` at runtime, since the same code has to work both from a bare git checkout (`src/lib/` sitting next
to the launchers) and from an installed package (`/usr/share/pacfz/lib/`), and those two cases only differ in
*which* directory gets added to `sys.path`, not in how the modules refer to each other. Making `lib/` a real package
would mean choosing one fixed import path (`lib.config`, say) and then having to fake up a parent package at the
other location too, for a benefit that's mostly cosmetic. Every bash launcher's own comment block explains this
same resolution logic (own directory first, `/usr/share/pacfz/lib` as the installed fallback), it's worth reading
once in `src/pacfz`'s header if this is new to you.

## The two databases

Two separate SQLite files, both resolved through `config.py`, both overridable via environment variable, and both
outliving a `pacman -R pacfz` uninstall on purpose, they're your data, not the package's:

- **The package cache** (`PACFZ_DB_PATH`, default `$XDG_CACHE_HOME/pacman_packages.db`). Built from `pacman -Qi` /
  `pacman -Qqm` by `create_db.py`, rebuilt atomically (built to a temp file, `PRAGMA integrity_check`'d, then
  `os.replace()`'d into place), so a concurrent reader, like the fzf preview pane mid-refresh, only ever sees a
  complete old file or a complete new one, never a half-written one.
- **User notes** (`PACFZ_NOTES_DB_PATH`, default `$XDG_DATA_HOME/pacfz/user_data.db`). A separate, much smaller DB,
  deliberately decoupled from the cache so rebuilding the package cache (which happens often, cheaply) never risks
  the notes you've actually written (which happen rarely, and would be annoying to lose).

Every module that touches either database resolves its path once, at import time (`DB_PATH = cache_db_path()`),
rather than on every call. This is a real, known trade-off, not an accident, it makes the common case (one process,
one database, for its whole lifetime) simple, at the cost of a genuine footgun: calling a function without passing
`db_path=` explicitly silently falls back to whatever `DB_PATH` resolved to when the module was first imported, not
whatever the environment says *right now*. Every test that needs a different database passes `db_path=` explicitly
for exactly this reason, and any new code that wants to point at a specific database should do the same rather than
relying on the module-level default.

## Data layer never touches the terminal directly

`src/lib/`'s modules never call `print()` for user-facing output, parse `sys.argv` outside of their own `main()`
entry point, or make assumptions about being run interactively. `list_packages.py`'s `build_query()` returns a SQL
string and a params list; it doesn't execute anything or print anything itself. `create_db.py`'s `create_database()`
takes an explicit `verbose` flag rather than checking some global state. This is what makes the three-front-ends
setup actually work in practice, not just in theory, `pactui` needs the query *results* as Python data structures to
put in a table widget, not formatted text meant for a terminal, and that's exactly what the data layer already
hands back.

## Where output formatting actually lives

- **Package metadata rendering** (colors, field order, the `Note` line) lives in `preview_item.py`, in one shared
  helper (`_formatted_line_for()`) underneath two different entry points: `print_line()`, which `pacfz`'s CLI
  preview uses, and `render_preview()`, which builds the same content as one string for `pactui`'s widget. `pacq`
  doesn't use either, deliberately, its whole point is plain, scriptable name-per-line output. Neither of the other
  two front-ends formats package data itself, both go through this one module.
- **CLI help text** for the shared filter/sort/size flags lives once, in `list_packages.py`'s `SHARED_HELP`, printed
  via the hidden `--print-help` flag (see `docs/flags.md`). Bash-only flags (notes, `-r`, `--exact`) get documented
  directly in each wrapper's own `show_usage()`, since they have no Python-side equivalent to pull from.

## Security-relevant bits worth knowing up front

Package metadata (descriptions, packager strings, and so on) ultimately comes from whatever a package's own build
script put into `pacman -Qi`'s output, not something pacfz controls or can fully trust. `sanitize_terminal_value()`
in `preview_item.py` strips ANSI/OSC escape sequences and control characters from every value before it's ever
printed, specifically so a hostile package couldn't inject terminal escape codes (title spoofing, and worse) into
your session just by being installed. This runs unconditionally inside `format_line()`, not as an opt-in step, any
new code path that prints a raw field value should go through this too.
