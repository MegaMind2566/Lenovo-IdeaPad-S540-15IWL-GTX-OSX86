/* Explicit CPU-only logger endpoint. No IOKit executes. */
#ifndef S540_FIXTURE_IOLIB_H
#define S540_FIXTURE_IOLIB_H
extern "C" void IOLog(const char *, ...) __attribute__((format(printf, 1, 2)));
#endif
