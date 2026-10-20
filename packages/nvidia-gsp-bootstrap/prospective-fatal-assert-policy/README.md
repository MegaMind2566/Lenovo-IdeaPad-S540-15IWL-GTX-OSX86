# Optional fatal RM invariant policy

This exact source successor turns an executed invariant assertion into a fatal
diagnostic through the original-header `os_bug_check` facade and the real
Darwin `panic` provider. Ordinary `NV_CHECK` helper bodies remain unchanged.
The policy does not establish successful OOM recovery or a sufficient stack.

`prepare.overlay` accepts the pinned complete `nvassert.h` and `nvassert.c`
pair and returns both replacements. Every original-header translation unit
using this successor must select `S540_NVIDIA_FATAL_ASSERT_POLICY=1` with the
original NVRM/Unix compile profile. The header refuses missing, false or
unreviewed platform configurations. Four assertion helpers are `noreturn`.
Four macros bypass their upstream pre-helper NVLOG operation; PRECOMP
assertions inherit the selected function macro. Direct calls to all four
helpers also terminate.

This deliberately omits the upstream assertion's NVLOG, RCDB journal,
backtrace and file/line output. Expression text is preserved as data, including
literal `%s` and `%n`; status assertions preserve their status code. A trap
prevents continuation if a defective bug-check implementation returns.

The controls execute eight fatal cases in both ordinary and sanitized userspace
variants against the real host `abort` provider. They also compile the complete
selected assertion source, five real macro probes, the existing diagnostic
facade and its KERNEL format provider. Independent Mach-O decoding checks the
exact helper-to-bug-check-to-panic chain, rejects additional calls or unknown
transfers, and permits only the exact defensive `ud2` backstop. `_panic` retains
an unknown stack bound. No kernel code is executed and no RM entry is admitted.

The October 20 reconstruction was tested anew after loss of the previous
workspace. Only the newly generated report is referenced by local validation.
Native Apple execution and complete same-profile integration remain separate.

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-fatal-assert-policy/check.py \
  --upstream /path/to/pinned-open-gpu-kernel-modules \
  --namespace /path/to/S540GlobalRmNamespace.h \
  --sdk /path/to/pinned-MacKernelSDK \
  --output build/fatal-assert-controls
```

Linux replay adds `--host-control --llvm-objdump /path/to/llvm-objdump-18` and
uses Clang with its ASan/UBSan runtimes. The recorded local execution disables
LSan after an actual `/proc/task`/ptrace failure; address, undefined-behavior
and function sanitizers remain active.
