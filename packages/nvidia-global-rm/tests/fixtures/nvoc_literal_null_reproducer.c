// SPDX-License-Identifier: MIT
// Reduced compiler diagnostic reproducer, not a driver implementation.
// Clang18.1.3 -O1 -fsanitize=undefined -fno-sanitize-recover=all diagnoses the
// anonymous-union member in the unevaluated true branch. The condition is NULL.
// This fixture is kept for provenance; it is not expected to fail on compilers
// that have corrected that diagnostic. No sanitizer is disabled by the driver.
#ifdef KERNEL
#error "Native compiler reproducer must never enter a kernel build"
#endif
typedef struct NativeDynamic { const void *rtti; } NativeDynamic;
typedef struct NativeObject {
    union { NativeDynamic base; const void *rtti; };
} NativeObject;
static NativeDynamic *literalNull(void)
{
    return (NativeObject *)0 ? (NativeDynamic *)&((NativeObject *)0)->rtti : 0;
}
int main(void) { return literalNull() != 0; }
