#!/bin/bash
# Export only raphael source changes; proprietary firmware and DTBs remain local.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
MU=../../../Mu-Silicium
git -C "$MU" rev-parse HEAD > BASE
git -C "$MU" diff -- BootShim Silicon > mu-silicium.patch
stage=$(mktemp -d files-export.XXXXXX)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/Platforms/Xiaomi" "$stage/Resources/Configs"
cp -a "$MU/Platforms/Xiaomi/raphaelPkg" "$stage/Platforms/Xiaomi/"
cp "$MU/Resources/Configs/raphael.toml" "$stage/Resources/Configs/"
mkdir -p "$stage/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib"
cp "$MU/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/"XnuLoader.[ch] "$stage/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/"
rm -rf files
mv "$stage" files
trap - EXIT
