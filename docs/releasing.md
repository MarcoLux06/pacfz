# Release process

This is the actual sequence for cutting a new release, and why it has to happen in this order. Most of the
individual steps are mechanical, the ordering is the part that's easy to get wrong.

## What lives where

The release automation itself (a script that walks through all of this interactively, plus a `--dev` mode that
targets a private sandbox repo instead of the real one) deliberately isn't part of this repo. It's a personal tool
that lives elsewhere and just operates on a checkout of this project from the outside, the same way you'd run any
of this by hand. What *is* in the repo is everything the release actually touches: `PKGBUILD`, `src/lib/config.py`'s
`__version__`, and the `Makefile`/`build.env` machinery that keeps build output out of the repo root.

## The actual sequence

1. **Commit and push whatever's going into the release.** Sounds obvious, but worth saying explicitly, uncommitted
   changes never get swept into a push, only committed work does. If something's still sitting uncommitted when you
   start the release, it silently won't be in the tag.
2. **Bump the version, in two places, in the same commit.** `PKGBUILD`'s `pkgver` (reset `pkgrel` to `1` alongside
   it) and `src/lib/config.py`'s `__version__`. These have to move together, `config.py`'s version is what actually
   shows up at runtime for `--version` on all three front-ends, so if it drifts from what's packaged, `pacfz
   --version` would report something that doesn't match the installed package.
3. **Tag and push the tag**, named `v$pkgver` to match `PKGBUILD`'s `source=()` line, which points at
   `$url/archive/v$pkgver.tar.gz`. On Codeberg this can be done entirely through the web UI (Releases, New Release,
   type the tag name, it offers to create it from `main`), no local `git tag` needed if you'd rather not.
4. **Only now compute the checksum.** This is the step that has to happen after the tag exists, not before,
   `updpkgsums` (or `makepkg -g` if `pacman-contrib` isn't installed) downloads the tarball at that exact URL and
   hashes it, and that URL doesn't resolve to real bytes until the tag/release actually exists on Codeberg. Trying
   to compute this earlier just gets you a checksum for nothing.
5. **Commit the checksum, push again.** This is necessarily a separate commit from the version bump, not a
   shortcoming, the checksum can't exist until step 3 has already happened, so it can't have been part of the same
   commit no matter how you order things locally.
6. **Verify with a real build.** `make install` (or `make build` if you don't want to actually install it) runs
   `makepkg` against the real tagged tarball, validates the checksum for real, and confirms the release genuinely
   installs. `build.env` keeps all of this contained under `build/`, sourced automatically by both `make` targets,
   so a build never touches anything else in the repo. If you'd rather test a release before it's actually pushed to
   Codeberg at all, `git archive --format=tar.gz --prefix=pacfz/ -o pacfz-local.tar.gz HEAD` produces a tarball
   shaped exactly like Codeberg's own archive would, and pointing `PKGBUILD`'s `source=()` at that local file (with
   `sha256sums=('SKIP')`) lets you build without touching the network or Codeberg at all, just remember to revert
   that edit afterward.

## Why the checksum step trips people up

The natural instinct is to fill in the checksum while you're already editing `PKGBUILD` for the version bump, since
it's right there. That doesn't work, and it's not a workaround-able ordering, `sha256sums` has to describe the exact
bytes of a file that only exists once the tag is live. `sha256sums=('SKIP')` in the meantime is fine and expected,
it just means "not computed yet," not "broken."

## AUR-specific notes (not yet relevant, kept here for later)

This project isn't published to the AUR yet. When it is, the AUR side works differently in one important way: the
AUR is its own git server (`ssh://aur@aur.archlinux.org/pacfz.git`), a completely separate repo from this one, whose
entire contents are just `PKGBUILD` and a generated `.SRCINFO` (`make srcinfo` produces that). That `PKGBUILD` would
still point its `source=()` at this repo's Codeberg releases, same as it does now, the AUR repo doesn't host any
actual source, just the packaging recipe. Publishing there means copying the already-tested `PKGBUILD` from here
into that separate checkout, regenerating `.SRCINFO`, and pushing there too, on top of everything above, not instead
of it.
