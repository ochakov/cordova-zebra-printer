# ZSDK_API.xcframework

Zebra's Link-OS SDK for iOS is distributed as a universal static library
(`libZSDK_API.a`, slices armv7 / arm64 / i386 / x86_64) whose arm64 objects
are marked as built for iOS *devices* (`LC_VERSION_MIN_IPHONEOS`).  On an
Apple-silicon Mac the iOS simulator is arm64 too, so Xcode refuses to link it:

    ld: building for 'iOS-simulator', but linking in object file
        (libZSDK_API.a[arm64][2](TcpPrinterConnection.o)) built for 'iOS'

Xcode 26+ has no Rosetta (x86_64) simulator destinations any more, so the
plugin ships the SDK as an XCFramework with two slices instead:

| slice | contents |
|---|---|
| `ios-arm64` | Zebra's original arm64 device objects, untouched |
| `ios-arm64_x86_64-simulator` | the same arm64 and x86_64 objects with their platform load command rewritten to *iOS simulator* (`LC_BUILD_VERSION`, platform 7) |

Only the Mach-O header of each object changes; code, symbols and relocations
are byte-identical (`tools/macho_to_sim.py` shifts the file offsets by the
8 bytes the longer load command needs).  The SDK itself was not rebuilt, so
MFi Bluetooth printing (`MfiBtPrinterConnection`) still needs a real device;
TCP printing and the rest of the API work in the simulator.

## Regenerating

```sh
src/ios/ZebraPrinter/lib/tools/make_xcframework.sh path/to/libZSDK_API.a
```

writes `src/ios/ZebraPrinter/lib/ZSDK_API.xcframework` from any
`libZSDK_API.a` that contains arm64 and x86_64 slices (headers are taken from
`include/`).  If a future Zebra release already contains an arm64 simulator
slice, package it with `xcodebuild -create-xcframework` directly and drop the
rewrite step.

Current build: Link-OS SDK library from the original plugin (objects built
with `LC_VERSION_MIN_IPHONEOS 8.0`), converted 2026-10-22.
