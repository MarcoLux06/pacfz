.PHONY: test check build install uninstall srcinfo clean

test:
	python3 -m pytest tests/ -q

check:
	@for l in src/pacfz src/pacq; do bash -n $$l && echo "$$l: syntax OK"; done

# Build the pacman package. Does NOT run the test suite (see PKGBUILD).
# All output (build.env redirects it) ends up in build/, not the repo root.
build:
	mkdir -p build
	bash -c 'source build.env && exec makepkg -s'

# Build and install it.
install:
	mkdir -p build
	bash -c 'source build.env && exec makepkg -si'

uninstall:
	sudo pacman -R pacfz

# Only needed if mirroring this PKGBUILD into the AUR.
srcinfo:
	makepkg --printsrcinfo > .SRCINFO

clean:
	rm -rf build tests/__pycache__ src/lib/__pycache__ .pytest_cache
	find . -name '*.pyc' -delete
