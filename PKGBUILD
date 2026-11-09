# Maintainer: Foodle <bruce[at]mail.kh.edu.tw>
pkgname=fcitx5-chichi77-keykey
pkgver=1.5.0
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
  'rust'
  'rust-docs'
)
optdepends=(
  'fcitx5-gtk: GTK support'
  'fcitx5-qt: Qt support'
  'fcitx5-configtool: Configuration GUI'
)
source=(
  "https://github.com/polobread/KeyKey/archive/refs/tags/v${pkgver}.tar.gz"
  "arch-rust-docs-compatibility.patch"
)
sha256sums=(
  '4a53c0b5971d8bf3b93a7c8a5d2b8f650aa1f31c7da94342877df3a1d7935947'
  'SKIP'
)

prepare() {
  cd "${srcdir}/KeyKey-${pkgver}"
  
  # 自動套用相容 Arch Linux 的 Rust doc/licenses 路徑補丁
  patch -Np1 -i "${srcdir}/arch-rust-docs-compatibility.patch"
}

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
