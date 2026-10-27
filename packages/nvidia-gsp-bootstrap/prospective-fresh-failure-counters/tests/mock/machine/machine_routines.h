/* Explicit CPU-only kernel primitive endpoints, not a Darwin SDK. */
#ifndef S540_FIXTURE_MACHINE_ROUTINES_H
#define S540_FIXTURE_MACHINE_ROUTINES_H
extern "C" int ml_at_interrupt_context(void);
extern "C" int ml_get_interrupts_enabled(void);
#endif
