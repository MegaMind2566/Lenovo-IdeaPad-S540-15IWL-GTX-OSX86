The isolated `builders/nvidia_stack_context_refinement.py` companion can remove
one infeasible nested ACPI DSM call edge. It preserves the general entries,
copies the actual measured frames into two contextual nodes, and retains every
other call and unresolved site. The frozen stack collector and source-profile
predecessors are unchanged.

The reviewed source passes one of twelve concrete DSM enum values from its
closed precedence table to `testIfDsmSubFunctionEnabled`. That function passes
the address of its unchanged scalar parameter to the nested remapper. The
nested remapper takes its non-generic branch and returns before the call back
to the tester. The general tester can still receive a generic enum, so its
original edge remains present.

The analysis requires complete measured manifests, exact source/object/stack
sidecars, an operator-selected trusted compiler, a sealed complete compiler
recipe, checked dependencies, sealed expanded functions and table, a byte-equal
object replay, and a real compiler-emitted twelve-value constant probe. It
accepts no archived graph JSON as verified input. A new compiler recipe or
expanded source profile is refused until reviewed explicitly.

The recovery controls are reproducible with the restored pinned sources and
an actual Clang capable of producing x86-64 Mach-O:

```sh
python3 packages/nvidia-global-rm/tests/test_stack_context_refinement.py \
  --upstream /absolute/pinned-upstream

python3 packages/nvidia-global-rm/tests/check_stack_context_source.py \
  --upstream /absolute/pinned-upstream \
  --composition /absolute/verified-source-composition \
  --trusted-compiler /absolute/clang \
  --llvm-objdump /absolute/llvm-objdump \
  --output /absolute/fresh-control-output \
  --include-fatal-policy
```

The second command copies the verified source composition and compiles only
the actual ACPI translation unit for each selected control profile. It does not
compile or certify the complete original profile. The optional fatal assertion
successor is applied only to its separate control copy; its source pair and
mandatory macro remain explicit.

The complete-profile analysis entry point, once fresh inputs exist, is:

```sh
python3 builders/nvidia_stack_context_refinement.py \
  --rm-manifest /absolute/composition/stack-usage-manifest.json \
  --acpi-compilation-report /absolute/composition/full-original-compilation.json \
  --trusted-compiler /absolute/compiler-used-for-those-objects \
  --project-manifest /absolute/composition/project-stack-usage-manifest.json \
  --project-unit-count 60 \
  --llvm-objdump /absolute/llvm-objdump \
  --output /absolute/fresh-context-analysis.json
```

Set the project count to the exact selected composition. The helper also
supports an explicit checked replacement manifest; that does not establish
composition equivalence for a mixed object union. Apple target recipe pins
alone do not establish Apple compiler execution.

Fresh recovery validation is recorded in
`STACK-CONTEXT-REFINEMENT-VALIDATION.json`. The two freshly reviewed complete
recovery commands are retained in `STACK-CONTEXT-COMPILER-RECIPES.json`; they
have new explicit acceptance pins, while the expanded-code seals match the
reviewed baseline and fatal source policies exactly. A complete current
1,100-object context replay remains pending. The helper always reports aggregate stack
safety as unproven: indirect calls, other recursion, external kernel costs,
entry headroom and the actual kernel stack budget require separate evidence.
No original entry or hardware admission is granted by these controls.
