#!/bin/bash
# Build only. Does not load a kext or change a system/EFI configuration.
set -euo pipefail
cd "$(dirname "$0")"
SDK_PIN=3f750085caa17ec3a7880f11c11bf4f48cd6a164
SDK_PATH=${SDK_PATH:-MacKernelSDK}
case "$SDK_PATH" in /*) ;; *) SDK_PATH="$PWD/$SDK_PATH" ;; esac
if [ "$(uname -s)" != Darwin ]; then echo 'Build requires macOS/Xcode.' >&2; exit 1; fi
if [ ! -f "$SDK_PATH/Headers/IOKit/IOService.h" ] || [ ! -f "$SDK_PATH/Library/x86_64/libkmod.a" ]; then
    echo "Set SDK_PATH to MacKernelSDK at $SDK_PIN." >&2; exit 1
fi
if [ "$(git -C "$SDK_PATH" rev-parse HEAD)" != "$SDK_PIN" ] ||
   [ -n "$(git -C "$SDK_PATH" status --porcelain --untracked-files=no)" ]; then
    echo 'MacKernelSDK must be clean at the pinned revision.' >&2; exit 1
fi
OUT="$PWD/build/Release"
KEXT="$OUT/S540O2MicroReadOnlyProbe.kext"
mkdir -p "$KEXT/Contents/MacOS"
cat > "$OUT/module-info.cpp" <<'EOF'
#include <mach/kmod.h>
extern "C" {
extern kern_return_t _start(kmod_info_t *, void *);
extern kern_return_t _stop(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(org.s540.driver.S540O2MicroReadOnlyProbe, "0.1.0", _start, _stop)
__attribute__((visibility("hidden"))) kmod_start_func_t *_realmain = 0;
__attribute__((visibility("hidden"))) kmod_stop_func_t *_antimain = 0;
__attribute__((visibility("hidden"))) int _kext_apple_cc = __APPLE_CC__;
}
EOF
FLAGS=(-target x86_64-apple-macos10.15 -std=c++14 -mkernel -fapple-kext -fno-builtin
       -fno-exceptions -fno-rtti -fno-common -fno-stack-protector -fno-threadsafe-statics
       -nostdinc -DKERNEL -D__KERNEL__ -I "$SDK_PATH/Headers" -Wall -Wextra -O2)
xcrun clang++ "${FLAGS[@]}" -c S540O2MicroReadOnlyProbe.cpp -o "$OUT/probe.o"
xcrun clang++ "${FLAGS[@]}" -c "$OUT/module-info.cpp" -o "$OUT/module-info.o"
xcrun ld -arch x86_64 -kext -undefined dynamic_lookup -no_function_starts \
    -o "$KEXT/Contents/MacOS/S540O2MicroReadOnlyProbe" \
    "$OUT/probe.o" "$OUT/module-info.o" "$SDK_PATH/Library/x86_64/libkmod.a"
cp Info.plist "$KEXT/Contents/Info.plist"
/usr/bin/plutil -lint "$KEXT/Contents/Info.plist"
/usr/bin/lipo "$KEXT/Contents/MacOS/S540O2MicroReadOnlyProbe" -verify_arch x86_64
/usr/bin/file "$KEXT/Contents/MacOS/S540O2MicroReadOnlyProbe"
echo "Built $KEXT"
