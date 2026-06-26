# pacfz

Deeper inspection of your installed Arch Linux packages. `pacfz` snapshots
`pacman -Qi` / `pacman -Qqm` into a small SQLite cache and gives you two
front-ends over it:

- **`pacfz`** — an interactive [fzf](https://github.com/junegunn/fzf) picker
  with a rich, colorized preview pane.
- **`pacq`** — the same query engine, non-interactive, one package name per
  line. Pipe it into anything.

Plus per-package **notes** ("built from source, don't let the AUR helper touch
it"), attached to packages and shown in the preview.

## Requirements

- Arch Linux (or a derivative) with `pacman` and `base-devel` (for `makepkg`).
- `python3` (standard library only; no third-party packages).
- `fzf` — required for the interactive `pacfz` front-end. `pacq` works without it.

## Install

```sh
makepkg -si          # or: make install
```

This builds and installs `pacfz` as a normal pacman package: launchers in
`/usr/bin`, the Python modules in `/usr/share/pacfz`, docs in
`/usr/share/doc/pacfz`, and the license in `/usr/share/licenses/pacfz`. It also
registers pacfz with pacman, so `pacman -Qi pacfz`, upgrades, and `pacman -R
pacfz` (or `make uninstall`) all work as expected — fitting, for a tool whose
whole purpose is inspecting installed packages.

The PKGBUILD deliberately does **not** run the test suite as part of
`makepkg -si` — doing so would pull in `python-pytest` (and its dependency
chain) for every install, just to use the program. If you want to run the
tests yourself — e.g. before trusting a build, or after pulling new code —
see [Running the tests](#running-the-tests) below; it's a separate, optional
step.

If you're publishing releases, see [Releasing](#releasing-tagging-for-the-pkgbuild)
below — `pkgver` and the checksum need to stay in sync with your Codeberg tags.

### Running from a checkout without installing

You don't need to package or install anything to try it out or to develop:
`./pacfz` and `./pacq` look for their Python modules next to themselves first,
and only fall back to `/usr/share/pacfz` if they're not found there. So from a
git checkout:

```sh
./pacfz -m            # just works, no install step
```

### After installing (either way)

The cache is built automatically on first run, so you can go straight to
`pacfz`. Rebuild it any time with `pacfz -r`, or from inside the picker with
**ctrl-r** (which refreshes the visible list in place and stamps the header
with the time).

## Repository layout

The PKGBUILD's `package()` function `cd "$pkgname"` (i.e. `cd pacfz`) right
after extracting the release tarball, then expects to find `config.py`,
`list_packages.py`, `pacfz`, `pacq`, `tests/`, etc. *directly* inside that
directory — not nested under something like `src/` or `pacfz-core/`. That's
because Codeberg/Gitea release tarballs extract to a top-level folder named
after the repository itself (just `pacfz`), unlike GitHub's `repo-tag`
naming. So:

- Keep everything flat at the repo root, exactly as it is now. If you ever
  restructure into subdirectories, update the `cd` path in `PKGBUILD`'s
  `package()` to match, or the package will fail to build.
- The repo name on Codeberg must stay `pacfz` to match `$pkgname` in
  `PKGBUILD` — the `source=()` URL and the post-extraction `cd "$pkgname"`
  both assume that.
- Tags must be named `v$pkgver` (e.g. `v1.0.0`), matching the `source=()` URL
  pattern `$url/archive/v$pkgver.tar.gz`.

**Yes, commit `PKGBUILD` (and `LICENSE`, `.gitignore`) to the repo**, at the
root, alongside `README.md`. That's the standard convention — anyone cloning
the repo or grabbing a release tarball should be able to run `makepkg -si`
immediately, without fetching anything from elsewhere. (A separate `.SRCINFO`
file is only needed if you later mirror this into the official AUR, which
uses its own git repo per package and reads `.SRCINFO` instead of executing
`PKGBUILD`. For installing straight from your own Codeberg repo, it's not
required — see the `srcinfo` Makefile target if you ever need to generate it.)

## Usage

`pacfz` (interactive) and `pacq` (non-interactive) share the same filters:

| Flag | Meaning |
|------|---------|
| `-m, --foreign` | foreign (AUR / non-repo) packages |
| `-o, --orphans` | orphans (see the note below) |
| `-e, --explicit` | explicitly installed |
| `-d, --deps` | installed as a dependency |
| `-n, --notadep` | not required by anything |
| `-k, --notoptdep` | not an optional dependency for anything |
| `--has-note` / `--no-note` | filter by presence of a user note |
| `-f, --field FIELD VALUE` | field matches value (repeatable, AND-combined) |
| `-a, --any VALUE` | any field matches value (repeatable) |
| `-x, --exact-match` | exact equality instead of substring for `-f`/`-a` |
| `-s, --sort-by [FIELD]` | sort (default `Name`; bare `-s` sorts by size) |
| `--asc` / `--desc` | sort direction |
| `-t, --totalsize` | total installed size of the **filtered** set |

By default `-f`/`-a` do case-sensitive substring matching; add `-x` for exact
equality.

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

**Bare `-v`** inverts *everything else you asked for*, as a single unit, last:

```sh
pacq -m -v                   # NOT foreign
pacq -f Name python -v       # packages whose name does NOT contain "python"
```

**`-v FILTER`** inverts *only that one named filter* and leaves your other
filters in place as preconditions. It's repeatable, and the named filters are
AND-ed together inside the negation:

```sh
# explicit packages that are NOT(orphans):
pacq -e -v orphan

# explicit packages where NOT(notadep AND notoptdep) —
# i.e. explicit packages that ARE required by something, optionally or not:
pacq -e -v notadep -v notoptdep
```

`FILTER` is one of `foreign`, `orphan`, `explicit`, `deps`, `notadep`,
`notoptdep` (or their short letters `m`/`o`/`e`/`d`/`n`/`k`).

### Notes

```sh
pacfz -D firefox "daily driver, keep on stable"   # set a note
pacfz -D firefox -d                                # delete it
pacfz --notes-list                                 # list all notes
pacq --has-note                                    # packages that have a note
```

Notes show up in the `pacfz` preview pane. Pass `--hide-notes` to suppress
them (the notes DB isn't even opened in that case).

## A note on "orphan"

Here, **orphan** means: installed as a dependency *and* now required by
nothing (`Install Reason = dependency AND Required By = None`) — the usual
`pacman -Qdt` sense. It does **not** consider *optional*-dependency
relationships, so a package that is only an *optional* dependency of something
still counts as an orphan. If you want to exclude things that are an optional
dependency for something, combine filters, e.g. `pacq -o -k` (orphans that are
also not an optional dependency for anything).

(Internally, "None" is the literal string pacman prints for an empty field and
is stored verbatim — it is not SQL `NULL`.)

## Configuration

All paths honor the XDG base-directory spec and can be overridden:

| Variable | Default | Purpose |
|----------|---------|---------|
| `XDG_CACHE_HOME` | `~/.cache` | location of the package cache DB |
| `XDG_DATA_HOME` | `~/.local/share` | location of the per-user notes DB |
| `PACFZ_DB_PATH` | `$XDG_CACHE_HOME/pacman_packages.db` | override the cache DB path outright |
| `PACFZ_NOTES_DB_PATH` | `$XDG_DATA_HOME/pacfz/user_data.db` | override the notes DB path outright |

Note these are unrelated to where the Python modules themselves live
(`/usr/share/pacfz` once installed via the PKGBUILD, or the checkout directory
when run directly) — that's a fixed lookup in `pacfz`/`pacq`, not something
governed by XDG variables.

The cache is rebuilt atomically (built in a temp file, then swapped into place),
so a rebuild — including a ctrl-r refresh while the preview pane is reading —
never exposes a half-written database.

## Releasing: tagging for the PKGBUILD

The `PKGBUILD` pulls its source from a tagged Codeberg release archive, not
from `main` directly, so a tag is what makes a version installable via
`makepkg -si`.

1. Bump `pkgver` (and reset `pkgrel=1`) in `PKGBUILD`.
2. Commit, then tag and push: `git tag v1.0.0 && git push origin v1.0.0`.
   Codeberg auto-generates `https://codeberg.org/marco-l/pacfz/archive/v1.0.0.tar.gz`
   for any tag — no separate "release" step is required for this to work,
   though making a proper Release on Codeberg's UI is still nice for
   changelogs.
3. Refresh the checksum so `makepkg` can verify the tarball:
   ```sh
   updpkgsums          # or: makepkg -g >> PKGBUILD, then dedupe by hand
   ```
4. Commit the updated `PKGBUILD` (with the new `sha256sums`).
5. Optionally regenerate `.SRCINFO` if you're mirroring this into the AUR:
   ```sh
   makepkg --printsrcinfo > .SRCINFO
   ```

If you bump `pkgrel` only (packaging fix, no source change), the existing
checksum stays valid — you're not re-fetching the tarball.

## Running the tests

These are entirely optional and separate from installing the package — see
[Install](#install) above for why `makepkg -si` doesn't run them itself.

```sh
make test        # equivalent to: python3 -m pytest tests/ -q
make check       # bash -n syntax check on the launchers
```

`make test` requires `python-pytest`, which is **not** installed as a
dependency of the package — install it yourself first if you want to run the
suite:

```sh
sudo pacman -S python-pytest
```

The suite runs against bundled fixture databases (no pacman required) by
pointing `PACFZ_DB_PATH` / `PACFZ_NOTES_DB_PATH` at scratch copies.
