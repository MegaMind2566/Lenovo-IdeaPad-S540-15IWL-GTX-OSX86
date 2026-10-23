# Current experimental native compilation

`compile_native.py` is a separate compiler for the independently replayed
retained first-initialization source plan. Frozen compilers and validators are
unchanged. It refuses non-Intel-macOS execution before creating output and uses
the actual `xcrun` selected Apple clang binaries and clean pinned MacKernelSDK.

All 1,100 make-declared original units and every current project unit are built
freshly. No historical object is reused. The obsolete closed-control kernel TU
is excluded; Power and the new experimental control TU are the only reviewed
initializer owners. Commands, actual complete dependency sidecars, compiler
stack captures, source/object/helper/compiler hashes and SDK inventory are bound
to the current composition. Additional C exports require their exact sole strong
owner. Input symbol closure remains diagnostic until the actual final link.

The native summary is `native-compilation.json`; original/project reports and
their object directories are retained for independent read-only revalidation.
`verify_native_reports` checks exact current commands and every actual input
without compiling or rewriting stack captures. A successful compile does not
claim linking, package readiness, kernel loading or GPU initialization.
