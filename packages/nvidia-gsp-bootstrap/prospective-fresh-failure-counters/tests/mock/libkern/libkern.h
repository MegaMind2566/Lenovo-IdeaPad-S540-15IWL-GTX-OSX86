/* Explicit CPU-only fatal endpoint. */
#ifndef S540_FIXTURE_LIBKERN_H
#define S540_FIXTURE_LIBKERN_H
extern "C" [[noreturn]] void panic(const char *, ...);
#endif
