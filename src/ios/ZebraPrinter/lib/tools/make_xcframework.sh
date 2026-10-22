#!/bin/sh
# Builds ZSDK_API.xcframework (device + simulator slices) from Zebra's
# universal libZSDK_API.a, whose arm64 slice is built for iOS devices only.
#
#   usage: make_xcframework.sh <path/to/libZSDK_API.a> [output dir]
#
# The simulator slice is produced by rewriting the platform load command of
# every arm64 / x86_64 object to "iOS simulator" (tools/macho_to_sim.py);
# the code itself is unchanged.  If Zebra ever ships a library that already
# contains an arm64 simulator slice, replace the "sim" part below with it.
set -e
LIB=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=${2:-$(cd "$(dirname "$0")/.." && pwd)}
HERE=$(cd "$(dirname "$0")" && pwd)
INCLUDE="$HERE/../include"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

lipo "$LIB" -thin arm64 -output "$WORK/ios-arm64.a"
mkdir -p "$WORK/ios" "$WORK/sim"
cp "$WORK/ios-arm64.a" "$WORK/ios/libZSDK_API.a"

for arch in arm64 x86_64; do
    mkdir -p "$WORK/$arch" "$WORK/sim-$arch"
    lipo "$LIB" -thin $arch -output "$WORK/$arch.a"
    (cd "$WORK/$arch" && ar -x "../$arch.a")
    for o in "$WORK/$arch"/*.o; do
        python3 "$HERE/macho_to_sim.py" "$o" "$WORK/sim-$arch/$(basename "$o")"
    done
    libtool -static -o "$WORK/sim-$arch.a" "$WORK/sim-$arch"/*.o 2>&1 | grep -v 'has no symbols' || true
done
lipo -create "$WORK/sim-arm64.a" "$WORK/sim-x86_64.a" -output "$WORK/sim/libZSDK_API.a"

rm -rf "$OUT/ZSDK_API.xcframework"
xcodebuild -create-xcframework \
    -library "$WORK/ios/libZSDK_API.a" -headers "$INCLUDE" \
    -library "$WORK/sim/libZSDK_API.a" -headers "$INCLUDE" \
    -output "$OUT/ZSDK_API.xcframework"
