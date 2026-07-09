# How flags work

There are three entry points, `pacfz`, `pacq`, and `src/lib/list_packages.py`, and each flag belongs to exactly one
of them. This doc says who owns what and how a flag actually travels from the command line to a result.

## The three layers

```
pacfz  (bash, interactive: fzf + preview + notes)
pacq   (bash, non-interactive: prints results and exits)
    |
    v
list_packages.py  (Python, argparse - the actual query engine)
```

`list_packages.py` is the single source of truth for every *filter*, *sort*, and *size* flag: what it's called, what
it does, and whether it's even valid. Both bash wrappers exist to add behavior Python doesn't have (fzf itself, the
live preview, notes editing) and otherwise just get out of the way.

## Flag ownership

**Owned by `list_packages.py` (argparse), forwarded untouched by both wrappers:**

`-m/--foreign`, `-o/--orphans`, `-e/--explicit`, `-d/--deps`, `-n/--notadep`, `-k/--notoptdep`, `--has-note`,
`--no-note`, `-f/--field`, `-a/--any`, `-x/--exact-match`, `-v/--invert`, `-s/--sort-by/--size`, `--asc`, `--desc`,
`-t/--totalsize`.

These are all defined once, in `main()`'s `argparse.ArgumentParser`. Neither wrapper knows or cares what any of these
actually mean, they just pass them straight through and let Python validate and act on them.

**Owned by `pacfz` (bash-only, never reach Python as filter flags):**

- `--exact`, tells *fzf* to use exact matching in the picker itself. Stripped out of `PYTHON_ARGS` before the query
  even runs; only affects the `fzf_opts` built in `show_interactive()`.
- `--hide-notes`, tells `preview_item.py` to skip opening the notes DB entirely. Stripped from `PYTHON_ARGS`, then
  forwarded separately as a literal `--hide-notes` suffix on the preview/picker command strings.
- `-D <pkg> [note|-d]`, routed straight to `note_manager.py`, never touches `list_packages.py` at all.
- `--notes-list`, same story, routed to `note_manager.py --list`.
- `-h/--help`, prints `pacfz`'s own `show_usage()` (bash), not argparse's.
- `-r/--refresh`, rebuilds the cache DB (`create_db.py`) and exits; never reaches the query engine.
- `--print-selection`, runs the exact same interactive session but prints the bare selected name instead of a
  rendered preview. This is what the shell key bindings (`key-bindings.bash`/`key-bindings.zsh`) call under the hood,
  see `docs/internals.md` for the full story.

**Owned by `pacq` (bash-only):**

- `-h/--help`, same idea as `pacfz`: intercepted before Python ever sees it, prints `pacq`'s own `show_usage()`.
- Everything else is `exec python "$SCRIPT_LIST" "$@"`, pacq does no filtering of its own argv at all.

## How dispatch actually works

### `pacq`, forward everything

```bash
for arg in "$@"; do
  case "$arg" in -h|--help) show_usage; exit 0 ;; esac
done
exec python "$SCRIPT_LIST" "$@"
```

`pacq` only ever intercepts `-h/--help`. Anything else, valid or not, goes straight to argparse, which is what
actually decides whether it's a real flag in the first place.

### `pacfz`, bash-only flags first, then forward

`pacfz` needs to do more before the query even runs (strip `--exact`/`--hide-notes` into local state, detect `-t`
anywhere in argv, decide between `show_total`, `show_interactive`, or a bash-only command like `-r`/`-D`). Its
`case $1` only special-cases flags that change *bash's own* control flow:

```bash
case $1 in
  -h|--help)      show_usage; exit 0 ;;
  -r|--refresh)   create_database; exit 0 ;;
  -D)             python "$SCRIPT_NOTES" "$@"; exit 0 ;;
  --notes-list)   python "$SCRIPT_NOTES" --list; exit 0 ;;
  -*)
    # Anything else dash-prefixed: let list_packages.py decide if it's real.
    package_list=$(python "$SCRIPT_LIST" "${PYTHON_ARGS[@]}") || exit $?
    show_interactive
    exit 0
    ;;
  *) echo "Unknown option: $1"; show_usage; exit 1 ;;
esac
```

There's no whitelist of filter/sort flag names in bash anymore. A flag pacfz doesn't need to special-case (which is
every filter/sort/size flag, plus `--exact`/`--hide-notes`, which were already stripped into `PYTHON_ARGS` before
this point) just falls into the `-*` arm and gets forwarded as-is. If argparse rejects it, `|| exit $?` stops pacfz
before it opens fzf on an empty list, it doesn't silently fall through to something weird.

## Shared help text

The Filter/Sort/Size flag descriptions used to be copy-pasted, word for word, into both `pacfz` and `pacq`'s
`show_usage()` functions. Now they only exist once, as `SHARED_HELP` in `list_packages.py`, printed on demand via a
hidden flag:

```
python "$SCRIPT_LIST" --print-help
```

`--print-help` is a real (but `argparse.SUPPRESS`-hidden) argument. It short-circuits `main()` before
`ensure_cache_db()` runs, so it still works even on a machine with no cache yet. Both wrappers' `show_usage()`
functions call it and print their own bash-only sections (Notes, Display Options, `-h`/`-r`, the interactive-picker
hint) around it.

One caveat worth knowing: since it's a real argparse flag, `pacq --print-help` invoked directly bypasses `pacq`'s own
usage wrapper and just dumps the shared block on its own. Harmless, but worth remembering if you ever go looking for
where `-h` output "really" comes from.

## Adding a new flag

- **New filter/sort/size flag** (something that changes what rows come back or their order): add it to
  `list_packages.py`'s argparse spec, add its description to `SHARED_HELP`, and update `where_filters`/`query_kwargs`
  in `main()`. There's nothing to touch in `pacfz` or `pacq`, the `-*` catch-all and `exec ... "$@"` already forward
  it, and `--print-help` already advertises it for you.
- **New bash-only flag** (changes fzf behavior, preview rendering, or note handling, not what rows are returned): add
  a case arm in `pacfz`'s first-pass loop (to strip it out of `PYTHON_ARGS` if Python shouldn't see it) and document
  it in `pacfz`'s `show_usage()` directly, since it has no Python-side equivalent to pull from.
