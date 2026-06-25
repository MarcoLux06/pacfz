# pacfz

A fast, [fzf](https://github.com/junegunn/fzf)-powered interactive browser for your installed `pacman` packages. Filter by foreign/orphan/explicit/dependency status, search any field, sort by size, attach personal notes to packages, and preview full package details before picking one.

## Features

- Interactive fuzzy search over every installed package
- Canned filters for foreign (AUR), orphan, explicit, and dependency packages
- Generic field search (`-f`) and a cross-field wildcard search (`-a`), each with substring or exact matching
- Result inversion (`-v`) so any combination of filters can be flipped
- Sort by name or installed size
- Total installed size at a glance
- Personal per-package notes, shown in the preview pane and filterable on their own
- Colorized preview pane with full `pacman -Qi`-style detail
- A local SQLite cache so every query is instant; rebuild it on demand after installs/removals
- Ships with `pacq`, a non-interactive sibling for scripts and pipelines — same filters, sorting, and search, just prints names with no `fzf` involved

## Requirements

- Arch Linux, or another pacman-based distro
- `pacman`
- `python3` (standard library only — `sqlite3`, `argparse`, `subprocess`, etc.)
- `fzf`
- `bash`

## Installation

1. Put the Python scripts in `~/.local/share/pacfz/`:
   - `listPackages.py`
   - `previewItem.py`
   - `noteManager.py`
   - `createDB.py`
2. Put `pacfz` and `pacq` somewhere on your `PATH` and make both executable: `chmod +x pacfz pacq`
3. Build the initial package cache: `pacfz -r`

## How it fits together

- **`createDB.py`** runs `pacman -Qi` (and `pacman -Qqm` to identify foreign packages) once and caches the result as a SQLite database at `~/.cache/pacman_packages.db`. This cache is what makes every other command instant. Re-run it with `pacfz -r` / `pacfz --refresh` whenever you install or remove packages.
- **`listPackages.py`** queries that cache and prints matching package names, applying whatever filters, sort order, and field searches you passed.
- **`pacfz`** (the bash entry point) pipes that list into `fzf` for interactive fuzzy selection.
- **`previewItem.py`** renders the colorized detail panel for whichever package is currently highlighted in `fzf`.
- **`noteManager.py`** manages a second, independent SQLite database at `~/.local/share/pacfz/user_data.db` holding your personal per-package notes. It's separate from the pacman cache, so your notes survive a `--refresh`.
- **`pacq`** is a thin non-interactive wrapper around the same `listPackages.py` — same filters, sorting, and search flags, just printed one per line with no `fzf` step. Useful for scripts, pipelines, and shell completions.

## Usage

```
pacfz [OPTIONS]
```

Run with no arguments to list every installed package and drop straight into the interactive picker.

### Filters

All filters below combine with each other using AND. `-f`/`-a` use case-insensitive substring matching by default.

| Flag                        | Meaning                                                                                                                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `-m`, `--foreign`           | only foreign (AUR) packages                                                                                                                                                                                        |
| `-o`, `--orphans`           | only orphans — dependency-installed, nothing currently requires them                                                                                                                                               |
| `-e`, `--explicit`          | only explicitly installed packages                                                                                                                                                                                 |
| `-d`, `--deps`              | only dependency-installed packages                                                                                                                                                                                 |
| `-n`, `--notadep`           | packages that nothing depends on                                                                                                                                                                                   |
| `-k`, `--notoptdep`         | packages that nothing optionally depends on                                                                                                                                                                        |
| `--has-note`                | only packages that have a note                                                                                                                                                                                     |
| `--no-note`                 | only packages without a note                                                                                                                                                                                       |
| `-f`, `--field FIELD VALUE` | only packages where `FIELD` matches `VALUE` (repeatable, AND-combined)                                                                                                                                             |
| `-a`, `--any VALUE`         | only packages where _any_ field matches `VALUE` (repeatable, AND-combined)                                                                                                                                         |
| `-x`, `--exact-match`       | use exact equality instead of substring matching for `-f`/`-a`                                                                                                                                                     |
| `-v`, `--invert [FILTER]`   | bare `-v` inverts the entire combined result (applied last, after everything else). `-v FILTER` (repeatable) instead inverts only that one canned filter, leaving every other active filter untouched — see below. |

`-f` validates `FIELD` against the database's real columns (case- and space-insensitive — `"installed size"`, `Installed_Size`, and `INSTALLED_SIZE` are all the same field). An unrecognized field name fails with the full list of valid fields rather than silently matching nothing.

Available fields: `Name`, `Version`, `Description`, `Architecture`, `URL`, `Licenses`, `Groups`, `Provides`, `Depends On`, `Optional Deps`, `Required By`, `Optional For`, `Conflicts With`, `Replaces`, `Installed Size`, `Packager`, `Build Date`, `Install Date`, `Install Reason`, `Install Script`, `Validated By`, `is foreign`.

### Bare `-v` vs scoped `-v FILTER`

Think of the filters you give as defining a set A, drawn from the universe T of every installed package. Without `-v`, you get A itself. Bare `-v` gives you the complement T − A, where A is the intersection of _everything_ you specified — including `-e`. That's mathematically correct, but it can surprise you: `pacfz -e -n -k -v` doesn't mean "explicit packages that fail the other two checks." By De Morgan's law it expands to "NOT explicit OR Required By isn't None OR Optional For isn't None," which lets through any package — explicit or not — that has _anything_ in either field, because failing just one of the three AND'd conditions is enough to satisfy the negation.

`-v FILTER` fixes this by letting you say which filters belong in A and which stay outside it as fixed preconditions defining T. `pacfz -e -v notadep -v notoptdep` keeps `-e` as a precondition and only folds `notadep`/`notoptdep` into A, giving you `explicit AND NOT(notadep AND notoptdep)` — i.e. explicit packages where Required By or Optional For isn't `None`. `FILTER` accepts the long name (`foreign`, `orphan`, `explicit`, `deps`, `notadep`, `notoptdep`) or the matching short letter (`m`, `o`, `e`, `d`, `n`, `k`); naming a filter this way activates its condition even if you don't also pass its bare flag. This scoping currently only covers the six canned filters above — `-f`/`-a`/`--has-note`/`--no-note` always stay outside A regardless of which `-v` form you use, except under bare `-v`, which (for backward compatibility) folds everything — canned filters and `-f`/`-a` alike — into a single inverted group.

### Sorting

| Flag                      | Meaning                                                                                                                                                                                                          |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-s`, `--sort-by [FIELD]` | sort by `FIELD` (validated against the schema, same as `-f`). Bare `-s` (no value) means `Installed_Size` — the legacy shorthand, also still spelled `--size`. With no `-s` at all, the default field is `Name`. |
| `--asc`                   | sort ascending, whichever field is active                                                                                                                                                                        |
| `--desc`                  | sort descending, whichever field is active                                                                                                                                                                       |

`--asc` and `--desc` are mutually exclusive — passing both is a clear error rather than one silently winning. Without either, the default direction is descending when sorting by `Installed_Size` (matching the historic bare `-s` behavior) and ascending for every other field, including the default `Name`.

### Special / utility

| Flag                | Meaning                                                                          |
| ------------------- | -------------------------------------------------------------------------------- |
| `-t`, `--totalsize` | print the total installed size of every package (does not respect other filters) |
| `-r`, `--refresh`   | rebuild the package cache from `pacman -Qi`                                      |
| `-h`, `--help`      | show built-in help                                                               |

### Notes

| Flag              | Meaning                            |
| ----------------- | ---------------------------------- |
| `-D <pkg> <note>` | set or update a note for `<pkg>`   |
| `-D <pkg> -d`     | delete the note for `<pkg>`        |
| `--notes-list`    | list every package that has a note |

### Display (interactive picker only)

| Flag           | Meaning                                       |
| -------------- | --------------------------------------------- |
| `--exact`      | use fzf's exact (non-fuzzy) matching mode     |
| `--hide-notes` | don't fetch or show notes in the preview pane |

While the picker is open, **Ctrl-R** rebuilds the package cache (`createDB.py --quiet`) and refreshes the visible list with the same filters you launched with — handy after a `pacman -Syu` in another terminal, without backing out of `fzf` and re-running `pacfz`. There's no static header taking up space; once the refresh completes, the header changes to `✓ cache refreshed at HH:MM:SS`, so pressing Ctrl-R twice in the same session is visibly distinguishable instead of showing the same message both times. This relies on fzf's `transform-header` action, which needs a fairly recent fzf — on an older version the refresh itself still works, you just won't get the confirmation text.

## Examples

```bash
# Browse everything interactively
pacfz

# Explicitly installed packages, largest first
pacfz -e -s

# Everything sorted by description text, A→Z
pacfz -s Description

# Packages sorted by name, Z→A
pacfz --desc

# Just the AUR / foreign packages
pacfz -m

# Anything whose description mentions "editor"
pacfz -f Description editor

# Anything that mentions "vim" in any field — name, description, dependencies, etc.
pacfz -a vim

# Exact name match instead of substring
pacfz -f Name firefox -x

# Everything that is NOT explicitly installed, i.e. pure dependencies —
# bare -v works fine here since there's only one filter to invert
pacfz -v -e

# Explicitly installed packages where something actually depends on them
# or optionally depends on them (Required By / Optional For isn't None) —
# needs scoped -v so -e stays a precondition instead of being inverted too
pacfz -e -v notadep -v notoptdep

# Leave yourself a note on a package
pacfz -D htop "system monitor, keep even if it shows up as orphaned"

# Every package you've left a note on
pacfz --has-note

# Total installed size of all packages
pacfz -t

# After a pacman -Syu or any install/remove, refresh the cache
pacfz -r
```

## pacq — non-interactive queries

`pacq` is a sibling script for when you just want package names back — for shell scripts, pipelines, completions, or anywhere `fzf` doesn't belong. It forwards every flag straight to `listPackages.py`, so it accepts the exact same [Filters](#filters), [Sorting](#sorting), and [Special / utility](#special--utility) flags as `pacfz`, and prints matching package names one per line instead of opening the interactive picker. It deliberately leaves out `-r`/`--refresh`, `-D`/note management, and `--exact`/`--hide-notes` — those belong to the interactive `pacfz` workflow.

```
pacq [OPTIONS]
```

```bash
# Names of every foreign package, one per line
pacq -m

# Pipe straight into another tool
pacq -e -s | head -5

# Sorted by a custom field, descending
pacq -s Version --desc

# Count how many packages mention "python" anywhere
pacq -a python | wc -l

# Scriptable total size
pacq -t
```

## Data locations

| Path                                | Contents                   | Notes                                                                                         |
| ----------------------------------- | -------------------------- | --------------------------------------------------------------------------------------------- |
| `~/.cache/pacman_packages.db`       | Cached `pacman -Qi` output | Rebuilt by `-r`/`--refresh`; safe to delete, it'll regenerate                                 |
| `~/.local/share/pacfz/user_data.db` | Your per-package notes     | Independent of the cache; not touched by `--refresh` — back it up if your notes matter to you |

## Known limitations

- `-t`/`--totalsize` always totals the entire package table and doesn't respect other filters.
- This is built specifically around `pacman`; `createDB.py` will refuse to run on a non-pacman system.
