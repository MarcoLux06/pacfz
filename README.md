# pacfz

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
<!-- TODO: once published to the AUR, add a version badge here, e.g.
     https://img.shields.io/aur/version/pacfz -->

**A fast, flexible explorer for your installed Arch Linux packages** - with rich previews, powerful filtering, and
per-package notes, built on top of
[fzf](https://github.com/junegunn/fzf).

<p align="center">
  <img src="assets/demo.gif" alt="pacfz demo" width="700">
</p>

`pacfz` snapshots `pacman -Qi` / `pacman -Qqm` into a small SQLite cache and queries it through two front-ends:

- **`pacfz`** - an interactive fzf picker with a rich, colorized preview pane.
- **`pacq`** - the same query engine, non-interactive, one package name per line.

Both share one flag set, so anything you can filter for interactively you can also script.

## Features

**Filtering**
Narrow the package list by installation reason (explicit / dependency), foreign (AUR/non-repo) status, orphan status,
and dependency relationships (not required by anything, not an optional dependency for anything). Filters combine -
stack as many as you like.

**Field & free-text search**
Search any field with substring or exact matching (`-f`/`-a`/`-x`), and invert results - either the whole query at once,
or just one specific filter while leaving the rest untouched (see [Inverting](#inverting) below).

**Sorting**
Sort by any field, ascending or descending.

**Notes**
Attach a free-text note to any package for anything worth remembering about a specific installation. Notes show up right
in the preview pane.

**Live, self-refreshing cache**
The package cache builds itself on first run and rebuilds atomically. Refresh it with `pacfz -r`, or from inside the
picker with **ctrl-r**, without leaving fzf.

**Total size, filtered**
`-t` reports the installed size of exactly the packages your other filters selected.

For the full flag reference, run `pacfz -h` / `pacq -h`, or see [Usage](#usage) below.

### `pactui` (experimental)

A third, TUI front-end is in development - built with
[Textual](https://github.com/Textualize/textual), sharing the exact same query engine as `pacfz`/`pacq`. It adds an
overview screen (package stats, pacman log) alongside a mouse-and-keyboard-driven search view. Feature parity to
`pacfz` / `pacq` documentation is still in progress. if you're curious, try `pactui` but expect rough edges.
Keybindings: `f1`/`f2` switch between the Overview and Search screens, `/` focuses the search box, `j`/`k`/`g`/`G` move
the table cursor (up/down/top/bottom), `ctrl+r` rebuilds the package cache from the Search screen, `r` refreshes the
Overview screen's stats and log, and `q` quits.

## Requirements

- Arch Linux (or a derivative) with `pacman` and `base-devel` (for `makepkg`).
- `python3` (standard library only; no third-party packages).
- `fzf` - required for the interactive `pacfz` front-end.
- `python-pytest` - needed just for running the test suite

- `python-textual` - required for the interactive `pactui` front-end. (experimental)

## Install

```sh
make install
```

This builds and installs `pacfz` as a normal pacman package:

| What                      | Where                       |
|---------------------------|-----------------------------|
| `pacfz`, `pacq` launchers | `/usr/bin`                  |
| Python modules            | `/usr/share/pacfz`          |
| License                   | `/usr/share/licenses/pacfz` |

### Run without installing

You can also just run `./src/pacfz` / `./src/pacq` straight from the downloaded folder.

### Uninstall

```sh
sudo pacman -R pacfz
```

This removes the launchers and Python modules pacman tracked. It does **not** delete your package cache or notes -
see [Where your files live](#where-your-files-live) below.

### Upgrade

Grab the new release with `git pull`, then `make install` from that folder.

## Usage

`pacfz` and `pacq` share the same core query/filter/sort flags. `pacfz` additionally has picker-only and
notes-management flags `pacq` doesn't (run `pacq -h` to see its own, shorter list):

```
Usage: pacfz [OPTIONS]

Filter Options:
  -m, --foreign       Show only foreign packages
  -o, --orphans       Show only orphan packages
  -e, --explicit      Show only explicitly installed packages
  -d, --deps          Show only dependency packages
  -n, --notadep       Not a dependency for anything
  -k, --notoptdep     Not an optional dependency for anything
  --has-note          Only packages that have a user note
  --no-note           Only packages without a user note
  -f, --field F V     Only packages where field F matches value V
                      (repeatable, AND-combined; e.g. -f Name vim)
  -a, --any V         Only packages where any field matches value V
                      (repeatable, AND-combined with everything else)
  -x, --exact-match   Use exact equality (instead of substring) for -f/-a
  -v, --invert [F]    Bare -v inverts the entire result, applied last.
                      -v FILTER (repeatable) inverts only that one canned
                      filter, leaving every other active filter untouched
                      (e.g. -e -v notadep -v notoptdep = explicit packages
                      where NOT(notadep AND notoptdep)). FILTER is one of:
                      foreign/orphan/explicit/deps/notadep/notoptdep or
                      their short letters m/o/e/d/n/k

Sort Options:
  -s, --sort-by [F]   Sort by field F (default field: Name; bare -s means
                      Installed_Size; --size also still works)
  --asc               Sort ascending (applies to whichever field is sorted)
  --desc              Sort descending (applies to whichever field is sorted)

Size:
  -t, --totalsize     Show total size of the (filtered) packages

Display Options:
  --exact             Use exact matching in fzf (-e flag)
  --hide-notes        Hide user notes in the preview pane

Notes:
  -D <pkg> <note>     Set a note for a package
  -D <pkg> -d         Delete the note for a package
  --notes-list        List all packages that have notes

Other:
  -h, --help          Show this help message
  -r, --refresh       Refresh the package database
  --version           Show the pacfz version

Inside the interactive picker:
  ctrl-r              Rebuild the package cache and refresh the visible
                      list, without leaving fzf - the header shows
                      '✓ cache refreshed at HH:MM:SS' when done, so
                      repeated presses are visibly distinct
```

### Examples

```sh
pacq -m                      # list foreign packages
pacq -o                      # orphans
pacq -m -t                   # total size of just the foreign packages
pacq -f Name vim             # packages whose name contains "vim"
pacq -e -s --desc            # explicit packages, largest first
pacfz -m                     # browse foreign packages interactively
```

### Inverting

Bare `-v` inverts *everything else you asked for*, as a single unit. `-v FILTER` inverts *only that one named filter*,
leaving every other active filter in place as a precondition - and it's repeatable.

```sh
pacq -m -v                   # NOT foreign
pacq -e -v orphan            # explicit packages that are NOT orphans
pacq -e -v notadep -v notoptdep
                             # explicit packages where NOT(notadep AND notoptdep) -
                             # i.e. explicit packages that ARE required by
                             # something, optionally or not
```

`FILTER` is one of `foreign`, `orphan`, `explicit`, `deps`, `notadep`,
`notoptdep` (or their short letters `m`/`o`/`e`/`d`/`n`/`k`).

## A note on "orphan"

Here, **orphan** means: installed as a dependency *and* now required by nothing (
`Install Reason = dependency AND Required By = None`) - the usual `pacman -Qdt` sense. It does **not** consider
*optional*-dependency relationships, so a package that is only an *optional* dependency of something still counts as an
orphan. If you want to exclude things that are an optional dependency for something, combine filters, e.g.
`pacq -o -k` (orphans that are also not an optional dependency for anything).

## A note on locale

pacfz parses the sizes `pacman -Qi` prints, which are locale-formatted with periods (56.72 KiB) and commas (56,72 KiB).
Both are supported as the decimal separator, but other separator styles (e.g. space or apostrophe as a thousands
separator) are not, and will fail to parse. Both binary (KiB, MiB, GiB, TiB) and decimal (KB, MB, GB, TB) units are
supported, each converted with its correct multiplier.

## Where your files live

| File             | Default location                    | Override              |
|------------------|-------------------------------------|-----------------------|
| Package cache DB | `~/.cache/pacman_packages.db`       | `PACFZ_DB_PATH`       |
| Notes DB         | `~/.local/share/pacfz/user_data.db` | `PACFZ_NOTES_DB_PATH` |

Both defaults follow the XDG base-directory spec, so they move automatically if you've customized `XDG_CACHE_HOME` /
`XDG_DATA_HOME`.

## License

MIT - see [LICENSE](LICENSE).
