# pacfz

Deeper inspection of your installed Arch Linux packages. `pacfz` snapshots
`pacman -Qi` / `pacman -Qqm` into a small SQLite cache and gives you two
front-ends over it:

- **`pacfz`** - an interactive [fzf](https://github.com/junegunn/fzf) picker
  with a rich, colorized preview pane.
- **`pacq`** - the same query engine, non-interactive, one package name per
  line. Pipe it into anything.

Plus per-package **notes**, attached to a package and shown in the preview.

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
| ------------------------- | --------------------------- |
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
downloaded folder - they look for their Python modules in the sibling `lib/`
directory first, so no install step is required to try it out.

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
the repo root. If you build with a bare `makepkg -si` instead, source that
file first to get the same behavior:

```sh
source build.env && makepkg -si
```

This only affects the shell session you run it in. If you'd rather have
_every_ `makepkg` build on your machine redirect to a `build/` next to
wherever you run it - not just this project - set the same five variables
in `~/.makepkg.conf` instead; that applies automatically with no per-build
step, but affects every package you build, not just this one.

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

This is the one piece worth reading carefully, because bare `-v` and
`-v FILTER` do deliberately different things.

**Bare `-v`** inverts _everything else you asked for_, as a single unit, last:

```sh
pacq -m -v                   # NOT foreign
pacq -f Name python -v       # packages whose name does NOT contain "python"
```

**`-v FILTER`** inverts _only that one named filter_ and leaves your other
filters in place as preconditions. It's repeatable, and the named filters are
AND-ed together inside the negation:

```sh
# explicit packages that are NOT(orphans):
pacq -e -v orphan

# explicit packages where NOT(notadep AND notoptdep) -
# i.e. explicit packages that ARE required by something, optionally or not:
pacq -e -v notadep -v notoptdep
```

`FILTER` is one of `foreign`, `orphan`, `explicit`, `deps`, `notadep`,
`notoptdep` (or their short letters `m`/`o`/`e`/`d`/`n`/`k`).

### Notes

Notes show up in the `pacfz` preview pane. Pass `--hide-notes` to suppress
them (the notes DB isn't even opened in that case).

## A note on "orphan"

Here, **orphan** means: installed as a dependency _and_ now required by
nothing (`Install Reason = dependency AND Required By = None`) - the usual
`pacman -Qdt` sense. It does **not** consider _optional_-dependency
relationships, so a package that is only an _optional_ dependency of something
still counts as an orphan. If you want to exclude things that are an optional
dependency for something, combine filters, e.g. `pacq -o -k` (orphans that are
also not an optional dependency for anything).

## Where your files live

| File             | Default location                    | Override              |
| ---------------- | ----------------------------------- | --------------------- |
| Package cache DB | `~/.cache/pacman_packages.db`       | `PACFZ_DB_PATH`       |
| Notes DB         | `~/.local/share/pacfz/user_data.db` | `PACFZ_NOTES_DB_PATH` |

Both defaults follow the XDG base-directory spec, so they move automatically
if you've customized `XDG_CACHE_HOME` / `XDG_DATA_HOME`. Neither survives a
`pacman -R pacfz` uninstall - pacman only removes the files it installed, not
data the program created while running.

The cache is rebuilt atomically (built in a temp file, then swapped into
place), so a rebuild - including a ctrl-r refresh while the preview pane is
reading - never exposes a half-written database.

## Running the tests

Optional, and separate from installing the package - `makepkg -si` doesn't
run these.

```sh
sudo pacman -S python-pytest   # one-time, not installed as a dependency
make test
```
