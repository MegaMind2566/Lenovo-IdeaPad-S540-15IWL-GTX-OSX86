# Experimental retained first-initialization image

`link_native.py` accepts only a complete current native matrix verified by the
separate native compiler. It does not change the frozen idle image verifier.

The actual Apple `ld -r` image preserves every compiled input atom. Optional
private imports in dormant input paths remain visible diagnostics. Only the final
dead-stripped `MH_KEXT_BUNDLE` establishes live closure: private imports must be
fully resolved, public imports require independent actual SDK declarations and
exported public KPI providers, and only `kmod_info` is exported.

Independent SDK references verify the Power and two experimental control
metaclasses, their exact initializer/finalizer instruction and relocation graphs,
and real `kmod_info_t` offsets. The image uses only the pinned SDK's C module
wrappers. All 25 typed original root pointers, loader pointers, module entry
pointers, unchanged firmware sections and normal C array boundaries are checked.

A fresh complete native object graph supplies diagnostic known frame sums. A
104-byte immutable profile records an explicit experimental stack budget and
allowances; it does not claim a formal bound for unknown framework, recursion,
indirect or scheduler behavior. Its code contract binds the current composition,
compiler/SDK, original/project reports, actual object bytes and preliminary graph;
only the late-bound profile data is excluded from its own hash. The actual final
native image graph is measured again and must fit that unchanged profile.

Reports, actual objects, compiler sidecars, SDK references and link logs are
preserved. Packaging independently revalidates the report and verifies the
signed image against the same code, data, roots, imports and metadata. No module
is loaded here and no hardware, PM acknowledgement, reclamation or acceleration
success is claimed.

`check.py` runs actual Linux-to-Mach-O SDK code-generation controls and parser
mutations. These controls are explicitly separate from native build evidence.
