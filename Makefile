.PHONY: test check build install uninstall srcinfo clean

test:
	python3 -m pytest tests/ -q

check:
	@for l in pacfz pacq; do bash -n $$l && echo "$$l: syntax OK"; done

# Build the pacman package. Does NOT run the test suite (see PKGBUILD).
build:
	makepkg -s

# Build and install it.
install:
	makepkg -si

uninstall:
	sudo pacman -R pacfz

# Only needed if mirroring this PKGBUILD into the AUR.
srcinfo:
	makepkg --printsrcinfo > .SRCINFO

clean:
	rm -rf pkg src *.pkg.tar.* tests/__pycache__ __pycache__ .pytest_cache
	find . -name '*.pyc' -delete
