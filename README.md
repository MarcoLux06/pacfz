# pacfz

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
<!-- TODO: once published to the AUR, add a version badge here, e.g.
     https://img.shields.io/aur/version/pacfz -->

**A fast, flexible explorer for your installed Arch Linux packages** - with
rich previews, powerful filtering, and per-package notes, built on top of
[fzf](https://github.com/junegunn/fzf).

<!-- TODO: demo.gif goes here — a quick pacfz session: launch, fuzzy-search,
     preview pane scrolling through package info, maybe an -v invert example.
     Suggested: asciinema or a short terminal-recording GIF, ~15-30s. -->
<!-- ![pacfz demo](demo.gif) -->

`pacfz` snapshots `pacman -Qi` / `pacman -Qqm` into a small SQLite cache and
queries it through two front-ends:

- **`pacfz`** - an interactive fzf picker with a rich, colorized preview pane.
- **`pacq`** - the same query engine, non-interactive, one package name per
  line. Pipe it into anything.

Both share one flag set, so anything you can filter for interactively you
can also script.

## Features

**Filtering**
Narrow the package list by install reason (explicit / dependency), foreign
(AUR/non-repo) status, orphan status, and dependency relationships (not
required by anything, not an optional dependency for anything). Filters
combine - stack as many as you like.

**Field & free-text search**
Search any field with substring or exact matching (`-f`/`-a`/`-x`), and
invert results - either the whole query at once, or just one specific
filter while leaving the rest untouched (see [Inverting](#inverting--v---invert)
below).

**Sorting**
Sort by any field, ascending or descending; a bare size-sort is one flag
away.

**Notes**
Attach a free-text note to any package - handy for "built from source,
don't touch," AUR-vs-repo reminders, or anything else worth remembering
about a specific install. Notes show up right in the preview pane.

**Live, self-refreshing cache**
The package cache builds itself on first run and rebuilds atomically (built
to a temp file, then swapped in - never a half-written read). Refresh it
anytime with `pacfz -r`, or from inside the picker with **ctrl-r**, without
leaving fzf.

**Total size, filtered**
`-t` reports the installed size of exactly the packages your other filters
selected - not the whole system.

For the full flag reference, run `pacfz -h` / `pacq -h`, or see
[Usage](#usage) below.

### `pactui` (experimental)

A third, TUI front-end is in development - built with
[Textual](https://github.com/Textualize/textual), sharing the exact same
query engine as `pacfz`/`pacq`. It adds an overview screen (package stats,
pacman log) alongside a mouse-and-keyboard-driven search view. Not yet
packaged or documented for general use; try it straight from a checkout with
`python3 src/pactui` if you're curious, but expect rough edges.

## Requirements

- Arch Linux (or a derivative) with `pacman` and `base-devel` (for `makepkg`).
- `python3` (standard library only; no third-party packages).
- `fzf` - required for the interactive `pacfz` front-end. `pacq` works without it.

## Install

```sh
make install
```

(equivalent to `makepkg -si`, but keeps every build artifact under `build/`
instead of the repo root - see [Keeping builds out of the repo](#keeping-builds-out-of-the-repo)
below. If you'd rather not use `make`, run
`source build.env && makepkg -si` instead, for the same effect.)

This builds and installs `pacfz` as a normal pacman package:

| What                      | Where                       |
|---------------------------|-----------------------------|
| `pacfz`, `pacq` launchers | `/usr/bin`                  |
| Python modules            | `/usr/share/pacfz`          |
| License                   | `/usr/share/licenses/pacfz` |

Because it's a real pacman package, `pacman -Qi pacfz` shows it as installed,
and the usual commands work as expected.

The cache is built automatically on first run, so you can go straight to
`pacfz`. Rebuild it any time with `pacfz -r`, or from inside the picker with
**ctrl-r** (which refreshes the visible list in place and stamps the header
with the time).

### Quick look without installing

You can also just run `./src/pacfz` / `./src/pacq` straight from the
downloaded folder.

### Uninstall

```sh
sudo pacman -R pacfz
```

This removes the launchers and Python modules pacman tracked. It does **not**
delete your package cache or notes - see [Where your files live](#where-your-files-live)
below. Remove those by hand if you want a clean slate.

### Upgrade

Grab the new release, then `make install` again from that folder - pacman
detects you already have an older version installed and replaces it. No
separate "upgrade" command needed.

### Keeping builds out of the repo

`make build`/`make install` source `build.env`, which redirects everything
`makepkg` produces - the extracted source, the staged install tree, the
final `.pkg.tar.zst`, logs - into `build/` (already gitignored) instead of
the repo root.

```sh
source build.env && makepkg -si
```

## Usage

`pacfz` and `pacq` share the same flags (`pacfz -h` / `pacq -h` for this same
text):

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

Display Options:
  --exact             Use exact matching in fzf (-e flag)
  --hide-notes        Hide user notes in the preview pane
  -t, --totalsize     Show total size of the (filtered) packages

Notes:
  -D <pkg> <note>     Set a note for a package
  -D <pkg> -d         Delete the note for a package
  --notes-list        List all packages that have notes

Other:
  -h, --help          Show this help message
  -r, --refresh       Refresh the package database

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

### Inverting: `-v` / `--invert`

Bare `-v` inverts *everything else you asked for*, as a single unit. `-v
FILTER` inverts *only that one named filter*, leaving every other active
filter in place as a precondition - and it's repeatable.

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

### Notes

Notes show up in the `pacfz` preview pane. Pass `--hide-notes` to suppress.

## A note on "orphan"

Here, **orphan** means: installed as a dependency *and* now required by
nothing (`Install Reason = dependency AND Required By = None`) - the usual
`pacman -Qdt` sense. It does **not** consider *optional*-dependency
relationships, so a package that is only an *optional* dependency of something
still counts as an orphan. If you want to exclude things that are an optional
dependency for something, combine filters, e.g. `pacq -o -k` (orphans that are
also not an optional dependency for anything).

## Where your files live

| File             | Default location                    | Override              |
|------------------|-------------------------------------|-----------------------|
| Package cache DB | `~/.cache/pacman_packages.db`       | `PACFZ_DB_PATH`       |
| Notes DB         | `~/.local/share/pacfz/user_data.db` | `PACFZ_NOTES_DB_PATH` |

Both defaults follow the XDG base-directory spec, so they move automatically
if you've customized `XDG_CACHE_HOME` / `XDG_DATA_HOME`. Neither survives a
`pacman -R pacfz` uninstall - pacman only removes the files it installed, not
data the program created while running.

The cache is rebuilt atomically (built in a temp file, then swapped into
place), so a rebuild - including a ctrl-r refresh while the preview pane is
reading - never exposes a half-written database.

## License

MIT - see [LICENSE](LICENSE).