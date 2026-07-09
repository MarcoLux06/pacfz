# Maintainer: marco-l
pkgname=pacfz
pkgver=1.1.2
pkgrel=1
pkgdesc="Interactive fzf/CLI explorer for installed pacman packages, with a cached SQLite metadata store and per-package notes"
arch=('any')
url="https://codeberg.org/marco-l/pacfz"
license=('MIT')
depends=('python')
optdepends=('fzf: for pacfz'
            'python-textual: for pactui'
            'python-pytest: for unit testing')

source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
sha256sums=('48bd7f6f752a9583da1e5f4d4b84bf1ee4553227001127e34d2bc9d4ef19e564')

package() {
  cd "$pkgname"

  install -Dm755 src/pacfz "$pkgdir/usr/bin/pacfz"
  install -Dm755 src/pacq  "$pkgdir/usr/bin/pacq"
  install -Dm755 src/pactui "$pkgdir/usr/bin/pactui"

  install -d "$pkgdir/usr/share/pacfz/lib"
  install -Dm644 src/lib/config.py src/lib/notes_db.py src/lib/preview_item.py \
    src/lib/list_packages.py src/lib/create_db.py src/lib/note_manager.py \
    src/lib/pacman_log.py \
    -t "$pkgdir/usr/share/pacfz/lib/"

  install -Dm644 src/key-bindings.bash "$pkgdir/usr/share/pacfz/key-bindings.bash"
  install -Dm644 src/key-bindings.zsh "$pkgdir/usr/share/pacfz/key-bindings.zsh"

  install -Dm644 LICENSE -t "$pkgdir/usr/share/licenses/$pkgname/"
}
