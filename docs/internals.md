# pacfz internals

This covers flags and mechanisms that are deliberately absent from the public README, either because they're
implementation details other parts of pacfz already rely on internally, or because they're only useful while working
on pacfz itself. Nothing here is meant for end users, but if you're changing the codebase, this is where the "why
does this flag even exist" answers live.

This is a starting point, more will get added here as it comes up.

## Hidden and internal flags

### `list_packages.py --print-help`

Hidden via `argparse.SUPPRESS`. Prints the shared Filter/Sort/Size flag descriptions and exits. This is how `pacfz`
and `pacq`'s own `show_usage()` functions get their flag reference text without duplicating it in bash: both just
shell out to `list_packages.py --print-help` and print their own bash-only sections (Notes, Display Options, and so
on) around it. If you add a new filter/sort/size flag to `list_packages.py`'s argparse spec, its help text shows up
automatically in both `pacfz -h` and `pacq -h` through this, no bash changes needed. See `docs/flags.md` for the
full picture of how flags travel between the three entry points.

### `list_packages.py --no-description`

Also hidden via `argparse.SUPPRESS`. Suppresses the descriptive sentence that normally prints above
`-t`/`--totalsize`'s output (see `build_totalsize_description()`). `pacq` always passes this internally, since its
whole point is clean, scriptable output; `pacfz` never passes it, since the description is actually useful there.
Not something you'd ever type by hand.

### `note_manager.py --get`

Hidden via `argparse.SUPPRESS`. Prints a single package's note text to stdout, or nothing at all if it has none.
`preview_item.py` shells out to this internally to fetch the note shown in the preview pane. Worth distinguishing
from `notes_db.get_note()`, the actual Python function: this is the subprocess-callable CLI wrapper around it, for
callers like `preview_item.py` that only have a shell available, not a Python import path.

### `pacfz --print-selection`

Not hidden via argparse (it's bash-only, stripped out of `PYTHON_ARGS` before `list_packages.py` ever sees it), but
undocumented in `pacfz -h` and the public README, since it's not meant to be typed directly. It runs the exact same
interactive fzf session `pacfz` always does, same live preview pane, same ctrl-r rebuild binding, but the final step
prints the bare selected package name to stdout instead of piping the selection into `preview_item.py` for a
rendered preview.

This exists specifically to power the shell key bindings (`key-bindings.bash`/`key-bindings.zsh`): they call
`pacfz --print-selection`, capture its stdout, and splice the result into the shell's current input line. See
`show_interactive()` in `src/pacfz` for the branch that handles this.

### `create_db.py --quiet` / `--verbose`

Both are real, non-suppressed argparse flags with their own genuine `--help` text, but `create_db.py` isn't a
user-facing entry point (nothing ever tells a regular user to run it directly), so in practice these only ever get
invoked internally:

- `pacfz -r` (no flag) calls `create_db.py` with neither flag set: prints only the summary block (packages inserted,
  foreign packages marked).
- `pacfz -r --verbose` calls `create_db.py --verbose`: additionally prints INFO-level logs and a sample of the
  packages that were just inserted.
- `pacq -r` and the interactive picker's ctrl-r binding always call `create_db.py --quiet`: no output at all.

`--quiet` and `--verbose` are mutually exclusive at the argparse level (see `create_db.py`'s `verbosity_group`).
There's no separate flag string for the "default, not quiet, not verbose" case, that's just what happens when
neither flag is passed.
