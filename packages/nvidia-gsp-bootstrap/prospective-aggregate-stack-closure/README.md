# Current native stack measurements for the retained experiment

`check.measure_verified_plan` authenticates the complete current Apple compilation,
the actual make plan, every project unit, full compiler commands and dependency
sidecars, and source/object/stack-capture bytes. It freshly decodes those objects.
The optional final-image pass selects retained named text atoms conservatively;
ambiguous local owners stay in the graph and unmeasured auxiliary code stays
explicitly unknown. Source-scoped local callback roots are lookup identities,
not invented external symbols in the persisted machine graph.

The current callback construction and receiver sources are reviewed again.
Dispatcher worker and privileged RPC caller are separate stack roots. Known
registered dispatcher, timer, work, deferred-bottom and physical-IRQ prefixes
are conservatively added to their separately measured bodies. No old graph is
transferred and no unknown callback, external edge or recursion barrier is
erased to make a capacity fit.

`native_budget.build_profile` encodes the actual 104-byte runtime profile using
the measured known acyclic sums and four explicit experimental allowances:
2048 framework, 4096 unknown subtree, 1024 recursion and 1024 exception bytes.
Required capacity rounds upward to 4096 bytes; equality is accepted. A known
dynamic compiler frame or demand beyond the 16384-byte experimental policy
limit is rejected. The final native measurement must fit the same immutable
profile. These allowances are acknowledged assumptions, not measured bounds on
unknown code. Formal stack, scheduler completion and production proofs remain
false.

`collect_target_stack.py` only reads the actual Intel Mac's `kern.stack_size`.
It accepts its real 32/64-bit raw integer, records the width and bytes, and never
treats `kern.stack_depth_max` as capacity. Physical IRQ capacity remains an
explicit 16384-byte experiment assumption. The userland test client performs
its own target capacity observation; this collector does not load anything.

Local controls exercise capacity equality and overflow, preserved unknowns,
code-contract substitution, object-scoped local roots and the real workflow
request parser against temporary Git commits. They are isolated controls;
only a later successful current native build can create the profile used by a
target package.
