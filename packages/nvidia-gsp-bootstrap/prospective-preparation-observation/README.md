Preparation observations are attached to the existing Owner snapshot before
failure cleanup. They record the attempted stage, last successful stage, first
failure and already collected host/device facts. The record survives the
existing successful cleanup and Impl destruction.

The PM record distinguishes attach/start, individual IOReturn calls, wait and
the existing ready/domain/active predicates. Explicit validity distinguishes an
actual zero return from an unobserved value. No new hardware query, admission
flag, retry, original entry, acknowledgement or cleanup operation is added.

This profile follows retained-stop and precedes experimental-target-control.
It accepts only the exact recorded B3 source hashes. CPU fixtures exercise
actual transformed method bodies; they are not native or Lenovo evidence.
