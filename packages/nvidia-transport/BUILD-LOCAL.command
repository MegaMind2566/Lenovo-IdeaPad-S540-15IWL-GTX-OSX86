#!/bin/bash
# Build and verify the experimental package; never install or load the kext.
set -euo pipefail
umask 077

stop() { printf 'Local NVIDIA build stopped: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || stop 'This command takes no arguments.'
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || stop 'Intel macOS is required.'
PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)
SOURCE_COMMIT='NVIDIA_LOCAL_SOURCE_COMMIT_PENDING'
SDK_COMMIT='3f750085caa17ec3a7880f11c11bf4f48cd6a164'
[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || stop 'Use the complete local-build ZIP, not the source template.'
if ! /usr/bin/xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang++ >/dev/null 2>&1; then
    printf 'Apple Command Line Tools are required. Run this command, complete the installation, then run BUILD-LOCAL.command again:\n\nxcode-select --install\n' >&2
    exit 1
fi
/usr/bin/python3 -c 'import sys; assert sys.version_info >= (3, 9)' >/dev/null 2>&1 || stop 'Python 3.9 or later from Apple Command Line Tools is required.'
[ -d "$HOME/Desktop" ] && [ -w "$HOME/Desktop" ] || stop 'The Desktop is not writable.'
[ -d "$PACKAGE/source" ] && [ -f "$PACKAGE/SOURCE-SHA256SUMS" ] || stop 'The source bundle is incomplete.'
(cd "$PACKAGE" && /usr/bin/shasum -a 256 -c SOURCE-SHA256SUMS) || stop 'A packaged source file differs from its checksum.'
WORK=$(/usr/bin/mktemp -d "$HOME/Desktop/NVIDIA-BUILD.XXXXXX") || stop 'Cannot create a private build folder.'
printf 'Building the integrated NVIDIA OS-adapter prototype. No administrator password is required.\nBuild folder: %s\n' "$WORK"

build_package() {
    printf 'Fetching the pinned public MacKernelSDK source.\n'
    export GIT_TERMINAL_PROMPT=0
    /usr/bin/git init -q "$WORK/MacKernelSDK" || return $?
    /usr/bin/git -C "$WORK/MacKernelSDK" remote add origin https://github.com/acidanthera/MacKernelSDK.git || return $?
    /usr/bin/git -c credential.helper= -c core.hooksPath=/dev/null -C "$WORK/MacKernelSDK" fetch --no-tags --depth=1 origin "$SDK_COMMIT" || return $?
    /usr/bin/git -c core.hooksPath=/dev/null -C "$WORK/MacKernelSDK" checkout --detach FETCH_HEAD || return $?
    printf 'Running the host policy tests.\n'
    CXX=/usr/bin/clang++ /usr/bin/python3 "$PACKAGE/source/tests/test_nvidia_transport_kernel.py" || return $?
    printf 'Compiling and verifying the native Intel package.\n'
    GITHUB_SHA="$SOURCE_COMMIT" /usr/bin/python3 "$PACKAGE/source/builders/build_nvidia_transport.py" \
        --kernel-sdk "$WORK/MacKernelSDK" --output-dir "$WORK/output" --allow-legacy-probe
}

if build_package 2>&1 | /usr/bin/tee "$WORK/build.log"; then
    printf '\nBuild completed. Share this ZIP for review before changing the test EFI:\n%s/output/S540-nvidia-transport-v5.zip\n' "$WORK"
else
    printf '\nBuild failed. Share this log:\n%s/build.log\n' "$WORK" >&2
    exit 1
fi
