# Optional disabled NVLink child

B8 identified class `0xce6818` (`KernelNvlink`) returning
`NV_ERR_NOT_SUPPORTED` during its engine constructor. The original driver
normally deletes that optional child and continues. The retained diagnostic
profile must preserve a published child on any constructor failure, so it
cannot apply that original cleanup and status normalization.

This profile omits the optional child before allocation or publication only
when the real NVLink library reports uninitialized and the original global
registry returns `NvLinkDisable=1`. The selected original profile is non-Windows
and still compiles the real library with `INCLUDE_NVLINK_LIB`. This profile
does not initialize that library or substitute its predicate.

The exact `KernelNvlink`, instance zero, and empty child slot are required.
Pure queries of the actual strong transaction record require the
current ordinary master, exact NV identity, current owner/generation, active
original call, a validated returned global epoch, no sticky failure and the
small stable snapshot of the real cancellation producer bound by that record.
The producer must still be in operation, owned by the real master, neither
revoked nor publishing revocation. No diagnostic counters are mutated.
An initialized library or another engine keeps
the original constructor path. Registry/protocol errors fail closed. No
failed published child is normalized, detached or freed.

A private 32-byte scalar observation is published once. Its getter requires
the real wrapper-return state and the same actual master and generation.
One bounded record is logged after the original public wrapper unwinds.
It grants no cleanup, DMA stop, physical release or hardware admission.

The focused CPU controls execute the actual transformed constructor, helper,
pure record queries and original library predicate with explicit CPU
endpoints. Native compilation and a separate Lenovo test remain required.
