# Inherited IOKit imports and target-kernel admission

The independent power-service reference produces 285 inherited framework
imports in the reviewed cross-compile probe. Matching that reference and
restricting imports to the actual SDK ancestor namespaces establishes
development compiler/declaration evidence. It does **not** establish that the
target Tahoe kernel will resolve those imports, patch the class correctly or
execute its loader functions. `production_candidate_allowed` remains false.

The reference contains the shared class declaration and Apple's metaclass
definition only. Project virtual methods must be defined by the actual project
object; they cannot become approved framework imports merely because the
reference leaves their bodies out. The exact initializer/finalizer comparison
is a separate control from superclass-vtable resolution.

## What the pinned Apple linker actually does

The primary source is `apple-oss-distributions/xnu` at
`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`:

| Pinned source | Git blob | Relevant behavior |
| --- | --- | --- |
| [kxld_kext.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/kxld/kxld_kext.c#L413-L458) | `1936a476d4dda1b5c6e25a33ba6a4c6c97d42d46` | Symbol resolution precedes class-vtable creation, conditional patching and final unresolved-symbol validation. |
| [kxld_vtable.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/kxld/kxld_vtable.c#L479-L699) | `634c19d4deafd78dc52f3bc98a05b3c31516738d` | Inherited slots can be rewritten to the actual parent's symbol/address; compatibility checks can reject the class. |
| [kxld_sym.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/kxld/kxld_sym.c#L438-L444) | `9060b04da403251b54fa3f844c84584dab34987d` | Replaced undefined symbols no longer count as unresolved; patching marks that state at lines 1022–1026. |
| [kxld.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/kxld/kxld.c#L494-L539) | `1a7c2988eb9d2950d263befc7aabfbadba2e500c` | Dependencies supply superclass vtables and C++ symbols by address as well as the permitted by-name symbol interface. |

This explains why a raw comparison with `IOKit.exports` and `Libkern.exports`
cannot, by itself, classify every inherited `_RESERVED*` reference as a missing
implementation. In particular, `kxld_kext.c:733–736` postpones missing-symbol
errors until vtable patching has had an opportunity to replace those references.
At `kxld_vtable.c:615–647`, a patched inherited slot can acquire the actual
parent's symbol and address even when that replacement was not already a
locally defined symbol in the extension. Interface-filtered dependency C++
symbols are also indexed by address (`kxld_kext.c:284–292`).

That mechanism is conditional, not an exemption for every ancestor name:

* Locally implemented overrides and pure virtual entries are not replaced.
* A same-name parent/child slot is left alone (`kxld_vtable.c:553–558`); absence
  from a raw export list does not prove that this slot will be repaired.
* An incompatible parent pad slot causes failure (`560–572`). Strict patching
  rejects a method declared by the child without an implementation (`574–612`).
* A matching patched superclass vtable must actually be available. Final
  unresolved-symbol validation still fails if resolution or patching did not
  account for a dependency (`kxld_kext.c:1085–1106`).
* This source's relocation pipeline skips `patch_vtables` for split kexts
  (`kxld_kext.c:449–452`). The actual target loader/collection mode must be
  established rather than inferred from this general mechanism.

The missing raw matches for inherited `IOService::open`, `IOService::probe` and
reserved slots therefore remain target-resolution questions. SDK ancestry
alone proves neither their successful resolution nor their failure. An ordinary
dynamic-lookup development link permits undefined symbols and cannot answer
that question.

## Evidence still required

Before calling the bridge an executable kernel closure, verify its actual
Mach-O symbols and slot relocations against the matching target kernel and
dependency/collection images: each import must resolve through the permitted
interface or receive a demonstrated valid inherited-slot replacement, with
the final unresolved set empty. This must include the real superclass and
metaclass vtables, dependency declarations, compatible layout and the target
loader mode. A successful supported target-link/collection validation can
provide that evidence; a namespace-prefix allowlist cannot.

The current SDK-reference check remains useful development evidence. It does
not close target linking, kernel loading/execution, executable-code lifetime,
the original RM callback closure, the stack budget or the PM deadline gates.
No additional laptop test or installable package follows from it alone.
