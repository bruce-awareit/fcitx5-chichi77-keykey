# Maintainer: Foodle <bruce[at]mail.kh.edu.tw>
pkgname=fcitx5-chichi77-keykey
pkgver=1.3.2
pkgrel=1
pkgdesc="琦琦輸入法 (chichi77 KeyKey) - Fcitx5 Chinese input method (Bopomofo / Cangjie / Simplex)"
arch=('x86_64')
url="https://github.com/polobread/KeyKey"
license=('BSD-3-Clause')
depends=(
  'fcitx5'
  'libcanberra'
  'sqlite'
)
makedepends=(
  'base-devel'
  'cmake'
  'fcitx5'
  'libcanberra'
  'sqlite'
  'pkgconf'
  'python'
)
optdepends=(
  'fcitx5-gtk: GTK support'
  'fcitx5-qt: Qt support'
  'fcitx5-configtool: Configuration GUI'
)
source=(
  "https://github.com/polobread/KeyKey/archive/refs/tags/v${pkgver}.tar.gz"
)
sha256sums=('721c8dc0cd0ccc9c4e90abf4562d4ca793fdd3bb04ccd2e2065ae95ec8532afa')

build() {
  cd "${srcdir}/KeyKey-${pkgver}/Source/Loaders/Linux-IME"

  ./configure --prefix=/usr
  make -j$(nproc)
}

check() {
  cd "${srcdir}/KeyKey-${pkgver}/Source/Loaders/Linux-IME"
  make check
}

package() {
  cd "${srcdir}/KeyKey-${pkgver}/Source/Loaders/Linux-IME"
  make DESTDIR="${pkgdir}" install

  # 安裝授權文件
  install -Dm644 "${srcdir}/KeyKey-${pkgver}/LICENSE.txt" \
    "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}

