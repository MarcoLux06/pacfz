# makepkg's own scratch directories are named "src" and "pkg" by default —
# the same name we use for our actual tracked source tree. BUILDDIR moves
# those scratch directories entirely outside the repo (and outside any name
# collision), so building never clutters or touches ./src.
BUILDDIR ?= /tmp/makepkg-pacfz

.PHONY: test check build install uninstall srcinfo clean

test:
	python3 -m pytest tests/ -q

check:
	@for l in src/pacfz src/pacq; do bash -n $$l && echo "$$l: syntax OK"; done

# Build the pacman package. Does NOT run the test suite (see PKGBUILD).
build:
	BUILDDIR=$(BUILDDIR) makepkg -s

# Build and install it.
install:
	BUILDDIR=$(BUILDDIR) makepkg -si

uninstall:
	sudo pacman -R pacfz

# Only needed if mirroring this PKGBUILD into the AUR.
srcinfo:
	makepkg --printsrcinfo > .SRCINFO

clean:
	rm -rf $(BUILDDIR) *.pkg.tar.* tests/__pycache__ src/lib/__pycache__ .pytest_cache
	find . -name '*.pyc' -delete
