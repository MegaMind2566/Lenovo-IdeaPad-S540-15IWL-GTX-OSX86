#!/bin/bash
set -euo pipefail

export PATH=/usr/bin:/bin:/usr/sbin:/sbin

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
S540_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)"
S540_SOURCE="$S540_ROOT/packages/nullmoth-s540/S540Sensors"
S540_BUILD="$S540_ROOT/build/nullmoth-s540/S540Sensors.kext"
S540_OBJECTS="$S540_ROOT/build/nullmoth-s540/S540Sensors-objects"
S540_KERNEL_SDK="$S540_ROOT/_external/MacKernelSDK"
S540_LILU="$S540_ROOT/_external/Lilu-1.7.2/Lilu"
S540_VSMC="$S540_ROOT/_external/VirtualSMC-1.3.8"

mkdir -p "$S540_BUILD/Contents/MacOS" "$S540_OBJECTS"
cp "$S540_SOURCE/Info.plist" "$S540_BUILD/Contents/Info.plist"

S540_FLAGS=(
  -arch x86_64
  -mmacosx-version-min=15.0
  -O2
  -Wall
  -Wextra
  -Werror
  -Wno-unused-parameter
  -Wno-mismatched-tags
  -Wno-sign-conversion
  -Wno-shadow
  -mkernel
  -fapple-kext
  -fno-builtin
  -fno-common
  -fno-stack-protector
  -mno-red-zone
  -fno-exceptions
  -fno-rtti
  -nostdinc
  -nostdinc++
  -DKERNEL
  -D__KERNEL__
  -std=gnu++17
  -isystem "$S540_KERNEL_SDK/Headers"
  -I "$S540_LILU"
  -I "$S540_VSMC"
  -I "$S540_SOURCE"
)

xcrun clang++ "${S540_FLAGS[@]}" -c "$S540_SOURCE/S540Sensors.cpp" -o "$S540_OBJECTS/S540Sensors.o"
xcrun clang++ "${S540_FLAGS[@]}" -c "$S540_SOURCE/kmod_start.cpp" -o "$S540_OBJECTS/kmod_start.o"

xcrun clang++ -arch x86_64 -mmacosx-version-min=15.0 -mkernel -nostdlib \
  -Wl,-kext -Wl,-no_source_version \
  "$S540_OBJECTS/S540Sensors.o" "$S540_OBJECTS/kmod_start.o" \
  "$S540_KERNEL_SDK/Library/x86_64/libkmod.a" \
  -o "$S540_BUILD/Contents/MacOS/S540Sensors"

codesign --force --sign - "$S540_BUILD"
codesign --verify --strict "$S540_BUILD"
plutil -lint "$S540_BUILD/Contents/Info.plist"
file "$S540_BUILD/Contents/MacOS/S540Sensors"
nm -u "$S540_BUILD/Contents/MacOS/S540Sensors" | sort
shasum -a 256 "$S540_SOURCE"/* "$S540_BUILD/Contents/Info.plist" "$S540_BUILD/Contents/MacOS/S540Sensors"
