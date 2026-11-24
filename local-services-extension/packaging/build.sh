#!/usr/bin/env bash
# Build the extension ZIP and graphical helper packages.
set -euo pipefail
umask 022
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir="$(pwd -P)"
build_go="${LOCAL_SERVICES_GO:-go}"
build_nsis="${LOCAL_SERVICES_MAKENSIS:-makensis}"

if [[ $# != 1 ]]; then
  echo "Usage: packaging/build.sh OUTPUT_DIRECTORY" >&2
  exit 2
fi
mkdir -p -- "$1"
output="$(cd -- "$1" && pwd -P)"
stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT

readarray -t metadata < <(node <<'JS'
const fs = require("node:fs");
const crypto = require("node:crypto");
const manifest = JSON.parse(fs.readFileSync("extension/manifest.json", "utf8"));
const id = crypto.createHash("sha256").update(Buffer.from(manifest.key, "base64"))
  .digest("hex").slice(0, 32).replace(/./g, (digit) => String.fromCharCode(97 + parseInt(digit, 16)));
console.log(manifest.version);
console.log("chrome-extension://" + id + "/");
JS
)
version="${metadata[0]}"
origin="${metadata[1]}"
host="io.github.ejoliet.local_services"
helper="local-services-helper"
build_flags="-s -w -X main.extensionOrigin=$origin -X main.version=$version"

"$build_go" build -trimpath -o "$stage/zip" ./packaging/zip.go
"$stage/zip" "$output/local-services-extension.zip" "$project_dir/extension"

build_helper() {
  (cd helper && CGO_ENABLED=0 GOOS="$1" GOARCH="$2" "$build_go" build -trimpath -ldflags "$build_flags" -o "$3" .)
}

for arch in amd64 arm64; do
  echo "Building Linux $arch"
  linux="$stage/linux-$arch"
  mkdir -p "$linux/DEBIAN" "$linux/usr/lib/local-services" "$linux/etc/opt/chrome/native-messaging-hosts" "$linux/etc/chromium/native-messaging-hosts"
  build_helper linux "$arch" "$linux/usr/lib/local-services/$helper"
  cat > "$linux/DEBIAN/control" <<CONTROL
Package: local-services-helper
Version: $version
Section: utils
Priority: optional
Architecture: $arch
Maintainer: Local Services contributors <770124+ejoliet@users.noreply.github.com>
Description: Native discovery helper for the Local Services Chrome extension
 Reads listening TCP sockets and identifies local HTTP and HTTPS endpoints on demand.
CONTROL
  manifest="$linux/etc/opt/chrome/native-messaging-hosts/$host.json"
  cat > "$manifest" <<MANIFEST
{
  "name": "$host",
  "description": "Local Services Helper",
  "path": "/usr/lib/local-services/$helper",
  "type": "stdio",
  "allowed_origins": ["$origin"]
}
MANIFEST
  cp -- "$manifest" "$linux/etc/chromium/native-messaging-hosts/$host.json"
  dpkg-deb --root-owner-group --build "$linux" "$output/$helper-linux-$arch.deb"

  echo "Building macOS $arch"
  mac="$stage/macos-$arch"
  app="$mac/Install Local Services Helper.app/Contents"
  mkdir -p "$app/MacOS" "$app/Resources"
  build_helper darwin "$arch" "$app/Resources/$helper"
  install -m 755 packaging/install-macos "$app/MacOS/Install"
  sed "s/@VERSION@/$version/g" packaging/macos-info.plist > "$app/Info.plist"
  "$stage/zip" "$output/$helper-macos-$arch.zip" "$mac"

  echo "Building Windows $arch"
  windows="$stage/$helper-$arch.exe"
  build_helper windows "$arch" "$windows"
  "$build_nsis" -V2 "-DOUTPUT=$output/$helper-windows-$arch.exe" "-DPAYLOAD=$windows" "-DVERSION=$version" packaging/windows.nsi
done

(cd -- "$output" && sha256sum local-services-extension.zip "$helper"-*.deb "$helper"-*.zip "$helper"-*.exe > SHA256SUMS)
printf 'Built Local Services %s for %s\n' "$version" "$origin"
